"""
================================================================================
  CoinPayments Payment Gateway Integration (v2 API)
  Handles cryptocurrency payments and auto-confirms premium subscriptions
================================================================================
"""

import os
import sys
import hmac
import hashlib
import base64
import json
import requests
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DB_PREMIUM, DB_INVOICES, DB_PAYMENTS, DATABASE_DIR

COINPAYMENTS_API_URL = "https://a-api.coinpayments.net/api/v2"

COINPAYMENTS_CLIENT_ID = os.environ.get("COINPAYMENTS_CLIENT_ID", "")
COINPAYMENTS_CLIENT_SECRET = os.environ.get("COINPAYMENTS_CLIENT_SECRET", "")
COINPAYMENTS_MERCHANT_ID = os.environ.get("COINPAYMENTS_MERCHANT_ID", "")

CRYPTO_FILE = f"{DATABASE_DIR}/crypto_transactions.txt"
CRYPTO_PENDING = f"{DATABASE_DIR}/crypto_pending.txt"

SUPPORTED_CRYPTOS = {
    "BTC": {"name": "Bitcoin", "id": "1"},
    "LTC": {"name": "Litecoin", "id": "2"},
    "ETH": {"name": "Ethereum", "id": "60"},
    "USDT.TRC20": {"name": "USDT (TRC20)", "id": "5759"},
    "USDT.ERC20": {"name": "USDT (ERC20)", "id": "136"},
    "DOGE": {"name": "Dogecoin", "id": "3"},
    "TRX": {"name": "Tron", "id": "1958"},
    "XRP": {"name": "Ripple", "id": "144"},
    "BNB.BSC": {"name": "BNB (BSC)", "id": "5805"},
    "SOL": {"name": "Solana", "id": "7565"}
}

USD_CURRENCY_ID = "5057"

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
    """Make authenticated request to CoinPayments API v2 using HMAC signature"""
    if not COINPAYMENTS_CLIENT_ID or not COINPAYMENTS_CLIENT_SECRET:
        return {"error": "CoinPayments API credentials not configured"}
    
    url = COINPAYMENTS_API_URL + endpoint
    
    # ISO-8601 format: YYYY-MM-DDTHH:mm:ss (excluding milliseconds and timezone)
    iso_date = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S')
    
    # Convert payload to JSON string (empty string if no data)
    payload_message = json.dumps(data) if data else ''
    
    # Construct unique request message per official docs:
    # BOM + METHOD + URL + CLIENT_ID + TIMESTAMP + PAYLOAD
    message = f"\ufeff{method}{url}{COINPAYMENTS_CLIENT_ID}{iso_date}{payload_message}"
    
    # Generate HMAC-SHA256 signature in Base64
    signature = base64.b64encode(
        hmac.new(
            COINPAYMENTS_CLIENT_SECRET.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).digest()
    ).decode('utf-8')
    
    headers = {
        'Content-Type': 'application/json',
        'X-CoinPayments-Client': COINPAYMENTS_CLIENT_ID,
        'X-CoinPayments-Timestamp': iso_date,
        'X-CoinPayments-Signature': signature
    }
    
    print(f"[CoinPayments] URL: {url}")
    print(f"[CoinPayments] Timestamp: {iso_date}")
    print(f"[CoinPayments] Payload: {payload_message}")
    
    try:
        if method == 'POST':
            response = requests.post(url, headers=headers, data=payload_message, timeout=30)
        elif method == 'GET':
            response = requests.get(url, headers=headers, timeout=30)
        else:
            return {"error": f"Unsupported method: {method}"}
        
        print(f"[CoinPayments] Status: {response.status_code}")
        print(f"[CoinPayments] Response: {response.text[:500]}")
        
        if response.status_code == 401:
            return {"error": "Authentication failed - check your Client ID and Secret"}
        
        if response.status_code != 200:
            return {"error": f"API error ({response.status_code}): {response.text[:200]}"}
        
        return response.json()
        
    except requests.exceptions.RequestException as e:
        return {"error": f"Request failed: {str(e)}"}
    except json.JSONDecodeError:
        return {"error": f"Invalid response from CoinPayments: {response.text[:200]}"}


