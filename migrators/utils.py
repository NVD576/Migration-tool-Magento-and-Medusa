import json
import requests
from datetime import datetime
from connectors.medusa_connector import MedusaConnector

def get_timestamp():
    return datetime.now().strftime("%H:%M:%S")

def log_info(msg, indent=0):
    prefix = "   " * indent
    print(f"[{get_timestamp()}] {prefix}ℹ️  {msg}")

def log_success(msg, indent=0):
    prefix = "   " * indent
    print(f"[{get_timestamp()}] {prefix}✅ {msg}")

def log_warning(msg, indent=0):
    prefix = "   " * indent
    print(f"[{get_timestamp()}] {prefix}⚠️  {msg}")

def log_error(msg, indent=0):
    prefix = "   " * indent
    print(f"[{get_timestamp()}] {prefix}❌ {msg}")

def log_step(step_num, total_steps, msg, indent=0):
    prefix = "   " * indent
    print(f"[{get_timestamp()}] {prefix}[STEP {step_num}/{total_steps}] {msg}")

def log_progress(current, total, entity_type):
    pct = (current / total * 100) if total > 0 else 0
    bar_len = 20
    filled = int(bar_len * current / total) if total > 0 else 0
    bar = "█" * filled + "░" * (bar_len - filled)
    print(f"[{get_timestamp()}] 📊 Progress: [{bar}] {current}/{total} ({pct:.0f}%) {entity_type}")

def log_section(title):
    print(f"\n[{get_timestamp()}] {'='*50}")
    print(f"[{get_timestamp()}] 📦 {title}")
    print(f"[{get_timestamp()}] {'='*50}")

def log_summary(entity_type, success, ignored, failed):
    print(f"\n[{get_timestamp()}] --- {entity_type} Migration Summary ---")
    print(f"[{get_timestamp()}] ✅ Success: {success}")
    print(f"[{get_timestamp()}] ℹ️  Ignored: {ignored}")
    print(f"[{get_timestamp()}] ❌ Failed:  {failed}")
    print(f"[{get_timestamp()}] {'-'*35}")

def _limit_iter(items, limit: int):
    if not limit or limit <= 0:
        return items
    return items[:limit]

def _is_http_status(err: Exception, status_code: int) -> bool:
    return f"{status_code} Client Error" in str(err)

def _resp_text(resp):
    if resp is None:
        return ""
    try:
        return resp.text or ""
    except Exception:
        return ""

def _resp_json_or_text(resp):
    if resp is None:
        return None
    try:
        return resp.json()
    except Exception:
        return _resp_text(resp)

def _is_duplicate_http(resp) -> bool:
    if resp is None:
        return False
    if resp.status_code == 409:
        return True
    txt = _resp_text(resp).lower()
    return any(
        s in txt for s in ("already exists", "duplicate", "unique", "exists", "handle")
    )

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

def _fetch_all_variants(medusa: MedusaConnector, page_limit: int = 50):
    offset = 0
    out = []
    while True:
        res = medusa.list_products(limit=page_limit, offset=offset, expand="variants")
        products = res.get("products") or res.get("data") or []
        if not products:
            break
        for p in products:
            variants = p.get("variants") or []
            out.extend(variants)
        offset += len(products)
        count = res.get("count")
        if count is not None and offset >= count:
            break
    return out

def log_dry_run(payload, entity_type, args):
    import json
    import os
    
    if getattr(args, "dry_run", False):
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    
    if getattr(args, "dry_run_file", False):
        run_id = getattr(args, "run_id", "latest")
        
        if not os.path.exists("exports"):
            os.makedirs("exports")
            
        filename = f"exports/payloads_{run_id}.json"
        
        data = []
        if os.path.exists(filename):
            try:
                with open(filename, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except:
                data = []
        
        data.append({
            "entity": entity_type,
            "payload": payload
        })
        
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

def handle_medusa_api_error(e: requests.exceptions.HTTPError, entity_name: str, entity_identifier: str):
    resp = getattr(e, "response", None)
    
    if _is_duplicate_http(resp):
        reason = "Already exists in Medusa (Duplicate)"
        print(f"   ℹ️  [SKIP] {entity_name} '{entity_identifier}': {reason}")
        return ('ignore', reason)
    
    if resp is not None and resp.status_code in (400, 422):
        detail = _resp_json_or_text(resp)
        reason = json.dumps(detail, ensure_ascii=False) if isinstance(detail, (dict, list)) else str(detail)
        print(f"   ❌ [FAIL] {entity_name} '{entity_identifier}': HTTP {resp.status_code}")
        print(f"      - Reason: {reason}")
        return ('fail', reason)
    
    reason = f"HTTP Error {resp.status_code if resp else 'unknown'}: {str(e)}"
    print(f"   ❌ [FAIL] {entity_name} '{entity_identifier}': {reason}")
    return ('fail', reason)
