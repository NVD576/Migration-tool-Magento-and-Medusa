import urllib3
import argparse
import json
import sys
import os
import requests
from config import MAGENTO, MEDUSA

from connectors.magento_connector import MagentoConnector
from connectors.medusa_connector import MedusaConnector

from extractors.products import extract_products
from extractors.categories import extract_categories
from extractors.customers import extract_customers
from extractors.orders import extract_orders

from transformers.product_transformer import transform_product
from transformers.category_transformer import (
    transform_category_as_collection,
    transform_category_as_product_category,
)
from transformers.customer_transformer import transform_customer
from transformers.order_transformer import transform_order_as_draft_order

from services.magento_auth import get_magento_token
from services.medusa_auth import get_medusa_token

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def _configure_stdio():
    """
    Windows cmd/powershell đôi khi dùng codepage không hỗ trợ emoji/ký tự có dấu,
    gây UnicodeEncodeError khi print. Ta ép UTF-8 và dùng errors=replace để không crash.
    """
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        # Không block chương trình nếu môi trường không cho reconfigure
        pass


def _env(name: str):
    v = os.environ.get(name)
    if v is None:
        return None
    v = str(v).strip()
    return v if v != "" else None


def _env_bool(name: str):
    v = _env(name)
    if v is None:
        return None
    return v.lower() in ("1", "true", "yes", "y", "on")


def _parse_args():
    parser = argparse.ArgumentParser(description="Magento -> Medusa migration")
    parser.add_argument(
        "--entities",
        default="products,categories,customers,orders",
        help="Danh sách entity cần sync, ví dụ: products,categories,customers,orders",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Giới hạn số lượng record mỗi entity (0 = không giới hạn)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Chỉ in payload (không gọi API create lên Medusa)",
    )

    # Optional overrides (CLI) - nếu không truyền thì dùng env, nếu env không có thì dùng config.py
    parser.add_argument("--magento-base-url", default=None)
    parser.add_argument("--magento-admin-username", default=None)
    parser.add_argument("--magento-admin-password", default=None)
    parser.add_argument("--magento-verify-ssl", action="store_true", help="Bật verify SSL cho Magento")
    parser.add_argument("--magento-insecure", action="store_true", help="Tắt verify SSL cho Magento")

    parser.add_argument("--medusa-base-url", default=None)
    parser.add_argument("--medusa-email", default=None)
    parser.add_argument("--medusa-password", default=None)
    return parser.parse_args()


def _limit_iter(items, limit: int):
    if not limit or limit <= 0:
        return items
    return items[:limit]


def _is_http_status(err: Exception, status_code: int) -> bool:
    return f"{status_code} Client Error" in str(err)


def _fetch_all_product_categories(medusa: MedusaConnector, page_limit: int = 50):
    offset = 0
    out = []
    while True:
        res = medusa.list_product_categories(limit=page_limit, offset=offset)
        items = res.get("product_categories") or res.get("data") or []
        if not items:
            break
        out.extend(items)
        offset += len(items)
        count = res.get("count")
        if count is not None and offset >= count:
            break
    return out