def create_transaction(user_id: int, username: str, plan_key: str, crypto: str = "LTC", ipn_url: str = None):
    """Create a CoinPayments invoice for premium purchase"""
    if not COINPAYMENTS_CLIENT_ID or not COINPAYMENTS_CLIENT_SECRET:
        return {"error": "CoinPayments API credentials not configured"}
    
    plan = PREMIUM_PLANS.get(plan_key)
    if not plan:
        return {"error": "Invalid plan"}
    
    if crypto not in SUPPORTED_CRYPTOS:
        return {"error": f"Unsupported cryptocurrency. Use: {', '.join(SUPPORTED_CRYPTOS.keys())}"}
    
    order_id = f"ONICHAN-{user_id}-{plan_key}-{int(datetime.now().timestamp())}"
    
    invoice_data = {
        "invoiceId": order_id,
        "amount": float(plan['price']),
        "currency": {
            "currencyId": USD_CURRENCY_ID
        },
        "notesToRecipient": f"Onichan Bot - {plan['name']}",
        "metadata": {
            "userId": str(user_id),
            "username": username or "User",
            "planKey": plan_key
        }
    }
    
    if ipn_url:
        invoice_data["notificationUrl"] = ipn_url
    
    endpoint = "/merchant/invoices"
    print(f"[CoinPayments] Sending payload: {json.dumps(invoice_data)}")
    result = make_api_request("POST", endpoint, invoice_data)
    
    if "error" in result:
        return result
    
    # Handle v2 API response format
    data = result.get("data", result)
    invoice_id = data.get("id", order_id)
    # v2 uses 'link' and 'checkoutLink' instead of 'invoiceUrl'/'paymentUrl'
    payment_url = data.get("checkoutLink", data.get("link", data.get("invoiceUrl", data.get("paymentUrl", ""))))
    
    save_pending_transaction(
        txn_id=invoice_id,
        user_id=user_id,
        username=username,
        plan_key=plan_key,
        amount=plan['price'],
        crypto=crypto,
        address=payment_url,
        crypto_amount=str(plan['price'])
    )
    
    return {
        "success": True,
        "txn_id": invoice_id,
        "order_id": order_id,
        "payment_url": payment_url,
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
                        "amount": float(parts[4]),
                        "crypto": parts[5],
                        "address": parts[6],
                        "crypto_amount": parts[7],
                        "created": parts[8],
                        "status": parts[9]
                    }
    except:
        pass
    return None


def get_user_pending_transactions(user_id):
    """Get all pending transactions for a user"""
    init_crypto_files()
    transactions = []
    try:
        with open(CRYPTO_PENDING, 'r', encoding='utf-8') as f:
            for line in f:
                parts = line.strip().split('|')
                if len(parts) >= 10 and int(parts[1]) == user_id and parts[9] == "PENDING":
                    transactions.append({
                        "txn_id": parts[0],
                        "plan_key": parts[3],
                        "amount": parts[4],
                        "crypto": parts[5],
                        "address": parts[6],
                        "crypto_amount": parts[7],
                        "created": parts[8]
                    })
    except:
        pass
    return transactions


