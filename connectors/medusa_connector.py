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
    
    def delete_draft_order(self, draft_order_id):
        """Delete a draft order"""
        endpoint = f"admin/draft-orders/{draft_order_id}"
        return self._request("DELETE", endpoint)
    
    def create_customer_address(self, customer_id, address):
        endpoint = f"admin/customers/{customer_id}/addresses"
        return self._request("POST", endpoint, json=address)

    def create_inventory_item(self, data):
        endpoint = "admin/inventory-items"
        return self._request("POST", endpoint, json=data)

    def list_inventory_items(self, params=None):
        endpoint = "admin/inventory-items"
        return self._request("GET", endpoint, params=params)

    def get_inventory_item_by_sku(self, sku):
        if not sku:
            return None
        res = self.list_inventory_items(params={"sku": sku})
        items = res.get("inventory_items", []) or res.get("data", [])
        if items:
            return items[0]
        return None

    def add_inventory_item_location_level(self, inventory_item_id, location_id, quantity):
        endpoint = f"admin/inventory-items/{inventory_item_id}/location-levels/batch"
        payload = {
            "create": [
                {
                    "location_id": location_id,
                    "stocked_quantity": quantity
                }
            ]
        }
        return self._request("POST", endpoint, json=payload)

    def link_variant_to_inventory_item(self, product_id, variant_id, inventory_item_id, quantity=1):
        # Medusa v2 uses a batch endpoint for product variants inventory items
        endpoint = f"admin/products/{product_id}/variants/inventory-items/batch"
        payload = {
            "create": [
                {
                    "variant_id": variant_id,
                    "inventory_item_id": inventory_item_id,
                    "required_quantity": quantity
                }
            ]
        }
        return self._request("POST", endpoint, json=payload)

    def get_stock_locations(self, limit=50, offset=0):
        endpoint = "admin/stock-locations"
        params = {"limit": limit, "offset": offset}
        return self._request("GET", endpoint, params=params)
