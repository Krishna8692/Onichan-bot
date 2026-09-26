"""
CC Generator using DrLab API
Generates credit card numbers from BIN using external API
"""

import requests
import random
from datetime import datetime, timedelta

API_URL = "https://drlabapis.onrender.com/api/ccgenerator"

def generate_cards(bin_number, count=10, custom_month=None, custom_year=None, custom_cvv=None):
    """
    Generate multiple credit cards using DrLab API
    
    Args:
        bin_number: BIN (first 6-9 digits)
        count: Number of cards to generate
        custom_month: Custom expiry month (optional)
        custom_year: Custom expiry year (optional)
        custom_cvv: Custom CVV (optional, 'xxx' for random)
    
    Returns:
        List of card dictionaries
    """
    cards = []
    
    try:
        response = requests.get(f"{API_URL}?bin={bin_number}", timeout=15)
        
        if response.status_code == 200:
            data = response.json()
            
            api_cards = []
            if isinstance(data, list):
                api_cards = data
            elif isinstance(data, dict):
                if 'cards' in data:
                    api_cards = data['cards']
                elif 'data' in data:
                    api_cards = data['data'] if isinstance(data['data'], list) else [data['data']]
                elif 'cc' in data or 'card' in data:
                    api_cards = [data]
            
            for i, card_data in enumerate(api_cards):
                if i >= count:
                    break
                
                if isinstance(card_data, str):
                    parts = card_data.replace('/', '|').split('|')
                    if len(parts) >= 4:
                        cc = parts[0].strip()
                        mm = parts[1].strip().zfill(2)
                        yy = parts[2].strip()[-2:] if len(parts[2].strip()) == 4 else parts[2].strip()
                        cvv = parts[3].strip()
                    else:
                        continue
                elif isinstance(card_data, dict):
                    cc = str(card_data.get('cc', card_data.get('card', card_data.get('number', ''))))
                    mm = str(card_data.get('mm', card_data.get('month', card_data.get('exp_month', '')))).zfill(2)
                    yy = str(card_data.get('yy', card_data.get('year', card_data.get('exp_year', ''))))
                    yy = yy[-2:] if len(yy) == 4 else yy
                    cvv = str(card_data.get('cvv', card_data.get('cvc', card_data.get('cvv2', ''))))
                else:
                    continue
                
                if not cc:
                    continue
                
                if custom_month:
                    mm = str(custom_month).zfill(2)
                if custom_year:
                    _yr = str(custom_year).strip(); yy = f"20{_yr[-2:]}" if len(_yr) <= 2 else _yr[-4:]
                
                cvv_length = 4 if is_amex(bin_number) else 3
                if custom_cvv and custom_cvv.lower() != 'xxx' and custom_cvv.lower() != 'xxxx':
                    cvv = str(custom_cvv).zfill(cvv_length)
                elif not cvv or cvv.lower() in ['xxx', 'xxxx'] or len(cvv) < 3:
                    cvv = generate_cvv(length=cvv_length)
                
                cards.append({
                    'cc': cc,
                    'mm': mm,
                    'yy': yy,
                    'cvv': cvv,
                    'full': f"{cc}|{mm}|{yy}|{cvv}"
                })
            
            while len(cards) < count:
                cc = generate_card_number_local(bin_number)
                if custom_month and custom_year:
                    mm = str(custom_month).zfill(2)
                    _yr = str(custom_year).strip(); yy = f"20{_yr[-2:]}" if len(_yr) <= 2 else _yr[-4:]
                else:
                    mm, yy = generate_expiry_date()
                
                cvv_length = 4 if is_amex(bin_number) else 3
                if custom_cvv and custom_cvv.lower() != 'xxx' and custom_cvv.lower() != 'xxxx':
                    cvv = str(custom_cvv).zfill(cvv_length)
                else:
                    cvv = generate_cvv(length=cvv_length)
                
                cards.append({
                    'cc': cc,
                    'mm': mm,
                    'yy': yy,
                    'cvv': cvv,
                    'full': f"{cc}|{mm}|{yy}|{cvv}"
                })
                
    except Exception as e:
        for i in range(count):
            cc = generate_card_number_local(bin_number)
            if custom_month and custom_year:
                mm = str(custom_month).zfill(2)
                _yr = str(custom_year).strip(); yy = f"20{_yr[-2:]}" if len(_yr) <= 2 else _yr[-4:]
            else:
                mm, yy = generate_expiry_date()
            
            cvv_length = 4 if is_amex(bin_number) else 3
            if custom_cvv and custom_cvv.lower() != 'xxx' and custom_cvv.lower() != 'xxxx':
                cvv = str(custom_cvv).zfill(cvv_length)
            else:
                cvv = generate_cvv(length=cvv_length)
            
            cards.append({
                'cc': cc,
                'mm': mm,
                'yy': yy,
                'cvv': cvv,
                'full': f"{cc}|{mm}|{yy}|{cvv}"
            })
    
    return cards

def luhn_checksum(card_number):
    """Calculate Luhn checksum"""
    def digits_of(n):
        return [int(d) for d in str(n)]
    
    digits = digits_of(card_number)
    odd_digits = digits[-1::-2]
    even_digits = digits[-2::-2]
    checksum = sum(odd_digits)
    
    for d in even_digits:
        checksum += sum(digits_of(d * 2))
    
    return checksum % 10

