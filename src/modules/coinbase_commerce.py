"""
================================================================================
  Coinbase Commerce Payment Gateway Integration
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

COINBASE_COMMERCE_API_URL = "https://api.commerce.coinbase.com"
COINBASE_COMMERCE_API_KEY = os.environ.get("COINBASE_COMMERCE_API_KEY", "")

CRYPTO_FILE = f"{DATABASE_DIR}/crypto_transactions.txt"
CRYPTO_PENDING = f"{DATABASE_DIR}/crypto_pending.txt"

SUPPORTED_CRYPTOS = {
    "BTC": {"name": "Bitcoin"},
    "ETH": {"name": "Ethereum"},
    "USDC": {"name": "USD Coin"},
    "DAI": {"name": "Dai"},
    "LTC": {"name": "Litecoin"},
    "BCH": {"name": "Bitcoin Cash"},
    "DOGE": {"name": "Dogecoin"},
    "SHIB": {"name": "Shiba Inu"}
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


def make_api_request(method: str, endpoint: str, data: dict = None) -> dict:
    """Make authenticated request to Coinbase Commerce API"""
    if not COINBASE_COMMERCE_API_KEY:
        return {"error": "Coinbase Commerce API key not configured"}
    
    url = COINBASE_COMMERCE_API_URL + endpoint
    
    headers = {
        'Content-Type': 'application/json',
        'X-CC-Api-Key': COINBASE_COMMERCE_API_KEY,
        'X-CC-Version': '2018-03-22'
    }
    
    try:
        if method == 'POST':
            response = requests.post(url, headers=headers, json=data, timeout=30)
        elif method == 'GET':
            response = requests.get(url, headers=headers, timeout=30)
        else:
            return {"error": f"Unsupported method: {method}"}
        
        print(f"[Coinbase] Status: {response.status_code}")
        print(f"[Coinbase] Response: {response.text[:500]}")
        
        if response.status_code == 401:
            return {"error": "Authentication failed - check your API Key"}
        
        if response.status_code not in [200, 201]:
            return {"error": f"API error ({response.status_code}): {response.text[:200]}"}
        
        return response.json()
        
    except requests.exceptions.RequestException as e:
        return {"error": f"Request failed: {str(e)}"}
    except json.JSONDecodeError:
        return {"error": f"Invalid response from Coinbase: {response.text[:200]}"}


def create_transaction(user_id: int, username: str, plan_key: str, crypto: str = "BTC", ipn_url: str = None):
    """Create a Coinbase Commerce charge for premium purchase"""
    if not COINBASE_COMMERCE_API_KEY:
        return {"error": "Coinbase Commerce API key not configured"}
    
    plan = PREMIUM_PLANS.get(plan_key)
    if not plan:
        return {"error": "Invalid plan"}
    
    order_id = f"ONICHAN-{user_id}-{plan_key}-{int(datetime.now().timestamp())}"
    
    charge_data = {
        "name": f"Onichan Bot - {plan['name']}",
        "description": f"Premium subscription for {plan['duration_days']} days",
        "pricing_type": "fixed_price",
        "local_price": {
            "amount": str(plan['price']),
            "currency": "USD"
        },
        "metadata": {
            "user_id": str(user_id),
            "username": username or "User",
            "plan_key": plan_key,
            "order_id": order_id
        }
    }
    
    if ipn_url:
        charge_data["redirect_url"] = ipn_url
    
    endpoint = "/charges"
    print(f"[Coinbase] Creating charge: {json.dumps(charge_data)}")
    result = make_api_request("POST", endpoint, charge_data)
    
    if "error" in result:
        return result
    
    data = result.get("data", result)
    charge_id = data.get("id", order_id)
    charge_code = data.get("code", "")
    hosted_url = data.get("hosted_url", "")
    
    save_pending_transaction(
        txn_id=charge_id,
        user_id=user_id,
        username=username,
        plan_key=plan_key,
        amount=plan['price'],
        crypto=crypto,
        address=hosted_url,
        crypto_amount=str(plan['price'])
    )
    
    return {
        "success": True,
        "txn_id": charge_id,
        "charge_code": charge_code,
        "order_id": order_id,
        "payment_url": hosted_url,
        "crypto": crypto,
        "crypto_name": SUPPORTED_CRYPTOS.get(crypto, {}).get("name", crypto),
        "plan": plan,
        "usd_amount": plan['price']
    }


def save_pending_transaction(txn_id, user_id, username, plan_key, amount, crypto, address, crypto_amount):
    """Save pending transaction to file"""
    init_crypto_files()
    record = f"{txn_id}|{user_id}|{username}|{plan_key}|{amount}|{crypto}|{address}|{crypto_amount}|{datetime.now()}|PENDING\n"
    with open(CRYPTO_PENDING, 'a', encoding='utf-8') as f:
        f.write(record)


def get_pending_transaction(txn_id):
    """Get pending transaction by txn_id"""
    init_crypto_files()
    try:
        with open(CRYPTO_PENDING, 'r', encoding='utf-8') as f:
            for line in f:
                parts = line.strip().split('|')
                if len(parts) >= 10 and parts[0] == txn_id:
                    return {
                        "txn_id": parts[0],
                        "user_id": int(parts[1]),
                        "username": parts[2],
                        "plan_key": parts[3],
                        "amount": parts[4],
                        "crypto": parts[5],
                        "address": parts[6],
                        "crypto_amount": parts[7],
                        "created_at": parts[8],
                        "status": parts[9]
                    }
    except Exception as e:
        print(f"Error reading pending transaction: {e}")
    return None


def get_pending_transactions_by_user(user_id):
    """Get all pending transactions for a user"""
    init_crypto_files()
    transactions = []
    try:
        with open(CRYPTO_PENDING, 'r', encoding='utf-8') as f:
            for line in f:
                parts = line.strip().split('|')
                if len(parts) >= 10 and parts[1] == str(user_id) and parts[9] == "PENDING":
                    transactions.append({
                        "txn_id": parts[0],
                        "user_id": int(parts[1]),
                        "username": parts[2],
                        "plan_key": parts[3],
                        "amount": parts[4],
                        "crypto": parts[5],
                        "address": parts[6],
                        "crypto_amount": parts[7],
                        "created_at": parts[8],
                        "status": parts[9]
                    })
    except Exception as e:
        print(f"Error reading pending transactions: {e}")
    return transactions


def check_charge_status(charge_id: str) -> dict:
    """Check the status of a charge"""
    if not COINBASE_COMMERCE_API_KEY:
        return {"error": "Coinbase Commerce API key not configured"}
    
    endpoint = f"/charges/{charge_id}"
    result = make_api_request("GET", endpoint)
    
    if "error" in result:
        return result
    
    data = result.get("data", result)
    
    timeline = data.get("timeline", [])
    payments = data.get("payments", [])
    
    status = "PENDING"
    if timeline:
        last_event = timeline[-1].get("status", "").upper()
        if last_event in ["COMPLETED", "RESOLVED"]:
            status = "CONFIRMED"
        elif last_event == "EXPIRED":
            status = "EXPIRED"
        elif last_event == "CANCELED":
            status = "CANCELED"
        elif last_event in ["PENDING", "UNRESOLVED"]:
            status = "PENDING"
    
    if payments:
        for payment in payments:
            if payment.get("status") == "CONFIRMED":
                status = "CONFIRMED"
                break
    
    return {
        "charge_id": charge_id,
        "status": status,
        "timeline": timeline,
        "payments": payments,
        "metadata": data.get("metadata", {})
    }


def update_transaction_status(txn_id, new_status):
    """Update transaction status in pending file"""
    init_crypto_files()
    try:
        with open(CRYPTO_PENDING, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        with open(CRYPTO_PENDING, 'w', encoding='utf-8') as f:
            for line in lines:
                parts = line.strip().split('|')
                if len(parts) >= 10 and parts[0] == txn_id:
                    parts[9] = new_status
                    f.write('|'.join(parts) + '\n')
                else:
                    f.write(line)
        return True
    except Exception as e:
        print(f"Error updating transaction status: {e}")
        return False


def complete_transaction(txn_id, user_id, plan_key):
    """Mark transaction as complete and record it"""
    init_crypto_files()
    
    update_transaction_status(txn_id, "CONFIRMED")
    
    plan = PREMIUM_PLANS.get(plan_key)
    if plan:
        record = f"{txn_id}|{user_id}|{plan_key}|{plan['price']}|{datetime.now()}|CONFIRMED\n"
        with open(CRYPTO_FILE, 'a', encoding='utf-8') as f:
            f.write(record)
    
    return True


def verify_webhook_signature(payload: bytes, signature: str, shared_secret: str) -> bool:
    """Verify Coinbase Commerce webhook signature"""
    import hmac
    import hashlib
    
    expected_sig = hmac.new(
        shared_secret.encode('utf-8'),
        payload,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(expected_sig, signature)


def process_webhook(payload: dict, signature: str = None) -> dict:
    """Process Coinbase Commerce webhook event"""
    event_type = payload.get("event", {}).get("type", "")
    event_data = payload.get("event", {}).get("data", {})
    
    print(f"[Coinbase Webhook] Event type: {event_type}")
    
    if event_type == "charge:confirmed":
        metadata = event_data.get("metadata", {})
        user_id = metadata.get("user_id")
        plan_key = metadata.get("plan_key")
        charge_id = event_data.get("id")
        
        if user_id and plan_key:
            complete_transaction(charge_id, int(user_id), plan_key)
            return {
                "success": True,
                "action": "premium_activated",
                "user_id": int(user_id),
                "plan_key": plan_key
            }
    
    elif event_type == "charge:pending":
        return {"success": True, "action": "payment_pending"}
    
    elif event_type == "charge:failed":
        return {"success": True, "action": "payment_failed"}
    
    return {"success": True, "action": "no_action"}


def get_premium_plans():
    """Return available premium plans"""
    return PREMIUM_PLANS


def get_supported_cryptos():
    """Return supported cryptocurrencies"""
    return SUPPORTED_CRYPTOS
