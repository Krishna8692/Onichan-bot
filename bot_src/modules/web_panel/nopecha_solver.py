import os
import asyncio
import httpx
import random

# Support multiple keys for rotation
NOPECHA_KEYS = [
    os.environ.get("NOPECHA_KEY", ""),
    os.environ.get("NOPECHA_KEY2", ""),
    os.environ.get("NOPECHA_KEY3", ""),
    os.environ.get("NOPECHA_KEY4", "")
]
# Filter out empty keys
NOPECHA_KEYS = [k for k in NOPECHA_KEYS if k]

# Rotation tracking
_current_key_index = 0

NOPECHA_TOKEN_URL = "https://api.nopecha.com/token"

def get_next_key():
    global _current_key_index
    if not NOPECHA_KEYS:
        return None
    key = NOPECHA_KEYS[_current_key_index]
    _current_key_index = (_current_key_index + 1) % len(NOPECHA_KEYS)
    return key

async def solve_turnstile(sitekey: str, url: str, proxy: dict = None) -> str:
    return await solve_captcha("turnstile", sitekey, url, proxy)

async def solve_recaptcha_v2(sitekey: str, url: str, proxy: dict = None) -> str:
    return await solve_captcha("recaptcha2", sitekey, url, proxy)

async def solve_hcaptcha(sitekey: str, url: str, proxy: dict = None) -> str:
    return await solve_captcha("hcaptcha", sitekey, url, proxy)

async def solve_captcha(captcha_type: str, sitekey: str, url: str, proxy: dict = None) -> str:
    """
    Generic CAPTCHA solver using NoPeCHA API.
    Supported types: 'turnstile', 'recaptcha2', 'hcaptcha'
    """
    api_key = get_next_key()
    if not api_key:
        print(f"[NoPeCHA] No API key configured - check NOPECHA_KEY environment variables")
        return None
    
    print(f"[NoPeCHA] Solving {captcha_type} for {url[:50]}...")
    
    try:
        payload = {
            "type": captcha_type,
            "sitekey": sitekey,
            "url": url,
            "key": api_key
        }
        
        if proxy:
            payload["proxy"] = proxy
        
        async with httpx.AsyncClient(timeout=60) as client:
            print(f"[NoPeCHA] Sending solve request...")
            response = await client.post(NOPECHA_TOKEN_URL, json=payload)
            result = response.json()
            
            if "error" in result:
                error_code = result.get("error")
                error_msg = result.get("message", "Unknown error")
                print(f"[NoPeCHA] API Error {error_code}: {error_msg}")
                return None
            
            job_id = result.get("data")
            if not job_id:
                print(f"[NoPeCHA] No job ID returned in response")
                return None
            
            print(f"[NoPeCHA] Job ID: {job_id}, polling for result...")
            
            # Poll for results with longer timeout
            for i in range(60):  # 30 seconds max
                await asyncio.sleep(0.5)
                poll_response = await client.get(
                    f"{NOPECHA_TOKEN_URL}?key={api_key}&id={job_id}"
                )
                poll_result = poll_response.json()
                
                if "error" in poll_result:
                    error_code = poll_result.get("error")
                    if error_code == 14:  # Incomplete job, keep polling
                        continue
                    print(f"[NoPeCHA] Poll error {error_code}: {poll_result.get('message', '')}")
                    return None
                
                token = poll_result.get("data")
                if token and isinstance(token, str) and len(token) > 10:
                    print(f"[NoPeCHA] Solved! Token length: {len(token)}")
                    return token
            
            print(f"[NoPeCHA] Timeout - no solution after 30s")
            return None
            
    except Exception as e:
        print(f"[NoPeCHA] Exception: {type(e).__name__}: {str(e)}")
        return None
