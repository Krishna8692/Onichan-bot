"""
================================================================================
  Binance Pay Payment Gateway Integration
  Handles cryptocurrency payments via Binance Pay Merchant API
  With automatic webhook verification and premium activation
================================================================================
"""

import os
import sys
import hmac
import hashlib
import time
import json
import requests
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DB_PREMIUM, DB_INVOICES, DB_PAYMENTS, DATABASE_DIR

BINANCE_API_KEY = os.environ.get("BINANCE_API_KEY", "")
BINANCE_SECRET_KEY = os.environ.get("BINANCE_SECRET_KEY", "")

BINANCE_PAY_URL = "https://bpay.binanceapi.com"

CRYPTO_FILE = f"{DATABASE_DIR}/binance_transactions.txt"
CRYPTO_PENDING = f"{DATABASE_DIR}/binance_pending.txt"

PREMIUM_PLANS = {
    "1_week": {"name": "1 Week Premium", "duration_days": 7, "price": 3},
    "2_weeks": {"name": "2 Weeks Premium", "duration_days": 14, "price": 5},
    "1_month": {"name": "1 Month Premium", "duration_days": 30, "price": 10},
    "3_months": {"name": "3 Months Premium", "duration_days": 90, "price": 25}
}

telegram_bot = None

def set_telegram_bot(bot):
    """Set the telegram bot instance for sending notifications"""
    global telegram_bot
    telegram_bot = bot

def init_binance_files():
    """Initialize Binance transaction files"""
    os.makedirs(DATABASE_DIR, exist_ok=True)
    for f in [CRYPTO_FILE, CRYPTO_PENDING]:
        if not os.path.exists(f):
            with open(f, 'w', encoding='utf-8') as file:
                pass


def generate_signature(payload: str) -> str:
    """Generate HMAC-SHA512 signature for Binance Pay API"""
    return hmac.new(
        BINANCE_SECRET_KEY.encode('utf-8'),
        payload.encode('utf-8'),
        hashlib.sha512
    ).hexdigest().upper()


def verify_webhook_signature(timestamp: str, nonce: str, body: str, signature: str) -> bool:
    """Verify incoming webhook signature from Binance"""
    if not BINANCE_SECRET_KEY:
        return False
    
    payload = f"{timestamp}\n{nonce}\n{body}\n"
    expected_sig = generate_signature(payload)
    return hmac.compare_digest(expected_sig, signature.upper())


def generate_nonce():
    """Generate random nonce for API requests"""
    import random
    import string
    return ''.join(random.choices(string.ascii_letters + string.digits, k=32))


def create_order(user_id: int, username: str, plan_key: str, webhook_url: str = None):
    """
    Create a Binance Pay order for premium purchase
    Returns checkout URL for user to complete payment
    """
    if not BINANCE_API_KEY or not BINANCE_SECRET_KEY:
        return {"error": "Binance API credentials not configured"}
    
    plan = PREMIUM_PLANS.get(plan_key)
    if not plan:
        return {"error": "Invalid plan"}
    
    timestamp = int(time.time() * 1000)
    nonce = generate_nonce()
    
    merchant_trade_no = f"ONICHAN{user_id}{int(time.time())}"
    
    body = {
        "env": {
            "terminalType": "WEB"
        },
        "merchantTradeNo": merchant_trade_no,
        "orderAmount": float(plan['price']),
        "currency": "USDT",
        "goods": {
            "goodsType": "02",
            "goodsCategory": "Z000",
            "referenceGoodsId": plan_key,
            "goodsName": plan['name'],
            "goodsDetail": f"Onichan Bot - {plan['name']}"
        },
        "description": f"Premium for user {user_id}"
    }
    
    if webhook_url:
        body["webhookUrl"] = webhook_url
    
    body_json = json.dumps(body)
    payload = f"{timestamp}\n{nonce}\n{body_json}\n"
    signature = generate_signature(payload)
    
    headers = {
        "Content-Type": "application/json",
        "BinancePay-Timestamp": str(timestamp),
        "BinancePay-Nonce": nonce,
        "BinancePay-Certificate-SN": BINANCE_API_KEY,
        "BinancePay-Signature": signature
    }
    
    try:
        response = requests.post(
            f"{BINANCE_PAY_URL}/binancepay/openapi/v2/order",
            headers=headers,
            json=body,
            timeout=30
        )
        
        result = response.json()
        
        if result.get("status") == "SUCCESS":
            data = result.get("data", {})
            
            prepay_id = data.get("prepayId", merchant_trade_no)
            checkout_url = data.get("checkoutUrl", "")
            universal_url = data.get("universalUrl", "")
            deeplink = data.get("deeplink", "")
            
            save_pending_transaction(
                txn_id=merchant_trade_no,
                prepay_id=prepay_id,
                user_id=user_id,
                username=username,
                plan_key=plan_key,
                amount=plan['price']
            )
            
            return {
                "success": True,
                "merchant_trade_no": merchant_trade_no,
                "prepay_id": prepay_id,
                "checkout_url": checkout_url,
                "universal_url": universal_url,
                "deeplink": deeplink,
                "plan": plan,
                "amount": plan['price']
            }
        else:
            error_msg = result.get("errorMessage", "Unknown error")
            error_code = result.get("code", "")
            return {"error": f"{error_code}: {error_msg}"}
            
    except Exception as e:
        return {"error": f"Request failed: {str(e)}"}


