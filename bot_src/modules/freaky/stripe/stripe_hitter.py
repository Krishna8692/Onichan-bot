"""
stripe_hitter.py — BINLookup utility (standalone, no scipy/numpy).
"""
import aiohttp
from typing import Dict


class BINLookup:
    """Free BIN database lookup with in-memory caching."""
    _cache: Dict[str, Dict] = {}

    @classmethod
    async def lookup(cls, card_number: str) -> Dict:
        bin6 = str(card_number)[:6]
        if bin6 in cls._cache:
            return cls._cache[bin6]
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"https://bins.antipublic.cc/bins/{bin6}",
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        result = {
                            'country':      (data.get('countrycode') or '').upper(),
                            'country_name': data.get('country', ''),
                            'flag':         data.get('emoji_flag', '🌐'),
                            'code':         (data.get('countrycode') or 'UNK').upper(),
                            'bank':         data.get('bank', ''),
                            'brand':        data.get('brand', ''),
                            'type':         data.get('type', ''),
                            'level':        data.get('level', ''),
                        }
                        cls._cache[bin6] = result
                        return result
        except Exception:
            pass
        fallback = {
            'country': '', 'country_name': '', 'flag': '🌐', 'code': 'UNK',
            'bank': '', 'brand': '', 'type': '', 'level': '',
        }
        cls._cache[bin6] = fallback
        return fallback
