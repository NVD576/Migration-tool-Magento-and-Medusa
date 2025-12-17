from .base_connector import BaseConnector

class MedusaConnector(BaseConnector):
    def __init__(self, base_url, api_token):
        headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json"
        }
        super().__init__(base_url, headers)

    def create_product(self, product):
        endpoint = "admin/products"
        return self._request("POST", endpoint, json=product)

    def create_customer(self, customer):
        endpoint = "admin/customers"
        return self._request("POST", endpoint, json=customer)

    def create_product_category(self, category):
        endpoint = "admin/product-categories"
        return self._request("POST", endpoint, json=category)

    def list_product_categories(self, limit=50, offset=0):
        endpoint = "admin/product-categories"
        return self._request("GET", endpoint, params={"limit": limit, "offset": offset})

    def create_collection(self, collection):
        endpoint = "admin/collections"
        return self._request("POST", endpoint, json=collection)

    def get_regions(self):
        endpoint = "admin/regions"
        return self._request("GET", endpoint)

    def create_draft_order(self, draft_order):
        endpoint = "admin/draft-orders"
        return self._request("POST", endpoint, json=draft_order)

