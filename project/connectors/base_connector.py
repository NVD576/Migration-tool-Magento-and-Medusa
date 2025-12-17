import requests
import time

class BaseConnector:
    def __init__(self, base_url, headers=None, max_retries=3, backoff_factor=1, verify_ssl=True):
        self.base_url = base_url.rstrip('/')
        self.headers = headers or {}
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.verify_ssl = verify_ssl

    def _request(self, method, endpoint, **kwargs):
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        for attempt in range(1, self.max_retries + 1):
            response = requests.request(method, url,verify=self.verify_ssl, headers=self.headers, **kwargs)
            if response.status_code == 429:
                wait = self.backoff_factor * attempt
                print(f"Rate limit hit. Retrying in {wait}s...")
                time.sleep(wait)
                continue
            response.raise_for_status()
            return response.json()
        raise Exception(f"Failed after {self.max_retries} attempts: {url}")

