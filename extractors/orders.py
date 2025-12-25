def extract_orders(magento_connector):
    page = 1
    all_orders = []

    while True:
        result = magento_connector.get_orders(page=page)
        items = result.get("items", [])
        if not items:
            break
        all_orders.extend(items)
        page += 1

    return all_orders