def calculate_luhn(partial_card_number):
    """Calculate the check digit for Luhn algorithm"""
    check_digit = luhn_checksum(int(partial_card_number) * 10)
    return (10 - check_digit) % 10

def generate_card_number_local(bin_number):
    """Generate a valid card number from BIN using Luhn algorithm (local fallback)"""
    bin_str = str(bin_number)
    bin_length = len(bin_str)
    
    if bin_length < 6:
        bin_str = bin_str.ljust(6, '0')
        bin_length = 6
    elif bin_length > 9:
        bin_str = bin_str[:9]
        bin_length = 9
    
    card_length = 15 if is_amex(bin_number) else 16
    
    random_digits_count = card_length - bin_length - 1
    middle_digits = ''.join([str(random.randint(0, 9)) for _ in range(random_digits_count)])
    partial_card = bin_str + middle_digits
    check_digit = calculate_luhn(partial_card)
    card_number = partial_card + str(check_digit)
    
    return card_number

def generate_expiry_date(custom_month=None, custom_year=None):
    """Generate expiry date — returns (MM, YYYY) with 4-digit year."""
    if custom_month and custom_year:
        mm = str(custom_month).zfill(2)
        yr = str(custom_year).strip()
        yy = f"20{yr[-2:]}" if len(yr) <= 2 else yr[-4:]
        return mm, yy

    current_date = datetime.now()
    future_date  = current_date + timedelta(days=random.randint(365, 1825))

    mm = str(future_date.month).zfill(2)
    yy = str(future_date.year)

    return mm, yy

def generate_cvv(custom_cvv=None, length=3):
    """Generate CVV"""
    if custom_cvv and custom_cvv.lower() != 'xxx' and custom_cvv.lower() != 'xxxx':
        return str(custom_cvv).zfill(length)
    
    return ''.join([str(random.randint(0, 9)) for _ in range(length)])

def is_amex(bin_number):
    """Check if BIN is AMEX (starts with 34 or 37)"""
    bin_str = str(bin_number)
    if len(bin_str) >= 2:
        return bin_str[:2] in ['34', '37']
    return False

def parse_gen_format(format_string):
    """
    Parse generation format string
    
    Formats:
        123456/xx/xx/xxx 10 - Generate 10 cards with random dates/CVV
        12345678/12/25/xxx 5 - Generate 5 cards with custom date, random CVV
        123456789/12/25/123 20 - Generate 20 cards with custom date and CVV
    
    Returns:
        (bin, month, year, cvv, count)
    """
    try:
        parts = format_string.strip().split()
        
        if len(parts) < 1:
            return None
        
        count = 10
        if len(parts) >= 2 and parts[-1].isdigit():
            count = int(parts[-1])
            format_part = ' '.join(parts[:-1])
        else:
            format_part = ' '.join(parts)
        
        format_parts = format_part.replace('|', '/').split('/')
        
        if len(format_parts) < 1:
            return None
        
        bin_number = format_parts[0]
        if len(bin_number) < 6:
            bin_number = bin_number.ljust(6, '0')
        elif len(bin_number) > 9:
            bin_number = bin_number[:9]
        
        month = None
        if len(format_parts) >= 2 and format_parts[1].lower() != 'xx':
            month = int(format_parts[1])
        
        year = None
        if len(format_parts) >= 3 and format_parts[2].lower() != 'xx':
            year = int(format_parts[2])
            if year < 100:
                year = 2000 + year if year < 50 else 1900 + year
        
        cvv = None
        if len(format_parts) >= 4 and format_parts[3].lower() != 'xxx':
            cvv = format_parts[3]
        
        return bin_number, month, year, cvv, count
        
    except Exception as e:
        return None

def get_card_brand(bin_number):
    """Detect card brand from BIN"""
    bin_str = str(bin_number)
    
    if not bin_str or len(bin_str) < 1:
        return "Unknown"
    
    first_digit = bin_str[0]
    first_two = bin_str[:2] if len(bin_str) >= 2 else bin_str[0]
    first_four = bin_str[:4] if len(bin_str) >= 4 else bin_str
    
    if first_digit == '4':
        return "VISA"
    
    if first_two in ['51', '52', '53', '54', '55']:
        return "MASTERCARD"
    
    try:
        if 2221 <= int(first_four) <= 2720:
            return "MASTERCARD"
    except:
        pass
    
    if first_two in ['34', '37']:
        return "AMEX"
    
    if first_two == '65' or first_four == '6011':
        return "DISCOVER"
    
    try:
        if 644 <= int(first_four[:3]) <= 649:
            return "DISCOVER"
    except:
        pass
    
    if first_two in ['36', '38']:
        return "DINERS"
    
    try:
        if 300 <= int(first_four[:3]) <= 305:
            return "DINERS"
    except:
        pass
    
    if len(first_four) >= 2 and first_four[:2] == '35':
        return "JCB"
    
    return "Unknown"

def validate_generated_card(card_number):
    """Validate card using Luhn algorithm"""
    try:
        return luhn_checksum(int(card_number)) == 0
    except:
        return False
