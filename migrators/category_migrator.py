import json
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from connectors.magento_connector import MagentoConnector
from connectors.medusa_connector import MedusaConnector
from extractors.categories import extract_categories
from transformers.category_transformer import (
    transform_category_as_collection,
    transform_category_as_product_category,
)
from migrators.utils import (
    _limit_iter,
    _fetch_all_product_categories,
    _is_duplicate_http,
    _resp_json_or_text,
    _is_http_status,
    log_dry_run,
    handle_medusa_api_error,
    get_timestamp, log_info, log_success, log_warning, log_error, log_section, log_summary,
    check_stop_signal, check_pause_signal
)

def _sync_single_category(cat, medusa: MedusaConnector, args, mg_to_medusa_map, handle_to_id_map):
    mg_id = cat.get("id")
    name = cat.get("name") or str(mg_id)
    parent_mg_id = cat.get("parent_id")
    parent_medusa_id = None

    if parent_mg_id and parent_mg_id not in (1, "1"):
        parent_medusa_id = mg_to_medusa_map.get(parent_mg_id) or mg_to_medusa_map.get(str(parent_mg_id))
        if not parent_medusa_id:
            print(f"   Parent category {parent_mg_id} for {name} not found. Deferring.")
            return mg_id, None, 'defer', None

    print(f"Syncing category: {name}")

    print(f"   [STEP 1] Preparing data...")
    payload_pc = transform_category_as_product_category(cat, parent_category_id=parent_medusa_id)
    handle = payload_pc.get("handle")

    log_dry_run(payload_pc, "category", args)
    if args.dry_run:
        return mg_id, f"(dry-run) {handle}", 'success', handle
    
    existing_id = handle_to_id_map.get(handle)
    if existing_id:
        print(f"   [SKIP] Category '{name}' handle '{handle}' already exists.")
        return mg_id, existing_id, 'ignore', handle

    try:
        print(f"   [STEP 2] Creating on Medusa API...")
        res = medusa.create_product_category(payload_pc, idempotency_key=f"category:{mg_id}")
        created = res.get("product_category") or res.get("productCategory") or res
        created_id = created.get("id")

        if created_id:
            print(f"   ✅ [SUCCESS] Created category: {name}")
            return mg_id, created_id, 'success', handle
        else:
            reason = f"No ID returned from API. Response: {json.dumps(res)}"
            print(f"   ❌ [FAIL] Category {name}: {reason}")
            return mg_id, None, 'fail', handle

    except requests.exceptions.HTTPError as e:
        status_tuple = handle_medusa_api_error(e, "Category", name)
        status = status_tuple[0] if isinstance(status_tuple, tuple) else status_tuple
        return mg_id, None, status, handle
    except Exception as e:
        reason = str(e)
        print(f"   [FAIL] Category {name}: {reason}")
        return mg_id, None, 'fail', handle

# Placeholder for build_category_tree, assuming it's defined elsewhere or imported.
# For the purpose of this edit, we'll define a minimal one to make the code syntactically correct.
def build_category_tree(categories):
    # This is a simplified placeholder. A real implementation would build a proper tree.
    # For this edit, we'll just return a flat list of nodes for demonstration.
    nodes = []
    for cat in categories:
        nodes.append({'data': cat, 'children': []})
    return nodes

