import hashlib
import requests
import time
import os

EASEBUZZ_KEY = os.environ.get('EASEBUZZ_KEY', '')
EASEBUZZ_SALT = os.environ.get('EASEBUZZ_SALT', '')
EASEBUZZ_ENV = os.environ.get('EASEBUZZ_ENV', 'test')

BASE_URL = 'https://pay.easebuzz.in' if EASEBUZZ_ENV == 'production' else 'https://testpay.easebuzz.in'

UPI_PLANS = {
    "1_week": {"name": "1 Week Premium", "duration_days": 7, "amount": "99.00", "inr": "₹99"},
    "2_weeks": {"name": "2 Weeks Premium", "duration_days": 14, "amount": "149.00", "inr": "₹149"},
    "1_month": {"name": "1 Month Premium", "duration_days": 30, "amount": "249.00", "inr": "₹249"},
    "3_months": {"name": "3 Months Premium", "duration_days": 90, "amount": "599.00", "inr": "₹599"}
}


def generate_hash(data: dict) -> str:
    hash_sequence = (
        f"{EASEBUZZ_KEY}|"
        f"{data.get('txnid', '')}|"
        f"{data.get('amount', '')}|"
        f"{data.get('productinfo', '')}|"
        f"{data.get('firstname', '')}|"
        f"{data.get('email', '')}|"
        f"{data.get('udf1', '')}|"
        f"{data.get('udf2', '')}|"
        f"{data.get('udf3', '')}|"
        f"{data.get('udf4', '')}|"
        f"{data.get('udf5', '')}||||||"
        f"{EASEBUZZ_SALT}"
    )
    return hashlib.sha512(hash_sequence.encode('utf-8')).hexdigest()


def verify_response_hash(data: dict) -> bool:
    reverse_hash_sequence = (
        f"{EASEBUZZ_SALT}|"
        f"{data.get('status', '')}||||||"
        f"{data.get('udf5', '')}|"
        f"{data.get('udf4', '')}|"
        f"{data.get('udf3', '')}|"
        f"{data.get('udf2', '')}|"
        f"{data.get('udf1', '')}|"
        f"{data.get('email', '')}|"
        f"{data.get('firstname', '')}|"
        f"{data.get('productinfo', '')}|"
        f"{data.get('amount', '')}|"
        f"{data.get('txnid', '')}|"
        f"{EASEBUZZ_KEY}"
    )
    calculated_hash = hashlib.sha512(reverse_hash_sequence.encode('utf-8')).hexdigest()
    return calculated_hash == data.get('hash', '')


def create_payment(user_id: int, plan_key: str, username: str = "", success_url: str = "", failure_url: str = "") -> dict:
    if not EASEBUZZ_KEY or not EASEBUZZ_SALT:
        return {"success": False, "error": "Easebuzz API keys not configured"}
    
    if plan_key not in UPI_PLANS:
        return {"success": False, "error": "Invalid plan"}
    
    plan = UPI_PLANS[plan_key]
    txnid = f"EB{user_id}_{int(time.time())}"
    
    payment_data = {
        'key': EASEBUZZ_KEY,
        'txnid': txnid,
        'amount': plan['amount'],
        'productinfo': f"Premium {plan['name']}",
        'firstname': username or f"User{user_id}",
        'email': f"user{user_id}@telegram.bot",
        'phone': '9999999999',
        'surl': success_url or 'https://example.com/success',
        'furl': failure_url or 'https://example.com/failure',
        'udf1': str(user_id),
        'udf2': plan_key,
        'udf3': str(plan['duration_days']),
        'udf4': '',
        'udf5': ''
    }
    
    payment_data['hash'] = generate_hash(payment_data)
    
    try:
        url = f"{BASE_URL}/payment/initiateLink"
        response = requests.post(url, data=payment_data, timeout=30)
        result = response.json()
        
        if result.get('status') == 1:
            access_key = result.get('data')
            payment_url = f"{BASE_URL}/pay/{access_key}"
            
            return {
                "success": True,
                "txnid": txnid,
                "payment_url": payment_url,
                "access_key": access_key,
                "amount": plan['amount'],
                "plan": plan['name'],
                "duration_days": plan['duration_days']
            }
        else:
            return {
                "success": False,
                "error": result.get('error', result.get('data', 'Unknown error'))
            }
            
    except Exception as e:
        return {"success": False, "error": str(e)}


def verify_transaction(txnid: str) -> dict:
    if not EASEBUZZ_KEY or not EASEBUZZ_SALT:
        return {"success": False, "error": "Easebuzz API keys not configured"}
    
    hash_string = f"{EASEBUZZ_KEY}|{txnid}|{EASEBUZZ_SALT}"
    hash_value = hashlib.sha512(hash_string.encode('utf-8')).hexdigest()
    
    try:
        url = f"{BASE_URL}/transaction/v1/retrieve"
        params = {
            'key': EASEBUZZ_KEY,
            'txnid': txnid,
            'hash': hash_value
        }
        
        response = requests.post(url, data=params, timeout=30)
        result = response.json()
        
        if result.get('status') == 1:
            msg = result.get('msg', {})
            return {
                "success": True,
                "status": msg.get('status'),
                "txnid": msg.get('txnid'),
                "amount": msg.get('amount'),
                "easepayid": msg.get('easepayid'),
                "mode": msg.get('mode'),
                "udf1": msg.get('udf1'),
                "udf2": msg.get('udf2'),
                "udf3": msg.get('udf3')
            }
        else:
            return {"success": False, "error": result.get('error', 'Transaction not found')}
            
    except Exception as e:
        return {"success": False, "error": str(e)}


def process_webhook(data: dict) -> dict:
    txnid = data.get('txnid', '')
    status = data.get('status', '')
    amount = data.get('amount', '')
    easepayid = data.get('easepayid', '')
    mode = data.get('mode', '')
    
    user_id = data.get('udf1', '')
    plan_key = data.get('udf2', '')
    duration_days = data.get('udf3', '')
    
    if status == 'success':
        return {
            "success": True,
            "txnid": txnid,
            "user_id": int(user_id) if user_id.isdigit() else 0,
            "plan_key": plan_key,
            "duration_days": int(duration_days) if duration_days.isdigit() else 7,
            "amount": amount,
            "easepayid": easepayid,
            "mode": mode
        }
    else:
        return {
            "success": False,
            "status": status,
            "txnid": txnid,
            "error": data.get('error_Message', 'Payment failed')
        }