def save_pending_transaction(txn_id, prepay_id, user_id, username, plan_key, amount):
    """Save pending transaction to file"""
    init_binance_files()
    record = f"{txn_id}|{prepay_id}|{user_id}|{username}|{plan_key}|{amount}|{datetime.now().isoformat()}|PENDING\n"
    with open(CRYPTO_PENDING, 'a', encoding='utf-8') as f:
        f.write(record)


def get_pending_transaction(merchant_trade_no: str = None, prepay_id: str = None):
    """Get pending transaction by merchant_trade_no or prepay_id"""
    init_binance_files()
    try:
        with open(CRYPTO_PENDING, 'r', encoding='utf-8') as f:
            for line in f:
                parts = line.strip().split('|')
                if len(parts) >= 8:
                    if (merchant_trade_no and parts[0] == merchant_trade_no) or \
                       (prepay_id and parts[1] == prepay_id):
                        return {
                            "merchant_trade_no": parts[0],
                            "prepay_id": parts[1],
                            "user_id": int(parts[2]),
                            "username": parts[3],
                            "plan_key": parts[4],
                            "amount": float(parts[5]),
                            "created": parts[6],
                            "status": parts[7]
                        }
    except Exception as e:
        print(f"Error reading pending transaction: {e}")
    return None


def get_user_pending_transactions(user_id):
    """Get all pending transactions for a user"""
    init_binance_files()
    transactions = []
    try:
        with open(CRYPTO_PENDING, 'r', encoding='utf-8') as f:
            for line in f:
                parts = line.strip().split('|')
                if len(parts) >= 8 and int(parts[2]) == user_id and parts[7] == "PENDING":
                    transactions.append({
                        "merchant_trade_no": parts[0],
                        "prepay_id": parts[1],
                        "plan_key": parts[4],
                        "amount": parts[5],
                        "created": parts[6]
                    })
    except:
        pass
    return transactions


