def extract_orders(magento_connector, updated_at_from=None):
    """
    Extract orders from Magento
    Args:
        magento_connector: MagentoConnector instance
        updated_at_from: Optional datetime string for delta migration (format: YYYY-MM-DD HH:mm:ss)
    """
    page = 1
    all_orders = []

    while True:
        result = magento_connector.get_orders(page=page, updated_at_from=updated_at_from)
        items = result.get("items", [])
        if not items:
            break
        all_orders.extend(items)
        page += 1

    return all_orders


def extract_order_invoices(magento_connector, order_id):
    """Extract invoices for a specific order"""
    result = magento_connector.get_order_invoices(order_id)
    return result.get("items", [])


def extract_order_payments(magento_connector, order_id):
    """Extract payment information for a specific order"""
    result = magento_connector.get_order_payments(order_id)
    # Magento payment API có thể trả về object hoặc array
    if isinstance(result, list):
        return result
    elif isinstance(result, dict):
        return [result] if result else []
    return []


