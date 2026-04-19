"""
CC Cleaner - Extract and Clean Credit Cards from Junk Text
Filters valid card formats from messy files
"""

import re
from datetime import datetime

def extract_cards_from_junk(text):
    """
    Extract valid credit card combos from junk/messy text
    Supports multiple formats:
    - CC|MM|YY|CVV
    - CC|MM|YYYY|CVV
    - CC:MM:YY:CVV
    - CC/MM/YY/CVV
    - CC MM YY CVV
    - CC|MM|YY (no CVV)
    """
    cards = []
    seen = set()  # To avoid duplicates
    
    # Pattern 1: Standard format with separators (|, :, /, space)
    # Matches: 16digits|2digits|2-4digits|3-4digits
    pattern1 = r'(\d{15,16})[|:/\s]+(\d{1,2})[|:/\s]+(\d{2,4})[|:/\s]+(\d{3,4})'
    matches1 = re.findall(pattern1, text)
    
    for match in matches1:
        cc = match[0][:16]
        mm = match[1].zfill(2)
        yy = match[2][-2:]  # Last 2 digits
        cvv = match[3][:4]
        
        # Validate
        if validate_card_format(cc, mm, yy, cvv):
            card_str = f"{cc}|{mm}|{yy}|{cvv}"
            if card_str not in seen:
                cards.append((cc, mm, yy, cvv))
                seen.add(card_str)
    
    # Pattern 2: Cards without CVV
    # Matches: 16digits|2digits|2-4digits
    pattern2 = r'(\d{15,16})[|:/\s]+(\d{1,2})[|:/\s]+(\d{2,4})(?![|:/\s]*\d{3})'
    matches2 = re.findall(pattern2, text)
    
    for match in matches2:
        cc = match[0][:16]
        mm = match[1].zfill(2)
        yy = match[2][-2:]
        cvv = "000"  # Default CVV
        
        if validate_card_format(cc, mm, yy, cvv):
            card_str = f"{cc}|{mm}|{yy}|{cvv}"
            if card_str not in seen:
                cards.append((cc, mm, yy, cvv))
                seen.add(card_str)
    
    # Pattern 3: Continuous digits (no separators)
    # Matches: 16-19 continuous digits that might be a card
    pattern3 = r'\b(\d{15,19})\b'
    matches3 = re.findall(pattern3, text)
    
    for match in matches3:
        if len(match) >= 15:
            cc = match[:16]
            # Try to find MM/YY/CVV nearby
            # Look for 2-4 digit patterns after the card number
            nearby_pattern = re.search(rf'{re.escape(match)}\D*(\d{{1,2}})\D*(\d{{2,4}})\D*(\d{{3,4}})', text)
            
            if nearby_pattern:
                mm = nearby_pattern.group(1).zfill(2)
                yy = nearby_pattern.group(2)[-2:]
                cvv = nearby_pattern.group(3)[:4]
                
                if validate_card_format(cc, mm, yy, cvv):
                    card_str = f"{cc}|{mm}|{yy}|{cvv}"
                    if card_str not in seen:
                        cards.append((cc, mm, yy, cvv))
                        seen.add(card_str)
    
    return cards

def validate_card_format(cc, mm, yy, cvv):
    """Validate card format"""
    try:
        # Check if all are digits
        if not (cc.isdigit() and mm.isdigit() and yy.isdigit() and cvv.isdigit()):
            return False
        
        # Check lengths
        if not (15 <= len(cc) <= 16):
            return False
        if len(mm) != 2:
            return False
        if len(yy) != 2:
            return False
        if not (3 <= len(cvv) <= 4):
            return False
        
        # Check month (01-12)
        month = int(mm)
        if not (1 <= month <= 12):
            return False
        
        # Check year (not expired)
        year = int(yy)
        current_year = datetime.now().year % 100  # Last 2 digits
        if year < current_year:
            return False
        
        # Check if card passes Luhn algorithm
        if not luhn_check(cc):
            return False
        
        return True
    except:
        return False

def luhn_check(card_number):
    """Validate card number using Luhn algorithm"""
    try:
        def digits_of(n):
            return [int(d) for d in str(n)]
        
        digits = digits_of(card_number)
        odd_digits = digits[-1::-2]
        even_digits = digits[-2::-2]
        checksum = sum(odd_digits)
        
        for d in even_digits:
            checksum += sum(digits_of(d * 2))
        
        return checksum % 10 == 0
    except:
        return False

def get_card_brand(cc):
    """Detect card brand from BIN"""
    if not cc or len(cc) < 1:
        return "Unknown"
    
    first_digit = cc[0]
    first_two = cc[:2] if len(cc) >= 2 else cc[0]
    first_four = cc[:4] if len(cc) >= 4 else cc
    
    # Visa
    if first_digit == '4':
        return "VISA"
    
    # Mastercard
    if first_two in ['51', '52', '53', '54', '55'] or (2221 <= int(first_four) <= 2720):
        return "MASTERCARD"
    
    # American Express
    if first_two in ['34', '37']:
        return "AMEX"
    
    # Discover
    if first_two == '65' or first_four == '6011' or (644 <= int(first_four[:3]) <= 649):
        return "DISCOVER"
    
    # Diners Club
    if first_two in ['36', '38'] or (300 <= int(first_four[:3]) <= 305):
        return "DINERS"
    
    # JCB
    if first_four[:2] == '35':
        return "JCB"
    
    return "Unknown"

def clean_and_format_cards(cards):
    """Format cards with brand info"""
    formatted = []
    
    for cc, mm, yy, cvv in cards:
        brand = get_card_brand(cc)
        formatted.append({
            'card': f"{cc}|{mm}|{yy}|{cvv}",
            'cc': cc,
            'mm': mm,
            'yy': yy,
            'cvv': cvv,
            'brand': brand,
            'bin': cc[:6]
        })
    
    return formatted

def remove_duplicates(cards):
    """Remove duplicate cards"""
    seen = set()
    unique = []
    
    for card in cards:
        card_str = card['card']
        if card_str not in seen:
            unique.append(card)
            seen.add(card_str)
    
    return unique

def filter_by_brand(cards, brands):
    """Filter cards by brand"""
    if not brands:
        return cards
    
    brands_upper = [b.upper() for b in brands]
    return [card for card in cards if card['brand'] in brands_upper]

def sort_cards(cards, by='brand'):
    """Sort cards by brand or BIN"""
    if by == 'brand':
        return sorted(cards, key=lambda x: x['brand'])
    elif by == 'bin':
        return sorted(cards, key=lambda x: x['bin'])
    return cards

def get_statistics(cards):
    """Get statistics about extracted cards"""
    if not cards:
        return {
            'total': 0,
            'by_brand': {},
            'unique_bins': 0
        }
    
    brands = {}
    bins = set()
    
    for card in cards:
        brand = card['brand']
        brands[brand] = brands.get(brand, 0) + 1
        bins.add(card['bin'])
    
    return {
        'total': len(cards),
        'by_brand': brands,
        'unique_bins': len(bins)
    }
