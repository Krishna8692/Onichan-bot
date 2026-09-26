"""
================================================================================
  OxaPay Crypto Payment Gateway Integration
  Handles cryptocurrency payments and auto-confirms premium subscriptions
================================================================================
"""

import os
import sys
import json
import requests
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DB_PREMIUM, DB_INVOICES, DB_PAYMENTS, DATABASE_DIR

OXAPAY_API_URL = "https://api.oxapay.com/v1/payment/invoice"
OXAPAY_API_KEY = os.environ.get("OXAPAY_API_KEY", "")

CRYPTO_FILE = f"{DATABASE_DIR}/crypto_transactions.txt"
CRYPTO_PENDING = f"{DATABASE_DIR}/crypto_pending.txt"

SUPPORTED_CRYPTOS = {
    "BTC": {"name": "Bitcoin"},
    "ETH": {"name": "Ethereum"},
    "USDT": {"name": "Tether USD"},
    "TRX": {"name": "Tron"},
    "LTC": {"name": "Litecoin"},
    "DOGE": {"name": "Dogecoin"},
    "BNB": {"name": "Binance Coin"},
    "SOL": {"name": "Solana"},
    "XRP": {"name": "Ripple"},
    "TON": {"name": "Toncoin"}
}

PREMIUM_PLANS = {
    "1_week": {"name": "1 Week Premium", "duration_days": 7, "price": 3},
    "2_weeks": {"name": "2 Weeks Premium", "duration_days": 14, "price": 5},
    "1_month": {"name": "1 Month Premium", "duration_days": 30, "price": 10},
    "3_months": {"name": "3 Months Premium", "duration_days": 90, "price": 25}
}


def init_crypto_files():
    """Initialize crypto transaction files"""
    os.makedirs(DATABASE_DIR, exist_ok=True)
    for f in [CRYPTO_FILE, CRYPTO_PENDING]:
        if not os.path.exists(f):
            with open(f, 'w', encoding='utf-8') as file:
                pass


def create_invoice(user_id: int, username: str, plan_key: str, crypto: str = "USDT", callback_url: str = None, return_url: str = None):
    """Create an OxaPay invoice for premium purchase"""
    if not OXAPAY_API_KEY:
        return {"error": "OxaPay API key not configured. Set OXAPAY_API_KEY in secrets."}
    
    plan = PREMIUM_PLANS.get(plan_key)
    if not plan:
        return {"error": "Invalid plan"}
    
    order_id = f"ONICHAN-{user_id}-{plan_key}-{int(datetime.now().timestamp())}"
    
    headers = {
        'merchant_api_key': OXAPAY_API_KEY,
        'Content-Type': 'application/json'
    }
    
    invoice_data = {
        "amount": plan['price'],
        "currency": "USD",
        "lifetime": 60,
        "fee_paid_by_payer": 1,
        "under_paid_coverage": 2.5,
        "to_currency": crypto,
        "order_id": order_id,
        "description": f"Onichan Bot - {plan['name']} for @{username}",
        "thanks_message": f"Thank you for purchasing {plan['name']}! Your premium will be activated shortly.",
        "sandbox": False
    }
    
    if callback_url:
        invoice_data["callback_url"] = callback_url
    if return_url:
        invoice_data["return_url"] = return_url
    
    try:
        response = requests.post(OXAPAY_API_URL, json=invoice_data, headers=headers, timeout=30)
        
        print(f"[OxaPay] Status: {response.status_code}")
        print(f"[OxaPay] Response: {response.text[:500]}")
        
        if response.status_code != 200:
            return {"error": f"API error ({response.status_code}): {response.text[:200]}"}
        
        result = response.json()
        
        api_status = result.get("status")
        data = result.get("data", {})
        
        if api_status == 200 and data:
            track_id = data.get("track_id")
            payment_url = data.get("payment_url")
        elif result.get("result") == 100:
            track_id = result.get("trackId") or result.get("track_id")
            payment_url = result.get("payLink") or result.get("payment_url")
        else:
            return {"error": result.get("message", "Unknown error")}
        
        init_crypto_files()
        
        pending_data = {
            "order_id": order_id,
            "user_id": user_id,
            "username": username,
            "plan_key": plan_key,
            "plan_name": plan['name'],
            "amount": plan['price'],
            "crypto": crypto,
            "track_id": track_id,
            "payment_url": payment_url,
            "created_at": datetime.now().isoformat(),
            "status": "pending"
        }
        
        with open(CRYPTO_PENDING, 'a', encoding='utf-8') as f:
            f.write(json.dumps(pending_data) + "\n")
        
        return {
            "success": True,
            "order_id": order_id,
            "track_id": track_id,
            "payment_url": payment_url,
            "amount": plan['price'],
            "crypto": crypto,
            "plan": plan
        }
        
    except requests.exceptions.RequestException as e:
        return {"error": f"Request failed: {str(e)}"}
    except json.JSONDecodeError:
        return {"error": f"Invalid response from OxaPay"}


