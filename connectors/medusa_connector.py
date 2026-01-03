import requests
from .base_connector import BaseConnector

class MedusaConnector(BaseConnector):
    def __init__(self, base_url, api_token):
        headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json"
        }
        super().__init__(base_url, headers)

    def _headers_with_idempotency(self, idempotency_key=None):
        if not idempotency_key:
            return None
        h = dict(self.headers)
        h["Idempotency-Key"] = str(idempotency_key)
        return h

    def create_product(self, product, idempotency_key=None):
        endpoint = "admin/products"
        headers = self._headers_with_idempotency(idempotency_key)
        return self._request("POST", endpoint, json=product, headers=headers)

    def create_customer(self, customer, idempotency_key=None):
        endpoint = "admin/customers"
        headers = self._headers_with_idempotency(idempotency_key)
        return self._request("POST", endpoint, json=customer, headers=headers)

    def create_product_category(self, category, idempotency_key=None):
        endpoint = "admin/product-categories"
        headers = self._headers_with_idempotency(idempotency_key)
        return self._request("POST", endpoint, json=category, headers=headers)

    def list_product_categories(self, limit=50, offset=0):
        endpoint = "admin/product-categories"
        return self._request("GET", endpoint, params={"limit": limit, "offset": offset})

    def create_collection(self, collection):
        endpoint = "admin/collections"
        return self._request("POST", endpoint, json=collection)

    def get_regions(self):
        endpoint = "admin/regions"
        return self._request("GET", endpoint)

    def list_products(self, limit=50, offset=0, expand=None, fields=None):
        endpoint = "admin/products"
        params = {"limit": limit, "offset": offset}
        if expand:
            params["expand"] = expand
        if fields:
            params["fields"] = fields
        return self._request("GET", endpoint, params=params)

    def list_shipping_options(self, limit=50, offset=0):
        endpoint = "admin/shipping-options"
        params = {"limit": limit, "offset": offset}
        return self._request("GET", endpoint, params=params)

    def get_sales_channels(self, limit=50, offset=0):
        endpoint = "admin/sales-channels"
        params = {"limit": limit, "offset": offset}
        return self._request("GET", endpoint, params=params)

    def get_shipping_profiles(self, limit=50, offset=0):
        endpoint = "admin/shipping-profiles"
        params = {"limit": limit, "offset": offset}
        return self._request("GET", endpoint, params=params)

    def create_draft_order(self, draft_order, idempotency_key=None):
        endpoint = "admin/draft-orders"
        headers = self._headers_with_idempotency(idempotency_key)
        return self._request("POST", endpoint, json=draft_order, headers=headers)

    def create_order(self, order, idempotency_key=None):
        endpoint = "admin/orders"
        headers = self._headers_with_idempotency(idempotency_key)
        return self._request("POST", endpoint, json=order, headers=headers)

    def create_fulfillment(self, order_id, items):
        endpoint = f"admin/orders/{order_id}/fulfillments"
        payload = {"items": items}
        return self._request("POST", endpoint, json=payload)

    def capture_payment(self, order_id):
        return None

    def finalize_draft_order(self, draft_order_id):
        endpoint = f"admin/draft-orders/{draft_order_id}/convert-to-order"
        return self._request("POST", endpoint, json={})
    def create_customer_address(self, customer_id, address):
        endpoint = f"admin/customers/{customer_id}/addresses"
        return self._request("POST", endpoint, json=address)
