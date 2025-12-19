import json
import requests
from connectors.magento_connector import MagentoConnector
from connectors.medusa_connector import MedusaConnector
from extractors.customers import extract_customers
from transformers.customer_transformer import transform_customer
from migrators.utils import _limit_iter, _is_duplicate_http, _resp_json_or_text, _is_http_status

def migrate_customers(magento: MagentoConnector, medusa: MedusaConnector, args):
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

    for c in customers:
        email = c.get("email")
        if not email:
            continue
        print(f"➡ Syncing customer: {email}")
        payload = transform_customer(c)

        if args.dry_run:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            continue

        try:
            medusa.create_customer(payload, idempotency_key=f"customer:{email}")
            print(f"✅ Đã tạo customer: {email}")
        except requests.exceptions.HTTPError as e:
            resp = getattr(e, "response", None)
            if _is_duplicate_http(resp):
                print(f"ℹ️  Customer {email} đã tồn tại, bỏ qua")
                continue

            status = resp.status_code if resp is not None else None
            if status in (400, 422):
                print("❌ Tạo customer thất bại (Bad Request). Bỏ qua customer này.")
                detail = _resp_json_or_text(resp)
                print(json.dumps(detail, ensure_ascii=False, indent=2) if isinstance(detail, (dict, list)) else str(detail))
                continue
            raise
        except Exception as e:
            if _is_http_status(e, 409):
                continue
            raise