def check_payment_status(track_id: str):
    """Check the status of an OxaPay payment"""
    if not OXAPAY_API_KEY:
        return {"error": "OxaPay API key not configured"}
    
    url = "https://api.oxapay.com/v1/payment/inquiry"
    
    headers = {
        'merchant_api_key': OXAPAY_API_KEY,
        'Content-Type': 'application/json'
    }
    
    try:
        response = requests.post(url, json={"trackId": track_id}, headers=headers, timeout=30)
        
        print(f"[OxaPay] Inquiry status: {response.status_code}")
        print(f"[OxaPay] Inquiry response: {response.text[:500]}")
        
        if response.status_code != 200:
            return {"error": f"API error: {response.status_code}"}
        
        result = response.json()
        
        data = result.get("data", {})
        if data and isinstance(data, dict):
            return data
        
        return result
        
    except Exception as e:
        return {"error": str(e)}


def get_pending_payments(user_id=None):
    """Get pending crypto payments, optionally filtered by user_id"""
    init_crypto_files()
    pending = []
    
    try:
        with open(CRYPTO_PENDING, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        data = json.loads(line)
                        if user_id is not None:
                            if str(data.get("user_id", "")) == str(user_id):
                                pending.append(data)
                        else:
                            pending.append(data)
                    except:
                        pass
    except:
        pass
    
    return pending


def confirm_payment(order_id: str, user_id: int = None, plan_key: str = None):
    """Confirm a crypto payment and activate premium"""
    init_crypto_files()
    
    pending = get_pending_payments()
    found = None
    
    for p in pending:
        if p.get("order_id") == order_id or p.get("track_id") == order_id:
            found = p
            break
    
    if not found:
        return {"error": "Payment not found"}
    
    with open(CRYPTO_FILE, 'a', encoding='utf-8') as f:
        found['status'] = 'confirmed'
        found['confirmed_at'] = datetime.now().isoformat()
        f.write(json.dumps(found) + "\n")
    
    match_id = found.get("order_id")
    remaining = [p for p in pending if p.get("order_id") != match_id]
    with open(CRYPTO_PENDING, 'w', encoding='utf-8') as f:
        for p in remaining:
            f.write(json.dumps(p) + "\n")
    
    return {
        "success": True,
        "user_id": found.get("user_id"),
        "username": found.get("username"),
        "plan_key": found.get("plan_key"),
        "plan_name": found.get("plan_name")
    }


def activate_premium(user_id: int, plan_key: str, username: str = "User", payment_method: str = "Crypto"):
    """Activate premium for a user after confirmed payment"""
    plan = PREMIUM_PLANS.get(plan_key)
    if not plan:
        return {"error": "Invalid plan"}
    
    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from modules.database import set_premium_sync, add_user_sync
        
        try:
            add_user_sync(int(user_id), username, "approved")
        except:
            pass
        
        set_premium_sync(int(user_id), plan['duration_days'])
        
        try:
            with open(DB_PREMIUM, 'a') as f:
                if str(user_id) not in open(DB_PREMIUM, 'r').read():
                    f.write(f"{user_id}\n")
        except:
            pass
        
        from modules.premium_plans import generate_invoice
        try:
            generate_invoice(str(user_id), username, plan_key, payment_method)
        except:
            pass
        
        print(f"[OxaPay] Premium activated for user {user_id} - {plan['name']} via {payment_method}")
        
        return {
            "success": True,
            "user_id": user_id,
            "username": username,
            "plan_key": plan_key,
            "plan_name": plan['name'],
            "days": plan['duration_days']
        }
    except Exception as e:
        print(f"[OxaPay] Error activating premium for {user_id}: {e}")
        return {"error": str(e)}


def get_crypto_transactions():
    """Get all confirmed crypto transactions"""
    init_crypto_files()
    transactions = []
    
    try:
        with open(CRYPTO_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        transactions.append(json.loads(line))
                    except:
                        pass
    except:
        pass
    
    return transactions


def format_payment_message(result: dict) -> str:
    """Format payment info for Telegram message"""
    if result.get("error"):
        return f"❌ <b>Error:</b> {result['error']}"
    
    plan = result.get("plan", {})
    
    return f"""
🎀 <b>ONICHAN BOT - CRYPTO PAYMENT</b>

━━━━━━━━━━━━━━━━━━━━━━

📦 <b>Plan:</b> {plan.get('name', 'N/A')}
💰 <b>Amount:</b> ${result.get('amount', 0)} USD
💎 <b>Crypto:</b> {result.get('crypto', 'USDT')}
⏰ <b>Duration:</b> {plan.get('duration_days', 0)} days

━━━━━━━━━━━━━━━━━━━━━━

🔗 <b>Payment Link:</b>
<a href="{result.get('payment_url', '#')}">Click Here to Pay</a>

📋 <b>Order ID:</b> <code>{result.get('order_id', 'N/A')}</code>
🔍 <b>Track ID:</b> <code>{result.get('track_id', 'N/A')}</code>

━━━━━━━━━━━━━━━━━━━━━━

⚠️ <b>Note:</b> Payment link expires in 60 minutes.
After payment, your premium will be activated automatically!
"""


def format_crypto_list() -> str:
    """Format supported cryptocurrencies for display"""
    crypto_list = "\n".join([f"• <code>{code}</code> - {info['name']}" for code, info in SUPPORTED_CRYPTOS.items()])
    return f"""
💎 <b>Supported Cryptocurrencies:</b>

{crypto_list}

Use: /buycrypto [plan] [crypto]
Example: /buycrypto 1_month USDT
"""
