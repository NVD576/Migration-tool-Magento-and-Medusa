def extract_customers(magento_connector):
    page = 1
    all_customers = []

    while True:
        result = magento_connector.get_customers(page=page)
        items = result.get("items", [])
        if not items:
            break
        all_customers.extend(items)
        page += 1

    return all_customers


