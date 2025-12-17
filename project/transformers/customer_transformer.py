def transform_customer(mg_customer: dict) -> dict:
    email = (mg_customer.get("email") or "").strip()
    first_name = (mg_customer.get("firstname") or "").strip()
    last_name = (mg_customer.get("lastname") or "").strip()

    payload = {"email": email}
    if first_name:
        payload["first_name"] = first_name
    if last_name:
        payload["last_name"] = last_name

    # metadata để trace; loại bỏ key None cho gọn payload
    metadata = {
        "magento_id": mg_customer.get("id"),
        "magento_group_id": mg_customer.get("group_id"),
        "magento_created_at": mg_customer.get("created_at"),
        "magento_updated_at": mg_customer.get("updated_at"),
    }
    payload["metadata"] = {k: v for k, v in metadata.items() if v is not None}

    # Magento thường có addresses; phone hay nằm trong địa chỉ.
    addresses = mg_customer.get("addresses") or []
    if addresses and isinstance(addresses, list):
        phone = addresses[0].get("telephone")
        if phone:
            payload["phone"] = phone

    return payload


