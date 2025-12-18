from .base_connector import BaseConnector

class MagentoConnector(BaseConnector):
    def __init__(self, base_url, token, verify_ssl=False):
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        super().__init__(base_url, headers, verify_ssl=verify_ssl)

    def get_products(self, page=1, page_size=20):
        endpoint = f"rest/V1/products?searchCriteria[currentPage]={page}&searchCriteria[pageSize]={page_size}"
        return self._request("GET", endpoint)

    def get_categories(self, page=1, page_size=100):
        endpoint = f"rest/V1/categories/list?searchCriteria[currentPage]={page}&searchCriteria[pageSize]={page_size}"
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

    def get_orders(self, page=1, page_size=50):
        endpoint = f"rest/V1/orders?searchCriteria[currentPage]={page}&searchCriteria[pageSize]={page_size}"
        return self._request("GET", endpoint)

