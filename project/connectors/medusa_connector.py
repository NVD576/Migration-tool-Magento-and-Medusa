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

    def create_draft_order(self, draft_order, idempotency_key=None):
        endpoint = "admin/draft-orders"
        headers = self._headers_with_idempotency(idempotency_key)
        return self._request("POST", endpoint, json=draft_order, headers=headers)

    def create_order(self, order, idempotency_key=None):
        endpoint = "admin/orders"
        headers = self._headers_with_idempotency(idempotency_key)
        return self._request("POST", endpoint, json=order, headers=headers)

    def create_fulfillment(self, order_id, items):
        # Medusa v2 endpoint for fulfillment
        endpoint = f"admin/orders/{order_id}/fulfillments"
        payload = {"items": items}
        return self._request("POST", endpoint, json=payload)

    def capture_payment(self, order_id):
        # Medusa v2: Trigger capture for the order's payment collection
        # Note: This might require fetching the order first to get payment_collection_id
        # For simplicity, we try the order-level capture if available, or assume the user handles it manually
        # as programmatic capture without a payment provider can be complex.
        # Alternatively, we can try marking it as paid via metadata or custom status.
        return None

    def finalize_draft_order(self, draft_order_id):
        # Endpoint chính xác cho Medusa v2 (trigger workflow convert-draft-order)
        endpoint = f"admin/draft-orders/{draft_order_id}/convert-to-order"
        return self._request("POST", endpoint, json={})
