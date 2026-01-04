from .base_connector import BaseConnector

class MagentoConnector(BaseConnector):
    def __init__(self, base_url, token, verify_ssl=False):
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        super().__init__(base_url, headers, verify_ssl=verify_ssl)

    def get_products(self, page=1, page_size=100, ids=None, fields=None):
        endpoint = f"rest/V1/products?searchCriteria[currentPage]={page}&searchCriteria[pageSize]={page_size}"
        if ids:
            ids_val = ",".join(str(i) for i in ids)
            endpoint += f"&searchCriteria[filterGroups][0][filters][0][field]=entity_id" \
                        f"&searchCriteria[filterGroups][0][filters][0][value]={ids_val}" \
                        f"&searchCriteria[filterGroups][0][filters][0][condition_type]=in"
        
        if fields:
            endpoint += f"&fields={fields}"

        return self._request("GET", endpoint)

    def get_categories(self, page=1, page_size=100, fields=None):
        endpoint = f"rest/V1/categories/list?searchCriteria[currentPage]={page}&searchCriteria[pageSize]={page_size}"
        if fields:
            endpoint += f"&fields={fields}"
        return self._request("GET", endpoint)

    def get_category_tree(self, root_category_id=None, depth=None):
        endpoint = "rest/V1/categories"
        params = {}
        if root_category_id is not None:
            params["rootCategoryId"] = root_category_id
        if depth is not None:
            params["depth"] = depth
        return self._request("GET", endpoint, params=params or None)

    def get_customers(self, page=1, page_size=100):
        endpoint = f"rest/V1/customers/search?searchCriteria[currentPage]={page}&searchCriteria[pageSize]={page_size}"
        return self._request("GET", endpoint)

    def get_orders(self, page=1, page_size=50, updated_at_from=None):
        endpoint = f"rest/V1/orders?searchCriteria[currentPage]={page}&searchCriteria[pageSize]={page_size}"
        if updated_at_from:
            # Delta migration: filter by updated_at
            endpoint += f"&searchCriteria[filterGroups][0][filters][0][field]=updated_at" \
                        f"&searchCriteria[filterGroups][0][filters][0][value]={updated_at_from}" \
                        f"&searchCriteria[filterGroups][0][filters][0][condition_type]=gteq"
        return self._request("GET", endpoint)

    def get_order_invoices(self, order_id):
        """Lấy tất cả invoices của một order"""
        endpoint = f"rest/V1/orders/{order_id}/invoices"
        try:
            return self._request("GET", endpoint)
        except Exception:
            return {"items": []}

    def get_order_payments(self, order_id):
        """Lấy tất cả payments của một order"""
        endpoint = f"rest/V1/orders/{order_id}/payment"
        try:
            return self._request("GET", endpoint)
        except Exception:
            return {}

