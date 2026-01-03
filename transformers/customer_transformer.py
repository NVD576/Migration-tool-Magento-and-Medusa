def transform_customer(mg_customer: dict) -> dict:
    email = (mg_customer.get("email") or "").strip()
    first_name = (mg_customer.get("firstname") or "").strip()
    last_name = (mg_customer.get("lastname") or "").strip()
    
    payload = {"email": email}
    if first_name:
        payload["first_name"] = first_name
    if last_name:
        payload["last_name"] = last_name
    
    metadata = {
        "magento_id": mg_customer.get("id"),
        "magento_group_id": mg_customer.get("group_id"),
        "magento_created_at": mg_customer.get("created_at"),
        "magento_updated_at": mg_customer.get("updated_at"),
    }
    payload["metadata"] = {k: v for k, v in metadata.items() if v is not None}

    addresses = mg_customer.get("addresses") or []
    if addresses and isinstance(addresses, list):
        phone = addresses[0].get("telephone")
        if phone:
            payload["phone"] = phone

    return payload

def transform_address(mg_address: dict) -> dict:
    street = mg_address.get("street") or []
    full_address = ", ".join(street) if isinstance(street, list) else str(street)
    
    payload = {
        "first_name": mg_address.get("firstname"),
        "last_name": mg_address.get("lastname"),
        "company": mg_address.get("company") or "",
        "address_1": full_address,
        "address_2": "",
        "city": mg_address.get("city") or "",
        "country_code": (mg_address.get("country_id") or "VN").lower(),
        "phone": mg_address.get("telephone") or "",
        "postal_code": mg_address.get("postcode") or "",
        "is_default_shipping": mg_address.get("default_shipping") or False,
        "is_default_billing": mg_address.get("default_billing") or False,
    }

    region_data = mg_address.get("region")
    if isinstance(region_data, dict):
        payload["province"] = region_data.get("region") or ""
    else:
        payload["province"] = str(mg_address.get("region") or "")

    metadata = {
        "magento_address_id": mg_address.get("id"),
    }
    payload["metadata"] = {k: v for k, v in metadata.items() if v is not None}

    return payload
