import json
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from connectors.magento_connector import MagentoConnector
from connectors.medusa_connector import MedusaConnector
from extractors.products import extract_products
from extractors.categories import extract_categories
from transformers.product_transformer import transform_product
from transformers.category_transformer import transform_category_as_product_category
from migrators.utils import (
    _limit_iter, _is_duplicate_http, _resp_json_or_text, 
    _fetch_all_product_categories, _is_http_status, log_dry_run,
    handle_medusa_api_error, log_info, log_success, log_warning, 
    log_error, log_step, log_progress, log_section, log_summary, get_timestamp,
    log_error, log_step, log_progress, log_section, log_summary, get_timestamp,
    check_stop_signal, check_pause_signal
)

def _fetch_all_magento_categories(magento: MagentoConnector, args):
    log_info("Fetching Magento categories for mapping...", indent=1)
    all_cats = extract_categories(magento, args)
    cat_map = {c.get("id"): c for c in all_cats}
    log_success(f"Fetched {len(cat_map)} categories successfully.", indent=1)
    return cat_map

def _sync_single_product(product, magento: MagentoConnector, medusa: MedusaConnector, args, mg_to_medusa_map, mg_category_map, sales_channel_id, shipping_profile_id):
    product_name = product.get('name', 'N/A')
    product_sku = product.get('sku', 'N/A')
    print(f"[{get_timestamp()}] Syncing: {product_name} (SKU: {product_sku})")

    product_categories = []
    links = (product.get("extension_attributes") or {}).get("category_links") or []
    
    for link in links:
        mg_cat_id = link.get("category_id")
        if mg_cat_id in (1, "1"): continue

        medusa_cat_id = mg_to_medusa_map.get(mg_cat_id) or mg_to_medusa_map.get(str(mg_cat_id)) or mg_to_medusa_map.get(int(mg_cat_id))
        
        if not medusa_cat_id:
            mg_cat = mg_category_map.get(str(mg_cat_id)) or mg_category_map.get(int(mg_cat_id))
            name = mg_cat.get("name") if mg_cat else f"ID {mg_cat_id}"
            log_warning(f"Category {name} (Magento ID: {mg_cat_id}) not found in Medusa map. Skipping link.", indent=1)
        
        if medusa_cat_id:
            product_categories.append({"id": medusa_cat_id})

    payload = transform_product(
        product, 
        magento.base_url, 
        categories=product_categories,
        sales_channel_id=sales_channel_id,
        shipping_profile_id=shipping_profile_id
    )

    log_dry_run(payload, "product", args)
    if args.dry_run:
        return ('ignore', "Dry run enabled")

    try:
        medusa.create_product(payload, idempotency_key=f"product:{product.get('id')}")
        log_success(f"Product '{product_name}' synced.", indent=1)
        return ('success', None)
    except requests.exceptions.HTTPError as e:
        return handle_medusa_api_error(e, "Product", product_name)
    except Exception as e:
        reason = str(e)
        log_error(f"Product '{product_name}': {reason}", indent=1)
        return ('fail', reason)

def migrate_products(magento: MagentoConnector, medusa: MedusaConnector, args, mg_to_medusa_map=None):
    log_section("PRODUCT MIGRATION PHASE")
    print(f"[{get_timestamp()}] Fetching products from Magento...")
    
    p_ids = None
    if getattr(args, "product_ids", None):
        p_ids = [x.strip() for x in str(args.product_ids).split(",") if x.strip()]
        log_info(f"Filter by IDs: {p_ids}", indent=1)

    products = extract_products(magento, ids=p_ids)
    products = _limit_iter(products, args.limit)
    product_count = len(products)
    print(f"[{get_timestamp()}] Found {product_count} products to migrate...\n")
    
    # 1. STOP CHECK
    if check_pause_signal(): return
    if check_stop_signal(): return
    
    mg_to_medusa = mg_to_medusa_map if mg_to_medusa_map is not None else {}
    mg_category_map = None

    sales_channel_id = None
    shipping_profile_id = None
    
    try:
        print(f"[{get_timestamp()}] Fetching sales channels from Medusa...")
        sc_response = medusa.get_sales_channels()
        sales_channels = sc_response.get("sales_channels", [])
        if sales_channels:
            sales_channel_id = sales_channels[0].get("id")
            log_success(f"Using sales channel: {sales_channels[0].get('name')} ({sales_channel_id})", indent=1)
        else:
            log_warning("No sales channels found, using default", indent=1)
    except Exception as e:
        log_warning(f"Failed to fetch sales channels: {e}. Using default.", indent=1)

    # 2. STOP CHECK
    if check_pause_signal(): return
    if check_stop_signal(): return
    
    try:
        print(f"[{get_timestamp()}] Fetching shipping profiles from Medusa...")
        sp_response = medusa.get_shipping_profiles()
        shipping_profiles = sp_response.get("shipping_profiles", [])
        if shipping_profiles:
            shipping_profile_id = shipping_profiles[0].get("id")
            log_success(f"Using shipping profile: {shipping_profiles[0].get('name')} ({shipping_profile_id})", indent=1)
        else:
            log_warning("No shipping profiles found, using default", indent=1)
    except Exception as e:
        log_warning(f"Failed to fetch shipping profiles: {e}. Using default.", indent=1)

    # 3. STOP CHECK
    if check_pause_signal(): return
    if check_stop_signal(): return

    if not mg_category_map:
        mg_category_map = _fetch_all_magento_categories(magento, args)

    # 4. STOP CHECK
    if check_pause_signal(): return
    if check_stop_signal(): return

    if not mg_to_medusa:
        existing = _fetch_all_product_categories(medusa)
        for c in existing:
             meta = c.get("metadata") or {}
             mg_id = meta.get("magento_id")
             if mg_id:
                 mg_to_medusa[mg_id] = c.get("id")
                 try:
                     mg_to_medusa[int(mg_id)] = c.get("id")
                     mg_to_medusa[str(mg_id)] = c.get("id")
                 except:
                     pass
                     
    # 5. STOP CHECK
    if check_pause_signal(): return
    if check_stop_signal(): return

    count_success = 0
    count_ignore = 0
    count_fail = 0

    print(f"[{get_timestamp()}] Starting transformation & sync process...")
    
    with ThreadPoolExecutor(max_workers=args.max_workers or 10) as executor:
        futures = {
            executor.submit(
                _sync_single_product,
                product, magento, medusa, args, mg_to_medusa, mg_category_map, sales_channel_id, shipping_profile_id
            ): product for product in products
        }

        processed_count = 0
        for future in as_completed(futures):
            # CHECK STOP SIGNAL
            if check_pause_signal(): pass # If paused, we just waited. If resumed, we continue.
            
            if check_stop_signal():
                log_warning("🛑 Stop signal detected. Cancelling remaining product tasks...", indent=1)
                for f in futures:
                    if not f.done():
                        f.cancel()
                break
                
            processed_count += 1
            product = futures[future]
            product_name = product.get('name', 'N/A')
            
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
                log_error(f"[CRITICAL] Unexpected error for '{product_name}': {e}", indent=1)
                count_fail += 1
            

    log_summary("Product", count_success, count_ignore, count_fail)

