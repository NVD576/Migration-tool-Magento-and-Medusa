def extract_products(magento_connector, ids=None):
    page = 1
    all_products = []
    while True:
        result = magento_connector.get_products(page=page, ids=ids)
        items = result.get('items', [])
        if not items:
            break
        all_products.extend(items)
        page += 1
    return all_products

