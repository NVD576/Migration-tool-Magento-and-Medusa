import requests
def get_medusa_token(base_url, email, password, logger=print):
    url = f"{base_url}/auth/user/emailpass"
    
    logger(f"🔐 [PROCESS] Requesting token from Medusa...\n")
    logger(f"   - Target URL: {url}\n")
    
    try:
        response = requests.post(
            url,
            json={
                "email": email,
                "password": password
            },
            timeout=15
        )
        response.raise_for_status()
        token = response.json().get("token")
        
        if not token:
            raise Exception("Success response but 'token' field not found")
            
        preview = f"{token[:6]}...{token[-6:]}" if len(token) > 12 else "***"
        logger(f"✅ [SUCCESS] Medusa login successful!\n")
        logger(f"   - Token received: {preview}\n\n")
        return token
        
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code
        logger(f"❌ [FAIL] Medusa response error (HTTP {status}).\n")
        if status == 401:
            logger(f"   - Reason: Incorrect email or password.\n")
        raise e
    except Exception as e:
        logger(f"❌ [FAIL] Unexpected error during Medusa login.\n")
        logger(f"   - Details: {str(e)}\n")
        raise e

