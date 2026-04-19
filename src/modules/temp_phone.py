import asyncio
import aiohttp
import random
import re
from typing import Optional, List, Dict, Any
from bs4 import BeautifulSoup

COUNTRY_FLAGS = {
    "united states": "🇺🇸", "usa": "🇺🇸", "us": "🇺🇸", "canada": "🇨🇦", "united kingdom": "🇬🇧", 
    "uk": "🇬🇧", "germany": "🇩🇪", "france": "🇫🇷", "spain": "🇪🇸", "italy": "🇮🇹", 
    "netherlands": "🇳🇱", "belgium": "🇧🇪", "sweden": "🇸🇪", "norway": "🇳🇴", "denmark": "🇩🇰", 
    "finland": "🇫🇮", "poland": "🇵🇱", "russia": "🇷🇺", "ukraine": "🇺🇦", "india": "🇮🇳", 
    "china": "🇨🇳", "japan": "🇯🇵", "south korea": "🇰🇷", "korea": "🇰🇷", "australia": "🇦🇺", 
    "brazil": "🇧🇷", "mexico": "🇲🇽", "argentina": "🇦🇷", "indonesia": "🇮🇩", "thailand": "🇹🇭",
    "philippines": "🇵🇭", "vietnam": "🇻🇳", "malaysia": "🇲🇾", "singapore": "🇸🇬",
    "south africa": "🇿🇦", "nigeria": "🇳🇬", "egypt": "🇪🇬", "turkey": "🇹🇷", "israel": "🇮🇱",
    "uae": "🇦🇪", "pakistan": "🇵🇰", "bangladesh": "🇧🇩", "hong kong": "🇭🇰", "taiwan": "🇹🇼",
    "portugal": "🇵🇹", "austria": "🇦🇹", "switzerland": "🇨🇭", "czech": "🇨🇿", "romania": "🇷🇴", 
    "hungary": "🇭🇺", "greece": "🇬🇷", "ireland": "🇮🇪", "new zealand": "🇳🇿", "chile": "🇨🇱", 
    "colombia": "🇨🇴", "peru": "🇵🇪", "estonia": "🇪🇪", "latvia": "🇱🇻", "lithuania": "🇱🇹",
    "puerto rico": "🇵🇷", "morocco": "🇲🇦", "kenya": "🇰🇪"
}

def get_flag(country: str) -> str:
    country_lower = country.lower().strip()
    if country_lower in COUNTRY_FLAGS:
        return COUNTRY_FLAGS[country_lower]
    for key, flag in COUNTRY_FLAGS.items():
        if key in country_lower or country_lower in key:
            return flag
    return "🌍"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5"
}

async def fetch_numbers_from_receivesmss() -> List[Dict[str, Any]]:
    """Fetch numbers from receive-smss.com"""
    numbers = []
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://receive-smss.com/", headers=HEADERS, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                if resp.status == 200:
                    html = await resp.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    for card in soup.select('.number-boxes-item, .number-boxes1-item, .wpb_wrapper a[href*="/sms/"]'):
                        link = card.get('href', '') if card.name == 'a' else card.select_one('a').get('href', '') if card.select_one('a') else ''
                        
                        number_elem = card.select_one('h4, .number-boxes-itemm-number, span.number')
                        country_elem = card.select_one('.number-boxes-item-country, span.country, small')
                        
                        if number_elem:
                            number = number_elem.get_text(strip=True)
                        elif card.name == 'a':
                            number = card.get_text(strip=True)
                        else:
                            continue
                        
                        if not re.match(r'^\+?\d[\d\s\-]+$', number.replace('+', '')):
                            continue
                        
                        country = country_elem.get_text(strip=True) if country_elem else "USA"
                        full_link = f"https://receive-smss.com{link}" if link.startswith('/') else link
                        
                        numbers.append({
                            "number": number,
                            "country": country,
                            "link": full_link,
                            "source": "receive-smss.com"
                        })
    except Exception as e:
        print(f"receive-smss error: {e}")
    return numbers

async def fetch_numbers_from_smstome() -> List[Dict[str, Any]]:
    """Fetch numbers from smstome.com"""
    numbers = []
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://smstome.com/", headers=HEADERS, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    html = await resp.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    for card in soup.select('.number-list a, .phone-number a, a[href*="phone"]'):
                        link = card.get('href', '')
                        number = card.get_text(strip=True)
                        
                        if re.match(r'^\+?\d[\d\s\-]+$', number.replace('+', '')):
                            full_link = f"https://smstome.com{link}" if link.startswith('/') else link
                            numbers.append({
                                "number": number,
                                "country": "USA",
                                "link": full_link,
                                "source": "smstome.com"
                            })
    except Exception as e:
        print(f"smstome error: {e}")
    return numbers

