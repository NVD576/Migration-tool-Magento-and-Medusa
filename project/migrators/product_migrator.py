import json
import requests
from connectors.magento_connector import MagentoConnector
from connectors.medusa_connector import MedusaConnector
from extractors.products import extract_products
from extractors.categories import extract_categories
from transformers.product_transformer import transform_product
from transformers.category_transformer import transform_category_as_product_category
from migrators.utils import _limit_iter, _is_duplicate_http, _resp_json_or_text, _fetch_all_product_categories, _is_http_status

def _fetch_all_magento_categories(magento: MagentoConnector):
    print("   Please wait, fetching all Magento categories for mapping...")
    all_cats = extract_categories(magento)
    cat_map = {c.get("id"): c for c in all_cats}
    print(f"   Fetched {len(cat_map)} categories.")
    return cat_map

def migrate_products(magento: MagentoConnector, medusa: MedusaConnector, args, mg_to_medusa_map=None):
    print("📦 Fetching products from Magento...")
    
    # Parse product_ids from args
    p_ids = None
    if getattr(args, "product_ids", None):
        p_ids = [x.strip() for x in str(args.product_ids).split(",") if x.strip()]
        print(f"   (Filter by IDs: {p_ids})")

    products = extract_products(magento, ids=p_ids)
    products = _limit_iter(products, args.limit)
    print(f"🚀 Migrating {len(products)} products...\n")

    mg_to_medusa = mg_to_medusa_map if mg_to_medusa_map is not None else {}
    mg_category_map = None

    if not mg_category_map:
        mg_category_map = _fetch_all_magento_categories(magento)

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

    for product in products:
        print(f"➡ Syncing: {product['name']}")

        product_categories = []
        links = (product.get("extension_attributes") or {}).get("category_links") or []
        
        for link in links:
            mg_cat_id = link.get("category_id")
            if mg_cat_id in (1, "1"): continue

            medusa_cat_id = mg_to_medusa.get(mg_cat_id)
            
            if not medusa_cat_id:
                 mg_cat = mg_category_map.get(str(mg_cat_id)) or mg_category_map.get(int(mg_cat_id))
                 if mg_cat:
                     print(f"   ⚠️ Category {mg_cat_id} not mapped. Creating on-the-fly...")
                     name = mg_cat.get("name")
                     payload_pc = transform_category_as_product_category(mg_cat, parent_category_id=None)
                     
                     try:
                         res = medusa.create_product_category(payload_pc, idempotency_key=f"category:{mg_cat_id}")
                         created = res.get("product_category") or res.get("productCategory") or res
                         medusa_cat_id = created.get("id")
                         if medusa_cat_id:
                             mg_to_medusa[mg_cat_id] = medusa_cat_id
                             print(f"   ✅ Created missing category: {name} ({medusa_cat_id})")
                     except requests.exceptions.HTTPError as he:
                         print(f"   ❌ Failed to auto-create category {mg_cat_id}: {he}")
                         if he.response is not None:
                             print(f"   Response: {he.response.text}")
                     except Exception as e:
                         print(f"   ❌ Failed to auto-create category {mg_cat_id}: {e}")
            
            if medusa_cat_id:
                product_categories.append({"id": medusa_cat_id})

        payload = transform_product(product, magento.base_url, categories=product_categories)

        if args.dry_run:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            continue

        try:
            medusa.create_product(payload, idempotency_key=f"product:{product.get('id')}")
            print("✅ Đã tạo sản phẩm")
        except requests.exceptions.HTTPError as e:
            resp = getattr(e, "response", None)
            if _is_duplicate_http(resp):
                print("ℹ️  Sản phẩm đã tồn tại, bỏ qua")
                continue
            if resp is not None and resp.status_code in (400, 422):
                print("❌ Tạo product thất bại (Bad Request).")
                detail = _resp_json_or_text(resp)
                print(json.dumps(detail, ensure_ascii=False, indent=2) if isinstance(detail, (dict, list)) else str(detail))
                continue
            raise
        except Exception as e:
            if _is_http_status(e, 409):
                continue
            raise
