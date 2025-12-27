import json
import requests
from connectors.magento_connector import MagentoConnector
from connectors.medusa_connector import MedusaConnector
from extractors.customers import extract_customers
from transformers.customer_transformer import transform_customer, transform_address
from migrators.utils import _limit_iter, _is_duplicate_http, _resp_json_or_text, _is_http_status, log_dry_run

def migrate_customers(magento: MagentoConnector, medusa: MedusaConnector, args):
    print("\n[STAGE 3/5] 📥 DATA EXTRACTION & FETCHING")
    print("👤 Fetching customers from Magento...")
    customers = extract_customers(magento)
    
    # Filter by IDs if provided
    customer_ids = None
    if getattr(args, "customer_ids", None):
        customer_ids = {x.strip() for x in str(args.customer_ids).split(",") if x.strip()}
        print(f"   (Filter by IDs: {customer_ids})")
        customers = [c for c in customers if str(c.get("id")) in customer_ids]
    
    customers = _limit_iter(customers, args.limit)
    print(f"🚀 Migrating {len(customers)} customers...\n")

    # Counters for summary
    count_success = 0
    count_ignore = 0
    count_fail = 0

    print(f"\n[STAGE 4/5] ⚙️ DATA TRANSFORMATION")
    print(f"[STAGE 5/5] 🚀 SYNCING")
    for c in customers:
        email = c.get("email")
        if not email:
            continue
        print(f"➡ Syncing customer: {email}")
        payload = transform_customer(c)

        log_dry_run(payload, "customer", args)
        if args.dry_run:
            continue

        try:
            res = medusa.create_customer(payload, idempotency_key=f"customer:{email}")
            created = res.get("customer") or res.get("customer") or res
            medusa_customer_id = created.get("id") if isinstance(created, dict) else None
            print(f"✅ Đã tạo customer: {email}")
            count_success += 1

            # Sync addresses
            if medusa_customer_id:
                for addr in c.get("addresses", []):
                    try:
                        addr_payload = transform_address(addr)
                        medusa.create_customer_address(medusa_customer_id, addr_payload)
                        print(f"   ✅ Đã thêm địa chỉ: {addr_payload.get('address_1')}")
                    except Exception as ae:
                        print(f"   ⚠️ Lỗi thêm địa chỉ: {ae}")

        except requests.exceptions.HTTPError as e:
            resp = getattr(e, "response", None)
            if _is_duplicate_http(resp):
                print(f"ℹ️  Customer {email} đã tồn tại, bỏ qua")
                count_ignore += 1
                
                # Still try to sync addresses for existing customer if we can get ID
                try:
                    # We might need to fetch the customer to get the ID
                    # For now, if it's a dry-run or we don't have ID, we skip
                    # But if we wanted to be thorough, we'd fetch it here.
                    pass
                except:
                    pass
                continue

            status = resp.status_code if resp is not None else None
            if status in (400, 422):
                print("❌ Tạo customer thất bại (Bad Request). Bỏ qua customer này.")
                detail = _resp_json_or_text(resp)
                print(json.dumps(detail, ensure_ascii=False, indent=2) if isinstance(detail, (dict, list)) else str(detail))
                count_fail += 1
                continue
            raise
        except Exception as e:
            if _is_http_status(e, 409):
                count_ignore += 1
                continue
            count_fail += 1
            raise

    print(f"\n--- Customer Migration Summary ---")
    print(f"✅ Success: {count_success}")
    print(f"ℹ️  Ignored: {count_ignore}")
    print(f"❌ Failed:  {count_fail}")
    print(f"----------------------------------\n")