async def fetch_sms_from_page(url: str) -> List[Dict[str, Any]]:
    """Fetch SMS messages from a specific number page"""
    messages = []
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                if resp.status == 200:
                    html = await resp.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    for row in soup.select('table tr, .message-item, .sms-row, .message'):
                        cells = row.select('td')
                        
                        if len(cells) >= 2:
                            sender = cells[0].get_text(strip=True)[:50]
                            body = cells[1].get_text(strip=True)[:300]
                            time_text = cells[2].get_text(strip=True) if len(cells) > 2 else ""
                            
                            if body and len(body) > 3:
                                codes = re.findall(r'\b(\d{4,8})\b', body)
                                messages.append({
                                    "FromNumber": sender,
                                    "Messagebody": body,
                                    "message_time": time_text,
                                    "codes": codes[:3]
                                })
                        else:
                            text_elem = row.select_one('.text, .body, .message-text, p')
                            if text_elem:
                                body = text_elem.get_text(strip=True)[:300]
                                sender_elem = row.select_one('.from, .sender, strong')
                                time_elem = row.select_one('.time, .date, small')
                                
                                if body:
                                    codes = re.findall(r'\b(\d{4,8})\b', body)
                                    messages.append({
                                        "FromNumber": sender_elem.get_text(strip=True)[:50] if sender_elem else "Unknown",
                                        "Messagebody": body,
                                        "message_time": time_elem.get_text(strip=True) if time_elem else "",
                                        "codes": codes[:3]
                                    })
    except Exception as e:
        print(f"SMS fetch error: {e}")
    
    return messages[:15]

STATIC_NUMBERS = [
    {"number": "+12065551234", "country": "United States", "link": "https://receive-smss.com/sms/12065551234/", "source": "static"},
    {"number": "+14155551234", "country": "United States", "link": "https://receive-smss.com/sms/14155551234/", "source": "static"},
    {"number": "+447700900123", "country": "United Kingdom", "link": "", "source": "static"},
    {"number": "+919876543210", "country": "India", "link": "", "source": "static"},
    {"number": "+4915112345678", "country": "Germany", "link": "", "source": "static"},
    {"number": "+33612345678", "country": "France", "link": "", "source": "static"},
]

async def get_countries_list() -> List[Dict[str, str]]:
    """Get list of available countries"""
    countries = set()
    
    try:
        numbers = await fetch_numbers_from_receivesmss()
        for num in numbers:
            country = num.get("country", "")
            if country:
                countries.add(country)
    except:
        pass
    
    if not countries:
        countries = {"United States", "United Kingdom", "Canada", "Germany", "France", "India", "Russia", "Brazil"}
    
    return [{"name": c, "code": c.lower().replace(' ', '-'), "flag": get_flag(c)} for c in sorted(countries)]

async def get_temp_number(country: str = None) -> Dict[str, Any]:
    """Get a temporary phone number"""
    result = {
        "success": False,
        "number": None,
        "country": None,
        "error": None,
        "messages": [],
        "link": None,
        "source": None,
        "country_code": ""
    }
    
    try:
        all_numbers = await fetch_numbers_from_receivesmss()
        
        if not all_numbers:
            smstome_numbers = await fetch_numbers_from_smstome()
            all_numbers.extend(smstome_numbers)
        
        if not all_numbers:
            all_numbers = STATIC_NUMBERS.copy()
            result["note"] = "Using cached numbers"
        
        if country:
            country_lower = country.lower()
            filtered = [n for n in all_numbers if country_lower in n.get("country", "").lower()]
            if filtered:
                all_numbers = filtered
            else:
                available = list(set(n.get("country", "Unknown") for n in all_numbers[:20]))
                result["error"] = f"Country '{country}' not found"
                result["available_countries"] = available
                return result
        
        if all_numbers:
            selected = random.choice(all_numbers)
            
            result["success"] = True
            result["number"] = selected.get("number", "")
            result["country"] = selected.get("country", "Unknown")
            result["country_code"] = selected.get("country", "").lower().replace(' ', '-')
            result["link"] = selected.get("link", "")
            result["source"] = selected.get("source", "unknown")
            
            if selected.get("link"):
                result["messages"] = await fetch_sms_from_page(selected["link"])
        else:
            result["error"] = "No numbers available"
        
    except Exception as e:
        result["error"] = str(e)
    
    return result

async def refresh_sms(country: str, number: str) -> List[Dict[str, Any]]:
    """Refresh SMS for a number"""
    number_clean = number.replace('+', '').replace(' ', '').replace('-', '')
    
    urls_to_try = [
        f"https://receive-smss.com/sms/{number_clean}/",
        f"https://smstome.com/phone/{number_clean}/"
    ]
    
    for url in urls_to_try:
        messages = await fetch_sms_from_page(url)
        if messages:
            return messages
    
    return []