def main():
    _configure_stdio()
    args = _parse_args()
    entities = {e.strip().lower() for e in (args.entities or "").split(",") if e.strip()}

    magento_cfg = dict(MAGENTO)
    medusa_cfg = dict(MEDUSA)

    # Apply overrides (CLI > env > config)
    magento_cfg["BASE_URL"] = args.magento_base_url or _env("MAGENTO_BASE_URL") or magento_cfg.get("BASE_URL")
    magento_cfg["ADMIN_USERNAME"] = args.magento_admin_username or _env("MAGENTO_ADMIN_USERNAME") or magento_cfg.get("ADMIN_USERNAME")
    magento_cfg["ADMIN_PASSWORD"] = args.magento_admin_password or _env("MAGENTO_ADMIN_PASSWORD") or magento_cfg.get("ADMIN_PASSWORD")
    if args.magento_verify_ssl:
        magento_cfg["VERIFY_SSL"] = True
    elif args.magento_insecure:
        magento_cfg["VERIFY_SSL"] = False
    else:
        env_verify = _env_bool("MAGENTO_VERIFY_SSL")
        if env_verify is not None:
            magento_cfg["VERIFY_SSL"] = env_verify

    medusa_cfg["BASE_URL"] = args.medusa_base_url or _env("MEDUSA_BASE_URL") or medusa_cfg.get("BASE_URL")
    medusa_cfg["EMAIL"] = args.medusa_email or _env("MEDUSA_EMAIL") or medusa_cfg.get("EMAIL")
    medusa_cfg["PASSWORD"] = args.medusa_password or _env("MEDUSA_PASSWORD") or medusa_cfg.get("PASSWORD")

    print(f"Magento base_url={magento_cfg.get('BASE_URL')} verify_ssl={magento_cfg.get('VERIFY_SSL')} user={magento_cfg.get('ADMIN_USERNAME')}")
    print(f"Medusa  base_url={medusa_cfg.get('BASE_URL')} email={medusa_cfg.get('EMAIL')}")

    print("🔐 Login Magento...")
    try:
        magento_token = get_magento_token(
            magento_cfg["BASE_URL"],
            magento_cfg["ADMIN_USERNAME"],
            magento_cfg["ADMIN_PASSWORD"],
            magento_cfg["VERIFY_SSL"]
        )
    except requests.exceptions.RequestException as e:
        print("\n❌ Không kết nối được Magento.")
        print(f"- base_url: {magento_cfg.get('BASE_URL')}")
        print("- Gợi ý: kiểm tra Magento server/container có đang chạy không, đúng http/https + port chưa, và URL này mở được trên máy bạn.")
        print(f"- Chi tiết: {e}")
        return

    magento = MagentoConnector(
        base_url=magento_cfg["BASE_URL"],
        token=magento_token,
        verify_ssl=magento_cfg["VERIFY_SSL"]
    )

    print("🔐 Login Medusa...")
    try:
        medusa_token = get_medusa_token(
            medusa_cfg["BASE_URL"],
            medusa_cfg["EMAIL"],
            medusa_cfg["PASSWORD"]
        )
    except requests.exceptions.RequestException as e:
        print("\n❌ Không kết nối được Medusa.")
        print(f"- base_url: {medusa_cfg.get('BASE_URL')}")
        print("- Gợi ý: kiểm tra Medusa đang chạy (thường `http://localhost:9000`) và đúng email/password.")
        print(f"- Chi tiết: {e}")
        return

    medusa = MedusaConnector(
        base_url=medusa_cfg["BASE_URL"],
        api_token=medusa_token
    )

    if "categories" in entities:
        print("🗂️ Fetching categories from Magento...")
        categories = extract_categories(magento)
        categories = _limit_iter(categories, args.limit)
        # Tạo cha trước (level nhỏ), rồi tới con
        categories_sorted = sorted(
            categories,
            key=lambda c: (
                int(c.get("level") or 0),
                int(c.get("position") or 0),
                int(c.get("id") or 0),
            ),
        )

        # Load categories đã có trên Medusa để map theo handle
        try:
            existing = _fetch_all_product_categories(medusa)
            handle_to_id = {c.get("handle"): c.get("id") for c in existing if c.get("handle") and c.get("id")}
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

                # Magento root parent (thường id=1) => parent null
                parent_medusa_id = None
                if parent_mg_id and parent_mg_id not in (1, "1"):
                    parent_medusa_id = mg_to_medusa.get(parent_mg_id)
                    if not parent_medusa_id:
                        next_pending.append(cat)
                        continue

                name = cat.get("name") or str(mg_id)
                print(f"➡ Syncing category: {name}")

                payload_pc = transform_category_as_product_category(cat, parent_category_id=parent_medusa_id)

                if args.dry_run:
                    print(json.dumps(payload_pc, ensure_ascii=False, indent=2))
                    mg_to_medusa[mg_id] = f"(dry-run) {payload_pc.get('handle')}"
                    progress = True
                    continue

                # Nếu đã có theo handle thì chỉ map lại để con bám theo được
                existing_id = handle_to_id.get(payload_pc.get("handle"))
                if existing_id:
                    mg_to_medusa[mg_id] = existing_id
                    progress = True
                    continue

                try:
                    res = medusa.create_product_category(payload_pc)
                    created = res.get("product_category") or res.get("productCategory") or res
                    created_id = created.get("id") if isinstance(created, dict) else None
                    if created_id:
                        mg_to_medusa[mg_id] = created_id
                        handle_to_id[payload_pc.get("handle")] = created_id
                    progress = True
                except Exception as e:
                    # Fallback nếu Medusa version không có product-categories
                    if _is_http_status(e, 404):
                        payload_col = transform_category_as_collection(cat)
                        medusa.create_collection(payload_col)
                        progress = True
                    elif _is_http_status(e, 409):
                        # Đã tồn tại: cố map lại bằng handle
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
            # Không block toàn bộ migration, nhưng báo để bạn kiểm tra parent_id lạ
            print(f"⚠️ Có {len(pending)} category chưa sync được do thiếu parent mapping.")

    if "customers" in entities:
        print("👤 Fetching customers from Magento...")
        customers = extract_customers(magento)
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
                medusa.create_customer(payload)
            except requests.exceptions.HTTPError as e:
                resp = getattr(e, "response", None)
                status = resp.status_code if resp is not None else None

                if status == 409:
                    # Đã tồn tại
                    continue

                # Với 400/422: in chi tiết để biết Medusa đang chê field nào, rồi tiếp tục customer khác
                if status in (400, 422):
                    try:
                        detail = resp.json() if resp is not None else {"error": str(e)}
                    except Exception:
                        detail = (resp.text if resp is not None else str(e))

                    print("❌ Tạo customer thất bại (Bad Request). Bỏ qua customer này.")
                    print("Response từ Medusa:")
                    print(json.dumps(detail, ensure_ascii=False, indent=2) if isinstance(detail, (dict, list)) else str(detail))
                    print("Payload đã gửi:")
                    print(json.dumps(payload, ensure_ascii=False, indent=2))
                    continue

                raise
            except Exception as e:
                if _is_http_status(e, 409):
                    continue
                raise

    if "orders" in entities:
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
        else:
            for o in orders:
                inc = o.get("increment_id") or o.get("entity_id")
                print(f"➡ Syncing order: {inc}")

                payload = transform_order_as_draft_order(o, region_id)
                if args.dry_run:
                    print(json.dumps(payload, ensure_ascii=False, indent=2))
                    continue

                # Lưu ý: schema draft order có thể khác tuỳ Medusa version.
                # Nếu lỗi, bạn chạy --dry-run để xem payload và mình sẽ chỉnh theo log lỗi.
                try:
                    medusa.create_draft_order(payload)
                except Exception as e:
                    # Fallback: một số version dùng custom_items thay cho items (custom line items)
                    if "items" in str(e) and payload.get("items"):
                        payload2 = dict(payload)
                        payload2["custom_items"] = payload2.pop("items")
                        medusa.create_draft_order(payload2)
                    else:
                        raise

    if "products" in entities:
        print("📦 Fetching products from Magento...")
        products = extract_products(magento)
        products = _limit_iter(products, args.limit)

        print(f"🚀 Migrating {len(products)} products...\n")

        for product in products:
            print(f"➡ Syncing: {product['name']}")

            payload = transform_product(
                product,
                magento_cfg["BASE_URL"]
            )

            if args.dry_run:
                print(json.dumps(payload, ensure_ascii=False, indent=2))
                continue

            try:
                medusa.create_product(payload)
            except Exception as e:
                if _is_http_status(e, 409):
                    continue
                raise

    print("\n✅ Migration completed!")


if __name__ == "__main__":
    main()
