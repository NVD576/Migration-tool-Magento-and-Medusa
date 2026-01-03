def _to_cents(value) -> int:

    try:

        return int(float(value))

    except Exception:

        return 0



def _transform_address(mg_address: dict) -> dict:

    if not mg_address:

        return {}


    street = mg_address.get("street")

    if isinstance(street, list):

        address_1 = street[0] if len(street) > 0 else None

        address_2 = street[1] if len(street) > 1 else None

    else:

        address_1 = street

        address_2 = None


    province = mg_address.get("region") or mg_address.get("region_code")


    return {

        "first_name": mg_address.get("firstname"),

        "last_name": mg_address.get("lastname"),

        "phone": mg_address.get("telephone"),

        "address_1": address_1,

        "address_2": address_2,

        "city": mg_address.get("city"),

        "province": province,

        "postal_code": mg_address.get("postcode"),

        "country_code": (mg_address.get("country_id") or "").lower() or None,

    }



def transform_order(mg_order: dict, region_id: str, sku_map: dict = None, shipping_option: dict = None) -> dict:

    if sku_map is None:

        sku_map = {}


    email = mg_order.get("customer_email") or ""


    items = []


    for it in mg_order.get("items", []) or []:
        if it.get("parent_item_id"):
            continue

        title = it.get("name") or it.get("sku") or "Item"
        quantity = int(it.get("qty_ordered") or 0)
        unit_price = _to_cents(it.get("price") or it.get("base_price") or 0)
        sku = it.get("sku")

        if quantity <= 0:
            continue
        
        variant_id = sku_map.get(sku) if sku else None

        if variant_id:
            items.append({
                "variant_id": variant_id,
                "quantity": quantity,
                "unit_price": unit_price,
                "metadata": {
                    "magento_sku": sku,
                    "magento_item_id": it.get("item_id"),
                },
            })
        else:
            items.append({
                "title": title,
                "unit_price": unit_price,
                "quantity": quantity,
                "metadata": {
                    "magento_sku": sku,
                    "magento_item_id": it.get("item_id"),
                },
            })


    billing_address = _transform_address(mg_order.get("billing_address") or {})


    shipping_address = {}
    ext = mg_order.get("extension_attributes") or {}
    shipping_assignments = ext.get("shipping_assignments") or []
    if shipping_assignments and isinstance(shipping_assignments, list):
        sa0 = shipping_assignments[0] or {}
        shipping = (sa0.get("shipping") or {})
        shipping_address = _transform_address(shipping.get("address") or {})


    shipping_methods = []
    if shipping_option:
        shipping_amount = _to_cents(mg_order.get("shipping_amount") or 0)
        shipping_methods.append({
            "shipping_option_id": shipping_option.get("id"),
            "amount": shipping_amount,
            "name": shipping_option.get("name")
        })


    payload = {
        "email": email,
        "region_id": region_id,
        "items": items,
        "billing_address": billing_address or None,
        "shipping_address": shipping_address or None,
        "shipping_methods": shipping_methods,

        "metadata": {

            "magento_entity_id": mg_order.get("entity_id"),

            "magento_increment_id": mg_order.get("increment_id"),

            "magento_status": mg_order.get("status"),

            "magento_grand_total": mg_order.get("grand_total"),

            "magento_order_currency_code": mg_order.get("order_currency_code"),

            "magento_created_at": mg_order.get("created_at"),

            "magento_updated_at": mg_order.get("updated_at"),

        },

    }


    return {k: v for k, v in payload.items() if v is not None}

