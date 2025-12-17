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


def transform_product(mg_product, magento_base_url):
    name = mg_product["name"]
    price = int(float(mg_product["price"]) * 100)

    payload = {
        "title": name,
        "description": name,
        "status": "published",
        "discountable": True,

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
                "options": {
                    "Default": "Default"
                },
                "prices": [
                    {
                        "currency_code": "usd",
                        "amount": price
                    }
                ]
            }
        ],

        "sales_channels": [
            {
                "id": "sc_01KC4H49PTBS2XBMJAWKG952TG",
                # "name": "Default Sales Channel",
            }
        ],
        "shipping_profile_id": "sp_01KC4H46N3H82S4C03309443MZ",


    }

    images = extract_images(mg_product, magento_base_url)
    if images:
        payload["images"] = images

    return payload 

