"""
Website Analysis Tool - Gateway Detection & Security Analysis
================================================================================
"""

import re
import time
import requests
import cloudscraper

VBV_KEYWORDS = ['3D-Secure', 'threeDSecureInfo', 'VBV', '3DSecure', '3D Secure']
AUTH_PATHS = ['/my-account', '/account', '/login', '/signin']
CHECKOUT_PAGES = ['/checkout', '/payment', '/pay', '/purchase', '/order', '/buy']

GATEWAYS = {
    "paypal": "PayPal",
    "stripe": "Stripe",
    "braintree": "Braintree",
    "square": "Square",
    "cybersource": "Cybersource",
    "authorize.net": "Authorize.Net",
    "2checkout": "2Checkout",
    "adyen": "Adyen",
    "worldpay": "Worldpay",
    "sagepay": "SagePay",
    "checkout.com": "Checkout.com",
    "shopify": "Shopify",
    "razorpay": "Razorpay",
    "bolt": "Bolt",
    "paytm": "Paytm",
    "venmo": "Venmo",
    "pay.google.com": "Google Pay",
    "revolut": "Revolut",
    "eway": "Eway",
    "woocommerce": "Woocommerce",
    "upi": "UPI",
    "apple.com": "Apple Pay",
    "payflow": "PayFlow",
    "payeezy": "Payeezy",
    "paddle": "Paddle",
    "payoneer": "Payoneer",
    "recurly": "Recurly",
    "klarna": "Klarna",
    "paysafe": "Paysafe",
    "webmoney": "WebMoney",
    "payeer": "Payeer",
    "payu": "Payu",
    "skrill": "Skrill"
}

def find_payment_gateways(response_text):
    """Detect payment gateways from HTML content"""
    detected_gateways = []
    
    for key, value in GATEWAYS.items():
        if key in response_text.lower():
            detected_gateways.append(value)
    
    if not detected_gateways:
        detected_gateways.append("Unknown")
    
    return detected_gateways

def analyze_website(url, user_name=None, user_id=None):
    """
    Analyze a website for payment gateways and security features
    Returns formatted result string
    """
    start_time = time.time()
    
    try:
        domain = url.replace('https://', '').replace('http://', '').split('/')[0].strip()
        
        if not domain:
            return "❌ Invalid URL provided"
        
        scraper = cloudscraper.create_scraper()
        
        try:
            response = scraper.get(f"https://{domain}", timeout=15)
        except:
            response = scraper.get(f"http://{domain}", timeout=15)
        
        html_content = response.text
        
        captcha = any(term in html_content.lower() for term in ['captcha', 'recaptcha', "i'm not a robot", 'hcaptcha'])
        cloudflare = any(term in html_content for term in ["Cloudflare", "cdnjs.cloudflare.com", "__cf_bm"])
        
        vbv_detected = any(re.search(keyword, html_content, re.IGNORECASE) for keyword in VBV_KEYWORDS)
        
        auth_detected = False
        for path in AUTH_PATHS:
            try:
                auth_response = requests.get(f"https://{domain}{path}", timeout=5)
                if auth_response.status_code == 200:
                    auth_detected = True
                    break
            except:
                continue
        
        checkout_detected = False
        for path in CHECKOUT_PAGES:
            try:
                checkout_response = requests.get(f"https://{domain}{path}", timeout=5)
                if checkout_response.status_code == 200:
                    checkout_detected = True
                    break
            except:
                continue
        
        gateways = find_payment_gateways(html_content)
        gateways_text = ', '.join(gateways) if gateways else 'Unknown'
        
        time_taken = round(time.time() - start_time, 2)
        
        checked_by = ""
        if user_name and user_id:
            checked_by = f"\n┃ Checked by: @{user_name}"
        
        result = f"""┏━━━━━━━⍟
┃ <b>Website Analysis</b> ✅
┗━━━━━━━━━━━━⊛
┏━━━━━━━⍟
┃ Site ➜ <code>{domain}</code>
┃ Gateways ➜ {gateways_text}
┃ Security:
┃   ❁ Captcha ➜ {'✅' if captcha else '❌'}
┃   ❁ Cloudflare ➜ {'✅' if cloudflare else '❌'}
┃   ❁ Login/Auth ➜ {'✅' if auth_detected else '❌'}
┃   ❁ Checkout ➜ {'✅' if checkout_detected else '❌'}
┃   ❁ VBV/3DS ➜ {'✅' if vbv_detected else '❌'}
┗━━━━━━━━━━━━⊛
┏━━━━━━━⍟
┃ Time ➜ {time_taken}s{checked_by}
┃ Bot ➜ @Onichanbabybot
┗━━━━━━━━━━━━⊛"""
        
        return result
    
    except requests.exceptions.Timeout:
        return f"❌ Timeout: Website took too long to respond"
    except requests.exceptions.ConnectionError:
        return f"❌ Connection Error: Could not connect to website"
    except Exception as e:
        return f"❌ Error: {str(e)[:100]}"
