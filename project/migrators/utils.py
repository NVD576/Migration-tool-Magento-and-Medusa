import json
from connectors.medusa_connector import MedusaConnector

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
