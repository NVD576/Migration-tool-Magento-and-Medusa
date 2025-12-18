import re
import unicodedata


def _slugify(text: str) -> str:
    if not text:
        return ""

    text = unicodedata.normalize("NFKD", text)
    text = "".join([c for c in text if not unicodedata.combining(c)])
    text = text.lower().strip()
    # tiếng Việt: "đ" không phải ký tự dấu-combining nên cần map thủ công
    text = text.replace("đ", "d")
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text


def transform_category_as_product_category(mg_category: dict, parent_category_id=None) -> dict:
    name = mg_category.get("name") or f"Category {mg_category.get('id')}"
    handle = _slugify(name) or f"category-{mg_category.get('id')}"

    payload = {
        "name": name,
        "handle": handle,
        "is_active": bool(mg_category.get("is_active", True)),
        "rank": int(mg_category.get("position") or 0),
        "metadata": {
            "magento_id": mg_category.get("id"),
            "magento_parent_id": mg_category.get("parent_id"),
            "magento_level": mg_category.get("level"),
            "magento_position": mg_category.get("position"),
        },
    }

    if parent_category_id:
        payload["parent_category_id"] = parent_category_id
    
    description = mg_category.get("description")
    if description:
        payload["description"] = description

    return payload


def transform_category_as_collection(mg_category: dict) -> dict:
    name = mg_category.get("name") or f"Category {mg_category.get('id')}"
    handle = _slugify(name) or f"category-{mg_category.get('id')}"

    return {
        "title": name,
        "handle": handle,
        "metadata": {
            "magento_id": mg_category.get("id"),
            "magento_parent_id": mg_category.get("parent_id"),
            "magento_level": mg_category.get("level"),
            "magento_position": mg_category.get("position"),
        },
    }