def mark_transaction_complete(merchant_trade_no: str):
    """Mark a transaction as complete"""
    init_binance_files()
    try:
        with open(CRYPTO_PENDING, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        with open(CRYPTO_PENDING, 'w', encoding='utf-8') as f:
            for line in lines:
                if line.startswith(merchant_trade_no + "|"):
                    line = line.replace("|PENDING", "|PAID")
                f.write(line)
        return True
    except:
        return False


def activate_premium(user_id: int, plan_key: str, username: str = "User", payment_method: str = "Binance Pay"):
    """Activate premium for a user"""
    plan = PREMIUM_PLANS.get(plan_key)
    if not plan:
        return False
    
    expiry = datetime.now() + timedelta(days=plan['duration_days'])
    expiry_str = expiry.strftime("%Y-%m-%d")
    
    try:
        if os.path.exists(DB_PREMIUM):
            with open(DB_PREMIUM, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        else:
            lines = []
        
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
        
        payment_record = f"{datetime.now().isoformat()}|{user_id}|@{username}|{plan['name']}|${plan['price']}|{payment_method}|SUCCESS\n"
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


def process_webhook(data: dict) -> dict:
    """
    Process Binance Pay webhook callback
    Returns activation result
    """
    try:
        biz_type = data.get("bizType")
        biz_status = data.get("bizStatus")
        biz_data = data.get("data", {})
        
        if biz_type != "PAY":
            return {"success": False, "error": "Not a payment notification"}
        
        if biz_status not in ["PAY_SUCCESS", "PAID"]:
            return {"success": False, "error": f"Payment not successful: {biz_status}"}
        
        merchant_trade_no = biz_data.get("merchantTradeNo")
        transaction_id = biz_data.get("transactionId")
        paid_amount = biz_data.get("transactAmount")
        
        if not merchant_trade_no:
            return {"success": False, "error": "Missing merchant trade number"}
        
        pending = get_pending_transaction(merchant_trade_no=merchant_trade_no)
        
        if not pending:
            return {"success": False, "error": f"Transaction not found: {merchant_trade_no}"}
        
        if pending.get("status") == "PAID":
            return {"success": True, "message": "Already processed", "already_processed": True}
        
        mark_transaction_complete(merchant_trade_no)
        
        result = activate_premium(
            user_id=pending["user_id"],
            plan_key=pending["plan_key"],
            username=pending["username"],
            payment_method="Binance Pay"
        )
        
        log_binance_transaction(
            txn_id=merchant_trade_no,
            binance_txn_id=transaction_id,
            user_id=pending["user_id"],
            username=pending["username"],
            plan_key=pending["plan_key"],
            amount=paid_amount or pending["amount"],
            status="SUCCESS"
        )
        
        if result:
            return {
                "success": True,
                "user_id": pending["user_id"],
                "username": pending["username"],
                "plan": result.get("plan"),
                "expiry": result.get("expiry"),
                "transaction_id": transaction_id
            }
        else:
            return {"success": False, "error": "Failed to activate premium"}
            
    except Exception as e:
        print(f"Webhook processing error: {e}")
        return {"success": False, "error": str(e)}


def query_order(merchant_trade_no: str = None, prepay_id: str = None):
    """Query order status from Binance Pay"""
    if not BINANCE_API_KEY or not BINANCE_SECRET_KEY:
        return {"error": "Binance API credentials not configured"}
    
    timestamp = int(time.time() * 1000)
    nonce = generate_nonce()
    
    body = {}
    if merchant_trade_no:
        body["merchantTradeNo"] = merchant_trade_no
    elif prepay_id:
        body["prepayId"] = prepay_id
    else:
        return {"error": "Must provide merchantTradeNo or prepayId"}
    
    body_json = json.dumps(body)
    payload = f"{timestamp}\n{nonce}\n{body_json}\n"
    signature = generate_signature(payload)
    
    headers = {
        "Content-Type": "application/json",
        "BinancePay-Timestamp": str(timestamp),
        "BinancePay-Nonce": nonce,
        "BinancePay-Certificate-SN": BINANCE_API_KEY,
        "BinancePay-Signature": signature
    }
    
    try:
        response = requests.post(
            f"{BINANCE_PAY_URL}/binancepay/openapi/v2/order/query",
            headers=headers,
            json=body,
            timeout=30
        )
        
        result = response.json()
        
        if result.get("status") == "SUCCESS":
            data = result.get("data", {})
            return {
                "success": True,
                "status": data.get("status"),
                "merchant_trade_no": data.get("merchantTradeNo"),
                "order_amount": data.get("orderAmount"),
                "paid_amount": data.get("transactAmount"),
                "transaction_id": data.get("transactionId"),
                "open_user_id": data.get("openUserId"),
                "pay_time": data.get("payTime")
            }
        else:
            return {"error": result.get("errorMessage", "Unknown error")}
            
    except Exception as e:
        return {"error": f"Request failed: {str(e)}"}


def check_and_activate_payment(merchant_trade_no: str):
    """
    Manually check payment status and activate if paid
    Useful as fallback if webhook fails
    """
    query_result = query_order(merchant_trade_no=merchant_trade_no)
    
    if query_result.get("error"):
        return query_result
    
    status = query_result.get("status")
    
    if status not in ["PAID", "SUCCESS"]:
        return {"success": False, "status": status, "message": f"Payment status: {status}"}
    
    pending = get_pending_transaction(merchant_trade_no=merchant_trade_no)
    
    if not pending:
        return {"success": False, "error": "Transaction not found in pending list"}
    
    if pending.get("status") == "PAID":
        return {"success": True, "message": "Already activated", "already_processed": True}
    
    mark_transaction_complete(merchant_trade_no)
    
    result = activate_premium(
        user_id=pending["user_id"],
        plan_key=pending["plan_key"],
        username=pending["username"],
        payment_method="Binance Pay"
    )
    
    if result:
        log_binance_transaction(
            txn_id=merchant_trade_no,
            binance_txn_id=query_result.get("transaction_id", ""),
            user_id=pending["user_id"],
            username=pending["username"],
            plan_key=pending["plan_key"],
            amount=query_result.get("paid_amount", pending["amount"]),
            status="SUCCESS"
        )
        
        return {
            "success": True,
            "user_id": pending["user_id"],
            "username": pending["username"],
            "plan": result.get("plan"),
            "expiry": result.get("expiry")
        }
    
    return {"success": False, "error": "Failed to activate premium"}


def log_binance_transaction(txn_id, binance_txn_id, user_id, username, plan_key, amount, status):
    """Log Binance transaction"""
    init_binance_files()
    record = f"{datetime.now().isoformat()}|{txn_id}|{binance_txn_id}|{user_id}|{username}|{plan_key}|{amount}|{status}\n"
    with open(CRYPTO_FILE, 'a', encoding='utf-8') as f:
        f.write(record)


def get_binance_stats():
    """Get Binance payment statistics"""
    init_binance_files()
    stats = {"total": 0, "count": 0}
    
    try:
        with open(CRYPTO_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                parts = line.strip().split('|')
                if len(parts) >= 8 and parts[7] == "SUCCESS":
                    stats["count"] += 1
                    try:
                        amount = float(parts[6])
                        stats["total"] += amount
                    except:
                        pass
    except:
        pass
    
    return stats


def get_plans():
    """Get all available plans"""
    return PREMIUM_PLANS


def get_qr_code_path():
    """Get the path to Binance QR code (legacy support)"""
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), "static/binance_qr.jpg")
