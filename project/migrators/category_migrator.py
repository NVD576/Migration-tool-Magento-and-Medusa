import json
import requests
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
)

def migrate_categories(magento: MagentoConnector, medusa: MedusaConnector, args):
    print("🗂️ Fetching categories from Magento...")
    categories = extract_categories(magento)
    
    # Filter by IDs if provided
    cat_ids = None
    if getattr(args, "category_ids", None):
        cat_ids = {x.strip() for x in str(args.category_ids).split(",") if x.strip()}
        print(f"   (Filter by IDs: {cat_ids})")
        # Ensure we filter by string comparison as API might return ints
        categories = [c for c in categories if str(c.get("id")) in cat_ids]

    categories = _limit_iter(categories, args.limit)

    categories_sorted = sorted(
        categories,
        key=lambda c: (
            int(c.get("level") or 0),
            int(c.get("position") or 0),
            int(c.get("id") or 0),
        ),
    )

    # Fetch existing to map
    try:
        existing = _fetch_all_product_categories(medusa)
        handle_to_id = {
            c.get("handle"): c.get("id")
            for c in existing
            if c.get("handle") and c.get("id")
        }
    except Exception:
        handle_to_id = {}

    print(f"🚀 Migrating {len(categories_sorted)} categories...\n")
    mg_to_medusa = {}
    pending = list(categories_sorted)
    progress = True

    while pending and progress:
        progress = False
        next_pending = []

        for cat in pending:
            mg_id = cat.get("id")
            parent_mg_id = cat.get("parent_id")
            parent_medusa_id = None

            if parent_mg_id and parent_mg_id not in (1, "1"):
                parent_medusa_id = mg_to_medusa.get(parent_mg_id)
                if not parent_medusa_id:
                    next_pending.append(cat)
                    continue

            name = cat.get("name") or str(mg_id)
            print(f"➡ Syncing category: {name}")

            payload_pc = transform_category_as_product_category(
                cat, parent_category_id=parent_medusa_id
            )

            if args.dry_run:
                print(json.dumps(payload_pc, ensure_ascii=False, indent=2))
                mg_to_medusa[mg_id] = f"(dry-run) {payload_pc.get('handle')}"
                progress = True
                continue

            existing_id = handle_to_id.get(payload_pc.get("handle"))
            if existing_id:
                print(f"ℹ️  Category '{name}' đã tồn tại, bỏ qua")
                mg_to_medusa[mg_id] = existing_id
                progress = True
                continue

            try:
                res = medusa.create_product_category(
                    payload_pc, idempotency_key=f"category:{mg_id}"
                )
                created = res.get("product_category") or res.get("productCategory") or res
                created_id = created.get("id") if isinstance(created, dict) else None
                if created_id:
                    mg_to_medusa[mg_id] = created_id
                    handle_to_id[payload_pc.get("handle")] = created_id
                    print(f"✅ Đã tạo category: {name}")
                progress = True

            except requests.exceptions.HTTPError as e:
                resp = getattr(e, "response", None)
                if _is_duplicate_http(resp):
                    print(f"ℹ️  Category '{name}' đã tồn tại, bỏ qua")
                    progress = True
                    continue

                if resp is not None and resp.status_code in (400, 422):
                    print("❌ Tạo category thất bại (Bad Request). Bỏ qua category này.")
                    detail = _resp_json_or_text(resp)
                    print(json.dumps(detail, ensure_ascii=False, indent=2) if isinstance(detail, (dict, list)) else str(detail))
                    progress = True
                    continue
                raise

            except Exception as e:
                if _is_http_status(e, 404):
                    payload_col = transform_category_as_collection(cat)
                    medusa.create_collection(payload_col)
                    progress = True
                elif _is_http_status(e, 409):
                     # Already exists, try mapping
                    try:
                        existing = _fetch_all_product_categories(medusa)
                        handle_to_id = {c.get("handle"): c.get("id") for c in existing if c.get("handle") and c.get("id")}
                        ex_id = handle_to_id.get(payload_pc.get("handle"))
                        if ex_id:
                            mg_to_medusa[mg_id] = ex_id
                            progress = True
                    except Exception:
                        pass
                else:
                    raise

        pending = next_pending

    if pending:
        print(f"⚠️ Có {len(pending)} category chưa sync được do thiếu parent mapping.")
    
    return mg_to_medusa
