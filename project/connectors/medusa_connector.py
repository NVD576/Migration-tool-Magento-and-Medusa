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

    def create_draft_order(self, draft_order, idempotency_key=None):
        endpoint = "admin/draft-orders"
        headers = self._headers_with_idempotency(idempotency_key)
        return self._request("POST", endpoint, json=draft_order, headers=headers)

    def finalize_draft_order(self, draft_order_id):
        """
        Thử chuyển Draft Order -> Order theo nhiều route tuỳ version Medusa.
        Trả về JSON response nếu thành công, hoặc None nếu không có route nào hỗ trợ.
        """
        candidates = [
            # Medusa (một số version UI dùng route này)
            f"admin/draft-orders/{draft_order_id}/convert-to-order",
            f"admin/draft-orders/{draft_order_id}/confirm",
            f"admin/draft-orders/{draft_order_id}/complete",
            f"admin/draft-orders/{draft_order_id}/pay",
            f"admin/draft-orders/{draft_order_id}/mark-paid",
        ]

        last_err = None
        for endpoint in candidates:
            try:
                return self._request("POST", endpoint, json={})
            except requests.exceptions.HTTPError as e:
                resp = getattr(e, "response", None)
                status = resp.status_code if resp is not None else None
                # 404/405: route không tồn tại / method không cho phép => thử route khác
                if status in (404, 405):
                    last_err = e
                    continue
                raise

        # Không route nào support
        _ = last_err
        return None

