import json
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from connectors.magento_connector import MagentoConnector
from connectors.medusa_connector import MedusaConnector
from extractors.customers import extract_customers
from transformers.customer_transformer import transform_customer, transform_address
from migrators.utils import _limit_iter, _is_duplicate_http, _resp_json_or_text, _is_http_status, log_dry_run, handle_medusa_api_error

def _sync_single_customer(customer, medusa: MedusaConnector, args):
    email = customer.get("email")
    if not email:
        return 'fail'

    print(f"➡ Syncing customer: {email}")
    print(f"   [STEP 1] Preparing info...")
    payload = transform_customer(customer)

    log_dry_run(payload, "customer", args)
    if args.dry_run:
        return ('ignore', "Dry run enabled")

    try:
        print(f"   [STEP 2] Creating customer account...")
        res = medusa.create_customer(payload, idempotency_key=f"customer:{email}")
        created = res.get("customer") or res
        medusa_customer_id = created.get("id") if isinstance(created, dict) else None
        print(f"   ✅ [SUCCESS] Customer: {email}")

        if medusa_customer_id:
            for addr in customer.get("addresses", []):
                try:
                    addr_payload = transform_address(addr)
                    medusa.create_customer_address(medusa_customer_id, addr_payload)
                    print(f"      - Address synced: {addr_payload.get('address_1')}")
                except Exception as ae:
                    print(f"      ⚠️  Address skip: {ae}")
        
        return ('success', None)

    except requests.exceptions.HTTPError as e:
        status_tuple = handle_medusa_api_error(e, "Customer", email)
        return status_tuple if isinstance(status_tuple, tuple) else (status_tuple, str(e))
    except Exception as e:
        reason = str(e)
        print(f"   ❌ [FAIL] Customer '{email}': {reason}")
        return ('fail', reason)

def migrate_customers(magento: MagentoConnector, medusa: MedusaConnector, args):
    print("\n" + "="*50)
    print("👤 CUSTOMER MIGRATION PHASE")
    print("="*50)
    print("📥 Fetching customers from Magento...")
    customers = extract_customers(magento)
    
    if getattr(args, "customer_ids", None):
        customer_ids = {x.strip() for x in str(args.customer_ids).split(",") if x.strip()}
        print(f"   (Filter by IDs: {customer_ids})")
        customers = [c for c in customers if str(c.get("id")) in customer_ids]
    
    customers = _limit_iter(customers, args.limit)
    customer_count = len(customers)
    print(f"🚀 Migrating {customer_count} customers...\n")

    count_success = 0
    count_ignore = 0
    count_fail = 0

    print("⚙️ Starting transformation & sync process...")

    with ThreadPoolExecutor(max_workers=args.max_workers or 10) as executor:
        futures = {executor.submit(_sync_single_customer, c, medusa, args): c for c in customers}

        processed_count = 0
        for future in as_completed(futures):
            processed_count += 1
            customer = futures[future]
            email = customer.get('email', 'N/A')
            
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
                print(f"   ❌ [CRITICAL] Unexpected error for '{email}': {e}")
                count_fail += 1
            
            if processed_count % 5 == 0 or processed_count == customer_count:
                print(f"📊 Progress: {processed_count}/{customer_count} customers processed...")


    print("\n\n--- Customer Migration Summary ---")
    print(f"✅ Success: {count_success}")
    print(f"ℹ️ Ignored: {count_ignore}")
    print(f"❌ Failed:  {count_fail}")
    print(f"----------------------------------\n")
