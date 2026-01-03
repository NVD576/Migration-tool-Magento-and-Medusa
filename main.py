import urllib3
import argparse
import warnings
import sys
import logging
import os
import requests

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from typing import cast
from io import TextIOWrapper

stdout = cast(TextIOWrapper, sys.stdout)
stderr = cast(TextIOWrapper, sys.stderr)

from config import MAGENTO, MEDUSA
from connectors.magento_connector import MagentoConnector
from connectors.medusa_connector import MedusaConnector
from services.magento_auth import get_magento_token
from services.medusa_auth import get_medusa_token

from migrators.category_migrator import migrate_categories
from migrators.customer_migrator import migrate_customers
from migrators.order_migrator import migrate_orders
from migrators.product_migrator import migrate_products

def _configure_stdio():
    try:
        if hasattr(sys.stdout, "reconfigure"):
            stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
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
        help="List of entities to sync, e.g., products,categories,customers,orders",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limit number of records per entity (0 = unlimited)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print payload only (no Medusa API calls)",
    )
    parser.add_argument(
        "--dry-run-file",
        action="store_true",
        help="Save dry-run results to JSON file",
    )
    parser.add_argument(
        "--finalize-orders",
        action="store_true",
        help="After creating Draft Order, attempt to confirm it as a real Order (if supported).",
    )
 
    parser.add_argument("--run-id", default=None, help="Mã ID cho lần chạy (dùng cho tên file export)")
    parser.add_argument("--product-ids", default=None, help="Comma separated list of product IDs to sync")
    parser.add_argument("--category-ids", default=None, help="Comma separated list of category IDs to sync")
    parser.add_argument("--order-ids", default=None, help="Comma separated list of order IDs to sync")
    parser.add_argument("--customer-ids", default=None, help="Comma separated list of customer IDs to sync")
    parser.add_argument(
        "--max-workers",
        type=int,
        default=10,
        help="Max workers for concurrent processing (default: 10)",
    )
    parser.add_argument(
        "--category-strategy",
        default="list",
        choices=["list", "tree"],
        help="Category fetching strategy: 'list' (paginated) or 'tree' (category tree)",
    )
 
    parser.add_argument("--magento-base-url", default=None)
    parser.add_argument("--magento-admin-username", default=None)
    parser.add_argument("--magento-admin-password", default=None)
    parser.add_argument("--magento-verify-ssl", action="store_true", help="Enable SSL verification for Magento")
    parser.add_argument("--magento-insecure", action="store_true", help="Disable SSL verification for Magento")
    parser.add_argument("--medusa-base-url", default=None)
    parser.add_argument("--medusa-email", default=None)
    parser.add_argument("--medusa-password", default=None)
    parser.add_argument(
        "--skip-init-log",
        action="store_true",
        help="Skip logging for STAGE 1 and STAGE 2 (Login & Config)",
    )
    return parser.parse_args()

def main():
    _configure_stdio()
    args = _parse_args()
    entities = {e.strip().lower() for e in (args.entities or "").split(",") if e.strip()}

    magento_cfg = dict(MAGENTO)
    medusa_cfg = dict(MEDUSA)

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

    medusa_cfg["BASE_URL"] = args.medusa_base_url or _env("MEDUSA_BASE_URL") or medusa_cfg.get("BASE_URL") or ""
    medusa_cfg["EMAIL"] = args.medusa_email or _env("MEDUSA_EMAIL") or medusa_cfg.get("EMAIL") or ""
    medusa_cfg["PASSWORD"] = args.medusa_password or _env("MEDUSA_PASSWORD") or medusa_cfg.get("PASSWORD") or ""

    magento_token = _env("MAGENTO_TOKEN")
    medusa_token = _env("MEDUSA_TOKEN")
    is_gui = magento_token is not None and medusa_token is not None

    if not args.skip_init_log and not is_gui:
        print(f"Magento base_url={magento_cfg.get('BASE_URL')} verify_ssl={magento_cfg.get('VERIFY_SSL')} user={magento_cfg.get('ADMIN_USERNAME')}")
        print(f"Medusa  base_url={medusa_cfg.get('BASE_URL')} email={medusa_cfg.get('EMAIL')}")

    stages = []
    if not magento_token or not medusa_token:
        stages.append("🔐 LOGIN & AUTHENTICATION")
    stages.append("🔌 CONFIGURATION & READINESS")
    stages.append("🚀 MIGRATION WORKFLOW STARTING")

    total_stages = len(stages)
    current_stage = 0

    def print_stage(name):
        nonlocal current_stage
        current_stage += 1

    try:
        if not magento_token:
            print_stage("🔐 LOGIN & AUTHENTICATION")
            magento_token = get_magento_token(
                magento_cfg["BASE_URL"],
                magento_cfg["ADMIN_USERNAME"],
                magento_cfg["ADMIN_PASSWORD"],
                magento_cfg["VERIFY_SSL"],
            )
        else:
            if not args.skip_init_log:
                print(f"✅ [SESSION] Magento: Session authenticated.")

        magento = MagentoConnector(base_url=magento_cfg["BASE_URL"], token=magento_token, verify_ssl=magento_cfg["VERIFY_SSL"])

        if not medusa_token:
            if current_stage == 0:
                 print_stage("🔐 LOGIN & AUTHENTICATION")
            medusa_token = get_medusa_token(
                medusa_cfg["BASE_URL"], medusa_cfg["EMAIL"], medusa_cfg["PASSWORD"]
            )
        else:
            if not args.skip_init_log:
                print(f"✅ [SESSION] Medusa: Session authenticated.")

        medusa = MedusaConnector(base_url=medusa_cfg["BASE_URL"], api_token=medusa_token)
        
    except Exception:
        return

    print_stage("🔌 CONFIGURATION & READINESS")
    if not args.skip_init_log:
        print("✅ Magento & Medusa connections initialized.")

    mg_to_medusa_map = {}

    if "categories" in entities:
        mg_to_medusa_map = migrate_categories(magento, medusa, args)

    if "customers" in entities:
        migrate_customers(magento, medusa, args)

    if "products" in entities:
        migrate_products(magento, medusa, args, mg_to_medusa_map=mg_to_medusa_map)

    if "orders" in entities:
        migrate_orders(magento, medusa, args)



    print("\n✅ Migration completed!")

if __name__ == "__main__":
    main()
