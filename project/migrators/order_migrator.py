import json
import requests
from connectors.magento_connector import MagentoConnector
from connectors.medusa_connector import MedusaConnector
from extractors.orders import extract_orders
from transformers.order_transformer import transform_order
from migrators.utils import _limit_iter, _fetch_all_variants, _is_duplicate_http, _resp_json_or_text

def migrate_orders(magento: MagentoConnector, medusa: MedusaConnector, args):
    print("🧾 Fetching orders from Magento...")
    orders = extract_orders(magento)
    orders = _limit_iter(orders, args.limit)
    print(f"🚀 Migrating {len(orders)} orders...\n")

    region_id = None
    try:
        regions_res = medusa.get_regions()
        regions = regions_res.get("regions") or regions_res.get("data") or []
        if regions:
            region_id = regions[0].get("id")
    except Exception:
        region_id = None

    if not region_id:
        print("⚠️ Không lấy được region_id từ Medusa (/admin/regions). Bỏ qua orders.")
        return

    # Load variants mapping
    print("🔍 Fetching existing variants from Medusa...")
    all_variants = _fetch_all_variants(medusa)
    sku_map = {}
    for v in all_variants:
        if v.get("sku") and v.get("id"):
            sku_map[v.get("sku")] = v.get("id")
    print(f"✅ Found {len(sku_map)} variants for mapping.\n")

    # Fetch shipping options
    print(f"🚚 Fetching shipping options (any)...")
    shipping_option = None
    try:
        so_res = medusa.list_shipping_options(limit=20)
        so_items = so_res.get("shipping_options") or so_res.get("data") or []
        if so_items:
            so = so_items[0]
            shipping_option = {
                "id": so.get("id"),
                "name": so.get("name") or "Standard Shipping",
            }
            print(f"✅ Using shipping option: {shipping_option['id']} ({shipping_option['name']})")
        else:
            print("⚠️ No shipping options found. Order finalization might fail.")
    except Exception as e:
        print(f"⚠️ Failed to fetch shipping options: {e}")

    for o in orders:
        inc = o.get("increment_id") or o.get("entity_id")
        print(f"➡ Syncing order: {inc}")

        payload = transform_order(o, region_id, sku_map, shipping_option)

        if args.dry_run:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            continue

        try:
            # 1. Create Draft
            res = medusa.create_draft_order(payload, idempotency_key=f"order:{inc}")
            draft = res.get("draft_order") or res.get("draftOrder") or res
            draft_id = draft.get("id") if isinstance(draft, dict) else None

            # 2. Finalize
            if draft_id:
                try:
                    finalized = medusa.finalize_draft_order(draft_id)
                    if finalized is None:
                        print(f"⚠️ Draft Order {draft_id} created. Finalize not supported/returned empty.")
                    else:
                        print(f"✅ Finalized Order from Draft: {draft_id}")
                        
                        # Post-creation fulfillment
                        try:
                            medusa.create_fulfillment(draft_id, draft.get("items") or [])
                            print(f"   ✅ Created fulfillment for order {draft_id}")
                        except Exception as fe:
                            print(f"   ⚠️ Failed to create fulfillment: {fe}")

                except requests.exceptions.HTTPError as fe:
                    print(f"⚠️ Draft Order {draft_id} created, but Finalize failed.")
                    if fe.response.status_code == 500:
                         print("   (Server Error 500 during finalize. Likely an inventory bug. Saved as Draft.)")
                    else:
                         print(f"   Status: {fe.response.status_code}")
                         print(fe.response.text)
            else:
                print("✅ Created Draft Order (unknown ID)")

        except requests.exceptions.HTTPError as e:
            resp = getattr(e, "response", None)
            if _is_duplicate_http(resp):
                continue
            if resp is not None and resp.status_code in (400, 422):
                print(" Tạo Draft Order thất bại (Bad Request).")
                detail = _resp_json_or_text(resp)
                print(json.dumps(detail, ensure_ascii=False, indent=2) if isinstance(detail, (dict, list)) else str(detail))
                continue
            raise
        except Exception:
            raise
