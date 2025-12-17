import requests


def get_magento_token(base_url, username, password, verify_ssl=False):
    response = requests.post(
        f"{base_url}/rest/V1/integration/admin/token",
        headers={"Content-Type": "application/json"},
        json={
            "username": username,
            "password": password
        },
        verify=verify_ssl
    )

    response.raise_for_status()
    return response.json()

