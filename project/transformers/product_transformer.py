import re
import unicodedata


def _slugify(text: str) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join([c for c in text if not unicodedata.combining(c)])
    text = text.lower().strip()
    text = text.replace("đ", "d")
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text


def _handle_from_magento_product(mg_product: dict) -> str:
    # Ưu tiên SKU để idempotent (chạy lại không tạo trùng)
    sku = (mg_product.get("sku") or "").strip()
    if sku:
        return _slugify(sku) or sku.lower()
    name = (mg_product.get("name") or "").strip()
    return _slugify(name) or f"product-{mg_product.get('id')}"


def extract_images(mg_product, magento_base_url):
    images = []

    for entry in mg_product.get("media_gallery_entries", []):
        file_path = entry.get("file")
        if not file_path:
            continue

        images.append({
            "url": f"{magento_base_url}/pub/media/catalog/product{file_path}"
        })

    return images


def transform_product(mg_product, magento_base_url, categories=None):
    name = mg_product["name"]
    price = int(float(mg_product["price"]) )
    handle = _handle_from_magento_product(mg_product)

    payload = {
        "title": name,
        "handle": handle,
        "description": name,
        "status": "published",
        "discountable": True,
        "metadata": {
            "magento_id": mg_product.get("id"),
            "magento_sku": mg_product.get("sku"),
        },

        "categories": categories or [],

        "options": [
            {
                "title": "Default",
                "values": ["Default"]
            }
        ],

        "variants": [
            {
                "title": "Default variant",
                "manage_inventory": False,
                "sku": mg_product.get("sku"),
                "options": {
                    "Default": "Default"
                },
                "prices": [
                    {
                        "currency_code": "eur",
                        "amount": price
                    }
                ]
            }
        ],

        "sales_channels": [
            {
                "id": "sc_01KC4H49PTBS2XBMJAWKG952TG",
            }
        ],
        "shipping_profile_id": "sp_01KC4H46N3H82S4C03309443MZ",


    }

    images = extract_images(mg_product, magento_base_url)
    if images:
        payload["images"] = images

    return payload 