def mark_transaction_complete(txn_id):
    """Mark a transaction as complete"""
    init_crypto_files()
    try:
        with open(CRYPTO_PENDING, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        with open(CRYPTO_PENDING, 'w', encoding='utf-8') as f:
            for line in lines:
                if line.startswith(txn_id):
                    line = line.replace("|PENDING", "|COMPLETE")
                f.write(line)
        return True
    except:
        return False


def activate_premium(user_id: int, plan_key: str, username: str = "User", payment_method: str = "Crypto"):
    """Activate premium for a user"""
    plan = PREMIUM_PLANS.get(plan_key)
    if not plan:
        return False
    
    expiry = datetime.now() + timedelta(days=plan['duration_days'])
    expiry_str = expiry.strftime("%Y-%m-%d")
    
    try:
        with open(DB_PREMIUM, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        new_lines = []
        found = False
        for line in lines:
            parts = line.strip().split()
            if parts and int(parts[0]) == user_id:
                if len(parts) >= 2:
                    try:
                        old_expiry = datetime.strptime(parts[1], "%Y-%m-%d")
                        if old_expiry > datetime.now():
                            expiry = old_expiry + timedelta(days=plan['duration_days'])
                            expiry_str = expiry.strftime("%Y-%m-%d")
                    except:
                        pass
                new_lines.append(f"{user_id} {expiry_str}\n")
                found = True
            else:
                new_lines.append(line)
        
        if not found:
            new_lines.append(f"{user_id} {expiry_str}\n")
        
        with open(DB_PREMIUM, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
        
        payment_record = f"{datetime.now()}|{user_id}|@{username}|{plan['name']}|${plan['price']}|{payment_method}|SUCCESS\n"
        with open(DB_PAYMENTS, 'a', encoding='utf-8') as f:
            f.write(payment_record)
        
        return {
            "success": True,
            "plan": plan['name'],
            "expiry": expiry_str,
            "duration_days": plan['duration_days']
        }
        
    except Exception as e:
        print(f"Error activating premium: {e}")
        return False


def verify_webhook_signature(payload: str, signature: str, timestamp: str) -> bool:
    """Verify webhook signature from CoinPayments v2"""
    if not COINPAYMENTS_CLIENT_SECRET:
        return False
    
    message = timestamp + payload
    expected_signature = hmac.new(
        COINPAYMENTS_CLIENT_SECRET.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(expected_signature, signature)


def process_webhook(payload: dict, headers: dict) -> dict:
    """Process webhook notification from CoinPayments v2"""
    
    signature = headers.get("X-CoinPayments-Signature", "")
    timestamp = headers.get("X-CoinPayments-Timestamp", "")
    
    if not signature or not timestamp:
        return {"error": "Missing signature headers"}
    
    invoice_id = payload.get("id", "")
    status = payload.get("status", "")
    
    if status in ["completed", "paid"]:
        try:
            pending_txn = get_pending_transaction(invoice_id)
            
            if not pending_txn:
                order_id = payload.get("invoiceId", "")
                if order_id:
                    parts = order_id.split("-")
                    if len(parts) >= 3 and parts[0] == "ONICHAN":
                        user_id = int(parts[1])
                        plan_key = parts[2]
                        username = "User"
                    else:
                        return {"error": f"Invoice {invoice_id} not found in pending transactions"}
                else:
                    return {"error": f"Invoice {invoice_id} not found in pending transactions"}
            else:
                user_id = pending_txn["user_id"]
                username = pending_txn["username"]
                plan_key = pending_txn["plan_key"]
            
            result = activate_premium(user_id, plan_key, username, "CoinPayments")
            
            if result:
                mark_transaction_complete(invoice_id)
                
                log_crypto_transaction(
                    txn_id=invoice_id,
                    user_id=user_id,
                    username=username,
                    plan_key=plan_key,
                    amount=payload.get("amount", {}).get("displayValue", "0"),
                    currency="USD",
                    status="COMPLETE"
                )
                
                return {
                    "success": True,
                    "user_id": user_id,
                    "plan_key": plan_key,
                    "expiry": result.get("expiry"),
                    "message": f"Premium activated for user {user_id}"
                }
            else:
                return {"error": "Failed to activate premium"}
                
        except Exception as e:
            return {"error": f"Failed to process: {str(e)}"}
    
    elif status in ["failed", "expired", "cancelled"]:
        log_crypto_transaction(
            txn_id=invoice_id,
            user_id=0,
            username="",
            plan_key="",
            amount="0",
            currency="USD",
            status=f"FAILED: {status}"
        )
        return {"status": "failed", "message": status}
    
    else:
        return {"status": "pending", "message": f"Waiting: {status}"}


def log_crypto_transaction(txn_id, user_id, username, plan_key, amount, currency, status):
    """Log crypto transaction"""
    init_crypto_files()
    record = f"{datetime.now()}|{txn_id}|{user_id}|{username}|{plan_key}|{amount}|{currency}|{status}\n"
    with open(CRYPTO_FILE, 'a', encoding='utf-8') as f:
        f.write(record)


def get_transaction_status(txn_id: str) -> dict:
    """Check invoice status via API"""
    if not COINPAYMENTS_CLIENT_ID or not COINPAYMENTS_CLIENT_SECRET:
        return {"error": "CoinPayments API credentials not configured"}
    
    endpoint = f"/merchant/invoices/{txn_id}"
    result = make_api_request("GET", endpoint)
    
    if "error" in result:
        return result
    
    return {
        "success": True,
        "status": result.get("status", "unknown"),
        "amount": result.get("amount", {}).get("displayValue", "0"),
        "payment_url": result.get("paymentUrl", "")
    }


def get_supported_cryptos():
    """Get list of supported cryptocurrencies"""
    return {k: v["name"] for k, v in SUPPORTED_CRYPTOS.items()}


def get_crypto_stats():
    """Get crypto payment statistics"""
    init_crypto_files()
    stats = {"total": 0, "count": 0, "by_crypto": {}}
    
    try:
        with open(CRYPTO_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                parts = line.strip().split('|')
                if len(parts) >= 8 and "COMPLETE" in parts[7]:
                    stats["count"] += 1
                    try:
                        amount = float(parts[5])
                        stats["total"] += amount
                    except:
                        pass
    except:
        pass
    
    return stats
