import json
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from connectors.magento_connector import MagentoConnector
from connectors.medusa_connector import MedusaConnector
from extractors.orders import extract_orders
from transformers.order_transformer import transform_order
from migrators.utils import (
    _limit_iter, _fetch_all_variants, _is_duplicate_http, 
    _resp_json_or_text, log_dry_run, handle_medusa_api_error
)

def _sync_single_order(order, medusa: MedusaConnector, args, region_id, sku_map, shipping_option):
    inc = order.get("increment_id") or order.get("entity_id")
    print(f"Syncing order: {inc}")

    print(f"   [STEP 1] Mapping data & SKUs...")
    payload = transform_order(order, region_id, sku_map, shipping_option)

    log_dry_run(payload, "order", args)
    if args.dry_run:
        return ('ignore', "Dry run enabled")

    try:
        print(f"   [STEP 2] Creating Draft Order...")
        res = medusa.create_draft_order(payload, idempotency_key=f"order:{inc}")
        draft = res.get("draft_order") or res.get("draftOrder") or res
        draft_id = draft.get("id") if isinstance(draft, dict) else None

        if draft_id and getattr(args, 'finalize_orders', False):
            try:
                print(f"   [STEP 3] Finalizing order...")
                finalized = medusa.finalize_draft_order(draft_id)
                if finalized is None:
                    print(f"⚠️ Draft Order {draft_id} created. Finalize not supported/returned empty.")
                else:
                    print(f"✅ Finalized Order from Draft: {draft_id}")
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
            print(f"   [SUCCESS] Created Draft Order: {draft_id} (Not finalized)")
        else:
            print("   [SUCCESS] Created Draft Order (unknown ID)")
        
        return ('success', None)

    except requests.exceptions.HTTPError as e:
        status_tuple = handle_medusa_api_error(e, "Draft Order", inc)
        return status_tuple if isinstance(status_tuple, tuple) else (status_tuple, str(e))
    except Exception as e:
        reason = str(e)
        print(f"   [FAIL] Order '{inc}': {reason}")
        return ('fail', reason)

def migrate_orders(magento: MagentoConnector, medusa: MedusaConnector, args):
    print("\n" + "="*50)
    print("🧾 ORDER MIGRATION PHASE")
    print("="*50)
    print("📥 Fetching orders from Magento...")
    orders = extract_orders(magento)
    
    if getattr(args, "order_ids", None):
        order_ids = {x.strip() for x in str(args.order_ids).split(",") if x.strip()}
        print(f"   (Filter by IDs: {order_ids})")
        orders = [o for o in orders if str(o.get("entity_id")) in order_ids or str(o.get("increment_id")) in order_ids]
    
    orders = _limit_iter(orders, args.limit)
    order_count = len(orders)
    print(f"🚀 Migrating {order_count} orders...\n")

    region_id = None
    try:
        regions_res = medusa.get_regions()
        regions = regions_res.get("regions") or regions_res.get("data") or []
        if regions:
            region_id = regions[0].get("id")
    except Exception:
        region_id = None

    if not region_id:
        print("Could not get region_id from Medusa (/admin/regions). Skipping orders.")
        return

    print("🔍 Fetching existing variants from Medusa...")
    all_variants = _fetch_all_variants(medusa)
    sku_map = {v.get("sku"): v.get("id") for v in all_variants if v.get("sku") and v.get("id")}
    print(f"Found {len(sku_map)} variants for mapping.\n")

    print("🚚 Fetching shipping options...")
    shipping_option = None
    try:
        so_res = medusa.list_shipping_options(limit=20)
        so_items = so_res.get("shipping_options") or so_res.get("data") or []
        if so_items:
            so = so_items[0]
            shipping_option = {"id": so.get("id"), "name": so.get("name") or "Standard Shipping"}
            print(f"Using shipping option: {shipping_option['id']} ({shipping_option['name']})")
        else:
            print("No shipping options found. Order finalization might fail.")
    except Exception as e:
        print(f"Failed to fetch shipping options: {e}")

    count_success = 0
    count_ignore = 0
    count_fail = 0

    print("Starting transformation & sync process...")

    with ThreadPoolExecutor(max_workers=args.max_workers or 10) as executor:
        futures = {
            executor.submit(_sync_single_order, o, medusa, args, region_id, sku_map, shipping_option): o
            for o in orders
        }

        processed_count = 0
        for future in as_completed(futures):
            processed_count += 1
            order = futures[future]
            inc = order.get("increment_id") or order.get("entity_id")
            
            try:
                res_tuple = future.result()
                if isinstance(res_tuple, tuple):
                    status, reason = res_tuple
                else:
                    status, reason = res_tuple, None
                    
                if status == 'success':
                    count_success += 1
                elif status == 'ignore':
                    count_ignore += 1
                else: 
                    count_fail += 1
            except Exception as e:
                print(f"   ❌ [CRITICAL] Unexpected error for '{inc}': {e}")
                count_fail += 1
            
            if processed_count % 5 == 0 or processed_count == order_count:
                print(f"📊 Progress: {processed_count}/{order_count} orders processed...")


    print(f"\n\n--- Order Migration Summary ---")
    print(f"✅ Success: {count_success}")
    print(f"ℹ️ Ignored: {count_ignore}")
    print(f"❌ Failed:  {count_fail}")
    print(f"-------------------------------\n")
