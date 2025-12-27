import json
import requests
from connectors.magento_connector import MagentoConnector
from connectors.medusa_connector import MedusaConnector
from extractors.orders import extract_orders
from transformers.order_transformer import transform_order
from migrators.utils import _limit_iter, _fetch_all_variants, _is_duplicate_http, _resp_json_or_text, log_dry_run

def migrate_orders(magento: MagentoConnector, medusa: MedusaConnector, args):
    print("\n[STAGE 3/5] 📥 DATA EXTRACTION & FETCHING")
    print("🧾 Fetching orders from Magento...")
    orders = extract_orders(magento)
    
    # Filter by IDs if provided
    order_ids = None
    if getattr(args, "order_ids", None):
        order_ids = {x.strip() for x in str(args.order_ids).split(",") if x.strip()}
        print(f"   (Filter by IDs: {order_ids})")
        orders = [o for o in orders if str(o.get("entity_id")) in order_ids or str(o.get("increment_id")) in order_ids]
    
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

    # Counters for summary
    count_success = 0
    count_ignore = 0
    count_fail = 0

    print(f"\n[STAGE 4/5] ⚙️ DATA TRANSFORMATION")
    print(f"[STAGE 5/5] 🚀 SYNCING")
    for o in orders:
        inc = o.get("increment_id") or o.get("entity_id")
        print(f"➡ Syncing order: {inc}")

        payload = transform_order(o, region_id, sku_map, shipping_option)

        log_dry_run(payload, "order", args)
        if args.dry_run:
            continue

        try:
            # 1. Create Draft
            res = medusa.create_draft_order(payload, idempotency_key=f"order:{inc}")
            draft = res.get("draft_order") or res.get("draftOrder") or res
            draft_id = draft.get("id") if isinstance(draft, dict) else None

            # 2. Finalize (only if requested)
            if draft_id and getattr(args, 'finalize_orders', False):
                try:
                    finalized = medusa.finalize_draft_order(draft_id)
                    if finalized is None:
                        print(f"⚠️ Draft Order {draft_id} created. Finalize not supported/returned empty.")
                    else:
                        print(f"✅ Finalized Order from Draft: {draft_id}")
                        count_success += 1
                        
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
            elif draft_id:
                print(f"✅ Created Draft Order: {draft_id} (Not finalized)")
                count_success += 1
            else:
                print("✅ Created Draft Order (unknown ID)")
                count_success += 1

        except requests.exceptions.HTTPError as e:
            resp = getattr(e, "response", None)
            if _is_duplicate_http(resp):
                print(f"ℹ️  Order {inc} đã tồn tại, bỏ qua")
                count_ignore += 1
                continue
            if resp is not None and resp.status_code in (400, 422):
                print(" Tạo Draft Order thất bại (Bad Request).")
                detail = _resp_json_or_text(resp)
                print(json.dumps(detail, ensure_ascii=False, indent=2) if isinstance(detail, (dict, list)) else str(detail))
                count_fail += 1
                continue
            raise
        except Exception:
            count_fail += 1
            raise

    print(f"\n--- Order Migration Summary ---")
    print(f"✅ Success: {count_success}")
    print(f"ℹ️  Ignored: {count_ignore}")
    print(f"❌ Failed:  {count_fail}")
    print(f"-------------------------------\n")
