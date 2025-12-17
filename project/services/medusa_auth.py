import requests
def get_medusa_token(base_url, email, password):
    response = requests.post(
        f"{base_url}/auth/user/emailpass",
        json={
            "email": email,
            "password": password
        }
    )

    response.raise_for_status()
    return response.json()["token"]

