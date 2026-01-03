import requests
def get_magento_token(base_url, username, password, verify_ssl=False, logger=print):
    url = f"{base_url}/rest/V1/integration/admin/token"
    
    logger(f"🔐 [PROCESS] Requesting token from Magento...\n")
    logger(f"   - Target URL: {url}\n")
    
    try:
        response = requests.post(
            url,
            headers={"Content-Type": "application/json"},
            json={
                "username": username,
                "password": password
            },
            verify=verify_ssl,
            timeout=15
        )
        response.raise_for_status()
        token = response.json()
        
        preview = f"{token[:6]}...{token[-6:]}" if len(token) > 12 else "***"
        logger(f"✅ [SUCCESS] Magento login successful!\n")
        logger(f"   - Token received: {preview}\n\n")
        return token
        
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code
        logger(f"❌ [FAIL] Magento response error (HTTP {status}).\n")
        if status == 401:
            logger(f"   - Reason: Invalid Username or Password.\n")
        elif status == 404:
            logger(f"   - Reason: API URL not found. Please check Base URL.\n")
        raise e
    except Exception as e:
        logger(f"❌ [FAIL] Unexpected error during Magento login.\n")
        logger(f"   - Details: {str(e)}\n")
        raise e