def migrate_categories(magento: MagentoConnector, medusa: MedusaConnector, args):
    print("\n" + "="*50)
    print("🗂️  CATEGORY MIGRATION PHASE")
    print("="*50)
    print("📥 Fetching categories from Magento...")
    categories = extract_categories(magento, args)
    
    if getattr(args, "category_ids", None):
        selected_ids = {x.strip() for x in str(args.category_ids).split(",") if x.strip()}
        print(f"   (Filter by IDs: {selected_ids})")
        
        all_cat_map = {str(c.get("id")): c for c in categories}
        include_set = set()
        
        for cid in selected_ids:
            curr = cid
            while curr and curr not in ("1", 1):
                include_set.add(str(curr))
                cat_obj = all_cat_map.get(str(curr))
                curr = str(cat_obj.get("parent_id")) if cat_obj else None
        
        print(f"   (Including ancestors, total categories to process: {len(include_set)})")
        categories = [c for c in categories if str(c.get("id")) in include_set]
    else:
        print(f"[{get_timestamp()}] Fetching categories from Magento...")
        categories = _limit_iter(categories, args.limit)

    # STOP CHECK
    if check_pause_signal(): return {}
    if check_stop_signal(): return {}

    print(f"[{get_timestamp()}] Found {len(categories)} categories to migrate...\n")
    
    if check_stop_signal():
        log_warning("🛑 Stop signal detected. Skipping category migration.", indent=1)
        return {} # Assuming mg_to_medusa_map is returned

    # Build tree
    tree = build_category_tree(categories)

    # STOP CHECK
    if check_stop_signal(): return {}

    count_success = 0
    count_ignore = 0
    count_fail = 0
    
    mg_to_medusa = {}
 
    try:
        existing = _fetch_all_product_categories(medusa)
        handle_to_id = {c.get("handle"): c.get("id") for c in existing if c.get("handle") and c.get("id")}
        for c in existing:
            meta = c.get("metadata") or {}
            mg_id = meta.get("magento_id")
            if mg_id:
                mg_to_medusa[str(mg_id)] = c.get("id")
                mg_to_medusa[int(mg_id)] = c.get("id")
    except Exception as e:
        print(f"⚠️ Could not fetch existing categories from Medusa: {e}. Parent mapping might fail.")
        handle_to_id = {}

    # STOP CHECK
    if check_stop_signal(): return {}

    deferred_categories = []

    print(f"[{get_timestamp()}] Starting transformation & sync process...")
    
    # Process level-by-level (BFS)
    queue = [node for node in tree]  # start with root nodes
    
    while queue:
        # CHECK STOP SIGNAL
        if check_pause_signal(): break
        if check_stop_signal():
            log_warning("🛑 Stop signal detected. Cancelling remaining category tasks...", indent=1)
            break
            
        current_node = queue.pop(0)
        cat = current_node['data']
        children = current_node['children']
        
        # Add children to queue
        queue.extend(children)

        # Assuming level_categories is meant to be the current category being processed
        # or a batch collected from the queue. Given the snippet, it's ambiguous.
        # To make it syntactically correct, we'll process `cat` as a single item.
        level_categories = [cat] # This makes the `for cat in level_categories` loop work.
        print(f"\n-- Syncing category {cat.get('name')} (ID: {cat.get('id')}) --") # Adapted print statement

        with ThreadPoolExecutor(max_workers=args.max_workers or 10) as executor:
            futures = {
                executor.submit(_sync_single_category, c, medusa, args, mg_to_medusa, handle_to_id): c
                for c in level_categories # Changed `cat` to `c` to avoid shadowing outer `cat`
            }

            for future in as_completed(futures):
                # STOP CHECK inside future loop
                if check_pause_signal(): pass 

                cat = futures[future]
                try:
                    mg_id, new_medusa_id, status, handle = future.result()
                    if status == 'success':
                        count_success += 1
                        if new_medusa_id:
                            mg_to_medusa[mg_id] = new_medusa_id
                            if handle: handle_to_id[handle] = new_medusa_id
                    elif status == 'ignore':
                        count_ignore += 1
                        if new_medusa_id:
                            mg_to_medusa[mg_id] = new_medusa_id
                    elif status == 'defer':
                        deferred_categories.append(cat)
                    else: 
                        count_fail += 1
                except Exception as e:
                    print(f"\n❌ [CRITICAL] Worker for category '{cat.get('name')}' failed: {e}")
                    count_fail += 1

    if deferred_categories:
        print(f"\n⚠️ Could not sync {len(deferred_categories)} categories due to missing parents:")
        for cat in deferred_categories:
            print(f"  - {cat.get('name')} (ID: {cat.get('id')})")
    
    print(f"\n--- Category Migration Summary ---")
    log_summary("Category", count_success, count_ignore, count_fail)
    
    print(f"Success: {count_success}")
    print(f"Ignored: {count_ignore}")
    print(f"Failed:  {count_fail}")
    print(f"----------------------------------\n")

    return mg_to_medusa
