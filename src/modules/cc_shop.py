import re
import json
import os
import base64
import hashlib
from datetime import datetime
from cryptography.fernet import Fernet, InvalidToken
from modules.database import _execute_with_retry, is_db_connected, get_connection_with_retry
from modules.bin_lookup import lookup_bin

_SECRET = os.environ.get("SESSION_SECRET", "")
if not _SECRET:
    raise RuntimeError("SESSION_SECRET environment variable is required for CC Shop encryption")
_FERNET_KEY = base64.urlsafe_b64encode(hashlib.sha256(_SECRET.encode()).digest())
_fernet = Fernet(_FERNET_KEY)

_LEGACY_KEY = _SECRET[:32].ljust(32, '0').encode('utf-8')

def _legacy_xor_decrypt(data: str) -> str:
    try:
        encrypted = base64.b64decode(data)
        decrypted = bytes([b ^ _LEGACY_KEY[i % len(_LEGACY_KEY)] for i, b in enumerate(encrypted)])
        return decrypted.decode('utf-8')
    except:
        return data

def _xor_encrypt(data: str) -> str:
    return _fernet.encrypt(data.encode('utf-8')).decode('utf-8')

def _xor_decrypt(data: str) -> str:
    try:
        return _fernet.decrypt(data.encode('utf-8')).decode('utf-8')
    except (InvalidToken, Exception):
        return _legacy_xor_decrypt(data)

import hmac
def _card_fingerprint(cc, mm, yy, cvv):
    canonical = f"{cc}|{mm}|{yy}|{cvv}"
    return hmac.new(_SECRET.encode(), canonical.encode(), hashlib.sha256).hexdigest()


def parse_cc_line(line):
    line = line.strip()
    if not line or line.startswith('#'):
        return None
    line = line.replace('/', '|').replace(' ', '|').replace('\t', '|').replace(',', '|')
    parts = [p.strip() for p in line.split('|') if p.strip()]
    if len(parts) < 4:
        return None
    cc = re.sub(r'\D', '', parts[0])
    mm = re.sub(r'\D', '', parts[1])
    yy = re.sub(r'\D', '', parts[2])
    cvv = re.sub(r'\D', '', parts[3])
    if len(cc) < 13 or len(cc) > 19:
        return None
    if len(mm) != 2 or int(mm) < 1 or int(mm) > 12:
        return None
    if len(yy) == 4:
        yy = yy[2:]
    if len(yy) != 2:
        return None
    if len(cvv) < 3 or len(cvv) > 4:
        return None
    return {'cc': cc, 'mm': mm, 'yy': yy, 'cvv': cvv}


def bulk_upload_cards(lines, default_price=5.00):
    parsed = []
    skipped = 0
    duplicates = 0

    for line in lines:
        card = parse_cc_line(line)
        if not card:
            skipped += 1
            continue
        parsed.append(card)

    if not parsed:
        return {'added': 0, 'skipped': skipped, 'duplicates': 0}

    rules = get_price_rules()
    added = 0
    for card in parsed:
        bin_info = lookup_bin(card['cc'][:6])
        enc_cc = _xor_encrypt(card['cc'])
        enc_cvv = _xor_encrypt(card['cvv'])
        fp = _card_fingerprint(card['cc'], card['mm'], card['yy'], card['cvv'])
        bin6 = card['cc'][:6]
        c_code = bin_info.get('country_code', 'XX')
        c_name = bin_info.get('country', 'Unknown')
        brand = bin_info.get('brand', 'Unknown')

        card_price = default_price
        best_priority = -1
        for r in rules:
            rt = r['rule_type']
            tgt = r['target']
            p = float(r['price'])
            if rt == 'bin' and bin6.startswith(tgt) and best_priority < 3:
                card_price = p
                best_priority = 3
            elif rt == 'brand' and brand.upper() == tgt.upper() and best_priority < 2:
                card_price = p
                best_priority = 2
            elif rt == 'country' and (c_code.upper() == tgt.upper() or c_name.upper() == tgt.upper()) and best_priority < 1:
                card_price = p
                best_priority = 1

        result = _execute_with_retry("""
            INSERT INTO cc_shop_stock (cc_number, mm, yy, cvv, bin6, country, country_code, brand, card_type, card_level, bank, price, status, card_fingerprint)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'available', %s)
            ON CONFLICT (card_fingerprint) DO NOTHING
        """, (
            enc_cc, card['mm'], card['yy'], enc_cvv,
            bin6, c_name, c_code, brand,
            bin_info.get('type', 'Unknown'),
            bin_info.get('level', ''),
            bin_info.get('bank', 'Unknown'),
            card_price,
            fp
        ), return_rowcount=True)
        if result and result > 0:
            added += 1
        else:
            duplicates += 1

    return {'added': added, 'skipped': skipped, 'duplicates': duplicates}


def get_shop_stats():
    result = _execute_with_retry("""
        SELECT 
            COUNT(*) FILTER (WHERE status = 'available') as available,
            COUNT(*) FILTER (WHERE status = 'sold') as sold,
            COUNT(*) FILTER (WHERE status = 'removed') as removed,
            COUNT(*) as total,
            COALESCE(SUM(price) FILTER (WHERE status = 'sold'), 0) as revenue
        FROM cc_shop_stock
    """, fetch_one=True)
    if result:
        return {
            'available': result.get('available', 0) or 0,
            'sold': result.get('sold', 0) or 0,
            'removed': result.get('removed', 0) or 0,
            'total': result.get('total', 0) or 0,
            'revenue': float(result.get('revenue', 0) or 0)
        }
    return {'available': 0, 'sold': 0, 'removed': 0, 'total': 0, 'revenue': 0}


def get_available_cards(country=None, brand=None, card_type=None, bank=None, bin_prefix=None, page=1, per_page=50):
    conditions = ["status = 'available'"]
    params = []

    if country:
        conditions.append("(LOWER(country) LIKE %s OR LOWER(country_code) = %s)")
        params.append(f"%{country.lower()}%")
        params.append(country.lower().strip())
    if brand:
        conditions.append("LOWER(brand) LIKE %s")
        params.append(f"%{brand.lower()}%")
    if card_type:
        conditions.append("LOWER(card_type) LIKE %s")
        params.append(f"%{card_type.lower()}%")
    if bank:
        conditions.append("LOWER(bank) LIKE %s")
        params.append(f"%{bank.lower()}%")
    if bin_prefix:
        conditions.append("bin6 LIKE %s")
        params.append(f"{bin_prefix}%")

    where = " AND ".join(conditions)
    offset = (page - 1) * per_page

    count_result = _execute_with_retry(
        f"SELECT COUNT(*) as cnt FROM cc_shop_stock WHERE {where}", params, fetch_one=True
    )
    total = count_result.get('cnt', 0) if count_result else 0

    cards = _execute_with_retry(
        f"SELECT id, bin6, country, country_code, brand, card_type, card_level, bank, price, uploaded_at FROM cc_shop_stock WHERE {where} ORDER BY uploaded_at DESC LIMIT %s OFFSET %s",
        params + [per_page, offset], fetch=True
    )

    return {
        'cards': cards or [],
        'total': total,
        'page': page,
        'per_page': per_page,
        'pages': (total + per_page - 1) // per_page if total > 0 else 1
    }


def get_all_stock(country=None, brand=None, card_type=None, bank=None, status=None, page=1, per_page=50):
    conditions = ["1=1"]
    params = []

    if country:
        conditions.append("LOWER(country) LIKE %s")
        params.append(f"%{country.lower()}%")
    if brand:
        conditions.append("LOWER(brand) LIKE %s")
        params.append(f"%{brand.lower()}%")
    if card_type:
        conditions.append("LOWER(card_type) LIKE %s")
        params.append(f"%{card_type.lower()}%")
    if bank:
        conditions.append("LOWER(bank) LIKE %s")
        params.append(f"%{bank.lower()}%")
    if status:
        conditions.append("status = %s")
        params.append(status)

    where = " AND ".join(conditions)
    offset = (page - 1) * per_page

    count_result = _execute_with_retry(
        f"SELECT COUNT(*) as cnt FROM cc_shop_stock WHERE {where}", params, fetch_one=True
    )
    total = count_result.get('cnt', 0) if count_result else 0

    cards = _execute_with_retry(
        f"SELECT * FROM cc_shop_stock WHERE {where} ORDER BY uploaded_at DESC LIMIT %s OFFSET %s",
        params + [per_page, offset], fetch=True
    )

    return {
        'cards': cards or [],
        'total': total,
        'page': page,
        'pages': (total + per_page - 1) // per_page if total > 0 else 1
    }


def purchase_card(user_id, card_id, holder_info):
    from psycopg2.extras import RealDictCursor
    conn = get_connection_with_retry()
    if not conn:
        return {'error': 'Database connection failed'}

    old_autocommit = conn.autocommit
    try:
        conn.autocommit = False

        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM cc_shop_stock WHERE id = %s AND status = 'available' FOR UPDATE",
                (card_id,)
            )
            card = cur.fetchone()
            if not card:
                conn.rollback()
                return {'error': 'Card not available or already sold'}

            price = float(card['price'])

            cur.execute(
                "SELECT shop_balance FROM users WHERE user_id = %s FOR UPDATE",
                (user_id,)
            )
            user = cur.fetchone()
            if not user:
                conn.rollback()
                return {'error': 'User not found'}

            balance = float(user.get('shop_balance', 0) or 0)
            if balance < price:
                conn.rollback()
                return {'error': f'Insufficient balance. Need ${price:.2f}, have ${balance:.2f}'}

            cur.execute(
                "UPDATE users SET shop_balance = shop_balance - %s, updated_at = NOW() WHERE user_id = %s",
                (price, user_id)
            )

            cur.execute(
                "UPDATE cc_shop_stock SET status = 'sold', sold_to = %s, sold_at = NOW() WHERE id = %s AND status = 'available'",
                (user_id, card_id)
            )
            if cur.rowcount == 0:
                conn.rollback()
                return {'error': 'Card was sold to another buyer'}

            cur.execute("""
                INSERT INTO cc_shop_purchases (user_id, card_id, price, holder_name, holder_email, holder_phone, holder_address)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                user_id, card_id, price,
                holder_info.get('name', ''),
                holder_info.get('email', ''),
                holder_info.get('phone', ''),
                holder_info.get('address', '')
            ))

        conn.commit()

        card['cc_number'] = _xor_decrypt(card['cc_number'])
        card['cvv'] = _xor_decrypt(card['cvv'])

        return {
            'success': True,
            'card': card,
            'price': price,
            'new_balance': balance - price,
            'holder': holder_info
        }
    except Exception as e:
        try:
            conn.rollback()
        except:
            pass
        return {'error': f'Purchase failed: {str(e)}'}
    finally:
        conn.autocommit = old_autocommit


def get_purchased_cards(user_id, page=1, per_page=20):
    offset = (page - 1) * per_page

    count_result = _execute_with_retry(
        "SELECT COUNT(*) as cnt FROM cc_shop_purchases WHERE user_id = %s",
        (user_id,), fetch_one=True
    )
    total = count_result.get('cnt', 0) if count_result else 0

    cards = _execute_with_retry("""
        SELECT p.*, s.cc_number, s.mm, s.yy, s.cvv, s.bin6, s.country, s.country_code, s.brand, s.card_type, s.card_level, s.bank
        FROM cc_shop_purchases p
        JOIN cc_shop_stock s ON p.card_id = s.id
        WHERE p.user_id = %s
        ORDER BY p.purchased_at DESC
        LIMIT %s OFFSET %s
    """, (user_id, per_page, offset), fetch=True)

    decrypted = []
    for c in (cards or []):
        c = dict(c)
        c['cc_number'] = _xor_decrypt(c.get('cc_number', ''))
        c['cvv'] = _xor_decrypt(c.get('cvv', ''))
        decrypted.append(c)

    return {
        'cards': decrypted,
        'total': total,
        'page': page,
        'pages': (total + per_page - 1) // per_page if total > 0 else 1
    }


def get_user_balance(user_id):
    result = _execute_with_retry(
        "SELECT shop_balance FROM users WHERE user_id = %s",
        (user_id,), fetch_one=True
    )
    if result:
        return float(result.get('shop_balance', 0) or 0)
    return 0.0


def add_user_balance(user_id, amount):
    result = _execute_with_retry("""
        INSERT INTO users (user_id, shop_balance, created_at, updated_at)
        VALUES (%s, %s, NOW(), NOW())
        ON CONFLICT (user_id) DO UPDATE SET
            shop_balance = COALESCE(users.shop_balance, 0) + %s,
            updated_at = NOW()
    """, (user_id, max(0, amount), amount), return_rowcount=True)
    return result and result > 0


def set_user_balance(user_id, amount):
    result = _execute_with_retry("""
        INSERT INTO users (user_id, shop_balance, created_at, updated_at)
        VALUES (%s, %s, NOW(), NOW())
        ON CONFLICT (user_id) DO UPDATE SET
            shop_balance = %s,
            updated_at = NOW()
    """, (user_id, amount, amount), return_rowcount=True)
    return result and result > 0


def delete_cards(card_ids):
    if not card_ids:
        return 0
    placeholders = ','.join(['%s'] * len(card_ids))
    result = _execute_with_retry(
        f"DELETE FROM cc_shop_stock WHERE id IN ({placeholders}) AND status = 'available'",
        card_ids, return_rowcount=True
    )
    return result or 0


def remove_cards(card_ids):
    if not card_ids:
        return 0
    placeholders = ','.join(['%s'] * len(card_ids))
    result = _execute_with_retry(
        f"UPDATE cc_shop_stock SET status = 'removed' WHERE id IN ({placeholders}) AND status = 'available'",
        card_ids, return_rowcount=True
    )
    return result or 0


def clear_all_stock(only_available=False):
    if only_available:
        result = _execute_with_retry(
            "DELETE FROM cc_shop_stock WHERE status = 'available'",
            return_rowcount=True
        )
    else:
        _execute_with_retry("DELETE FROM cc_shop_purchases")
        result = _execute_with_retry(
            "DELETE FROM cc_shop_stock",
            return_rowcount=True
        )
    return result or 0


def get_shop_setting(key, default=None):
    result = _execute_with_retry(
        "SELECT value FROM cc_shop_settings WHERE key = %s",
        (key,), fetch_one=True
    )
    if result:
        return result.get('value', default)
    return default


def set_shop_setting(key, value):
    return _execute_with_retry("""
        INSERT INTO cc_shop_settings (key, value, updated_at)
        VALUES (%s, %s, NOW())
        ON CONFLICT (key) DO UPDATE SET value = %s, updated_at = NOW()
    """, (key, value, value))


def get_default_price():
    val = get_shop_setting('default_price', '5.00')
    try:
        return float(val)
    except:
        return 5.00


def set_default_price(price):
    return set_shop_setting('default_price', str(price))


def update_card_price(card_id, price):
    return _execute_with_retry(
        "UPDATE cc_shop_stock SET price = %s WHERE id = %s",
        (price, card_id)
    )


def update_bin_price(bin_prefix, price):
    result = _execute_with_retry(
        "UPDATE cc_shop_stock SET price = %s WHERE bin6 LIKE %s AND status = 'available'",
        (price, f"{bin_prefix}%"), return_rowcount=True
    )
    return result or 0


def update_country_price(country, price):
    result = _execute_with_retry(
        "UPDATE cc_shop_stock SET price = %s WHERE (LOWER(country) = %s OR LOWER(country_code) = %s) AND status = 'available'",
        (price, country.lower().strip(), country.lower().strip()), return_rowcount=True
    )
    return result or 0


def update_brand_price(brand, price):
    result = _execute_with_retry(
        "UPDATE cc_shop_stock SET price = %s WHERE LOWER(brand) = %s AND status = 'available'",
        (price, brand.lower().strip()), return_rowcount=True
    )
    return result or 0


def add_price_rule(rule_type, target, price):
    target_val = target.strip().upper() if rule_type == 'country' else target.strip()
    if rule_type == 'bin':
        target_val = target_val.strip()[:6]
    elif rule_type == 'brand':
        target_val = target_val.upper()
    return _execute_with_retry("""
        INSERT INTO cc_shop_price_rules (rule_type, target, price, created_at)
        VALUES (%s, %s, %s, NOW())
        ON CONFLICT (rule_type, target) DO UPDATE SET price = %s, created_at = NOW()
    """, (rule_type, target_val, price, price))


def remove_price_rule(rule_id):
    return _execute_with_retry(
        "DELETE FROM cc_shop_price_rules WHERE id = %s",
        (rule_id,), return_rowcount=True
    )


def get_price_rules():
    return _execute_with_retry(
        "SELECT * FROM cc_shop_price_rules ORDER BY rule_type, target",
        fetch=True
    ) or []


def get_price_for_card(bin6='', country_code='', country='', brand=''):
    rules = get_price_rules()
    best_price = None
    best_priority = -1
    for r in rules:
        rt = r['rule_type']
        tgt = r['target']
        p = float(r['price'])
        if rt == 'bin' and bin6.startswith(tgt):
            if best_priority < 3:
                best_price = p
                best_priority = 3
        elif rt == 'brand' and brand.upper() == tgt.upper():
            if best_priority < 2:
                best_price = p
                best_priority = 2
        elif rt == 'country' and (country_code.upper() == tgt.upper() or country.upper() == tgt.upper()):
            if best_priority < 1:
                best_price = p
                best_priority = 1
    return best_price


def apply_price_rules_to_stock():
    rules = get_price_rules()
    priority_order = {'country': 0, 'brand': 1, 'bin': 2}
    sorted_rules = sorted(rules, key=lambda r: priority_order.get(r['rule_type'], -1))
    total = 0
    for r in sorted_rules:
        rt = r['rule_type']
        tgt = r['target']
        p = float(r['price'])
        if rt == 'bin':
            cnt = update_bin_price(tgt, p)
        elif rt == 'country':
            cnt = update_country_price(tgt, p)
        elif rt == 'brand':
            cnt = update_brand_price(tgt, p)
        else:
            cnt = 0
        total += cnt
    return total


def get_stock_summary():
    result = _execute_with_retry("""
        SELECT country, country_code, brand, COUNT(*) as count, AVG(price) as avg_price
        FROM cc_shop_stock
        WHERE status = 'available'
        GROUP BY country, country_code, brand
        ORDER BY count DESC
    """, fetch=True)
    return result or []


def get_filter_options():
    countries = _execute_with_retry("""
        SELECT DISTINCT country, country_code FROM cc_shop_stock WHERE status = 'available' ORDER BY country
    """, fetch=True) or []
    brands = _execute_with_retry("""
        SELECT DISTINCT brand FROM cc_shop_stock WHERE status = 'available' ORDER BY brand
    """, fetch=True) or []
    types = _execute_with_retry("""
        SELECT DISTINCT card_type FROM cc_shop_stock WHERE status = 'available' ORDER BY card_type
    """, fetch=True) or []
    banks = _execute_with_retry("""
        SELECT DISTINCT bank FROM cc_shop_stock WHERE status = 'available' ORDER BY bank LIMIT 50
    """, fetch=True) or []

    return {
        'countries': [{'name': c['country'], 'code': c['country_code']} for c in countries],
        'brands': [b['brand'] for b in brands],
        'types': [t['card_type'] for t in types],
        'banks': [b['bank'] for b in banks]
    }


def get_purchase_history(page=1, per_page=50):
    offset = (page - 1) * per_page
    count_result = _execute_with_retry(
        "SELECT COUNT(*) as cnt FROM cc_shop_purchases", fetch_one=True
    )
    total = count_result.get('cnt', 0) if count_result else 0

    purchases = _execute_with_retry("""
        SELECT p.*, s.bin6, s.country, s.brand, s.card_type, s.bank
        FROM cc_shop_purchases p
        JOIN cc_shop_stock s ON p.card_id = s.id
        ORDER BY p.purchased_at DESC
        LIMIT %s OFFSET %s
    """, (per_page, offset), fetch=True)

    return {
        'purchases': purchases or [],
        'total': total,
        'page': page,
        'pages': (total + per_page - 1) // per_page if total > 0 else 1
    }


def get_profit_percentage():
    val = get_shop_setting('profit_percentage', '0')
    try:
        return float(val)
    except:
        return 0.0


def set_profit_percentage(pct):
    return set_shop_setting('profit_percentage', str(pct))


def get_refund_window_minutes():
    val = get_shop_setting('refund_window_minutes', '5')
    try:
        return int(float(val))
    except:
        return 5


def set_refund_window_minutes(minutes):
    return set_shop_setting('refund_window_minutes', str(int(minutes)))


_DEFAULT_NON_REFUNDABLE = ["JP Morgan Chase", "Capital One"]


def get_non_refundable_banks():
    import json as _json
    val = get_shop_setting('non_refundable_banks', None)
    if val:
        try:
            return _json.loads(val)
        except:
            pass
    return list(_DEFAULT_NON_REFUNDABLE)


def set_non_refundable_banks(banks_list):
    import json as _json
    return set_shop_setting('non_refundable_banks', _json.dumps(banks_list))


def add_non_refundable_bank(bank_name):
    banks = get_non_refundable_banks()
    bank_name = bank_name.strip()
    if bank_name and bank_name not in banks:
        banks.append(bank_name)
        set_non_refundable_banks(banks)
    return banks


def remove_non_refundable_bank(bank_name):
    banks = get_non_refundable_banks()
    banks = [b for b in banks if b != bank_name]
    set_non_refundable_banks(banks)
    return banks


def is_bank_non_refundable(bank_name):
    if not bank_name:
        return False
    blocked = get_non_refundable_banks()
    bank_lower = bank_name.lower()
    for b in blocked:
        if b.lower() in bank_lower or bank_lower in b.lower():
            return True
    return False


def refund_purchase(purchase_id, user_id):
    from psycopg2.extras import RealDictCursor
    from datetime import datetime, timezone
    conn = get_connection_with_retry()
    if not conn:
        return {'error': 'Database connection failed'}

    old_autocommit = conn.autocommit
    try:
        conn.autocommit = False
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """SELECT p.*, s.bank FROM cc_shop_purchases p
                   JOIN cc_shop_stock s ON p.card_id = s.id
                   WHERE p.id = %s AND p.user_id = %s FOR UPDATE OF p""",
                (purchase_id, user_id)
            )
            purchase = cur.fetchone()
            if not purchase:
                conn.rollback()
                return {'error': 'Purchase not found'}

            if purchase.get('refunded'):
                conn.rollback()
                return {'error': 'Already refunded'}

            bank_name = purchase.get('bank', '') or ''
            if is_bank_non_refundable(bank_name):
                cur.execute(
                    "UPDATE cc_shop_purchases SET refunded = TRUE, refund_amount = 0, refunded_at = NOW(), refund_denial_reason = %s WHERE id = %s",
                    ('non_refundable_bank', purchase_id)
                )
                conn.commit()
                return {'error': 'non_refundable_bank', 'denied': True, 'bank': bank_name}

            window_min = get_refund_window_minutes()
            purchased_at = purchase.get('purchased_at')
            if purchased_at:
                if purchased_at.tzinfo is None:
                    purchased_at = purchased_at.replace(tzinfo=timezone.utc)
                now = datetime.now(timezone.utc)
                elapsed = (now - purchased_at).total_seconds()
                if elapsed > window_min * 60:
                    cur.execute(
                        "UPDATE cc_shop_purchases SET refunded = TRUE, refund_amount = 0, refunded_at = NOW(), refund_denial_reason = %s WHERE id = %s",
                        ('window_expired', purchase_id)
                    )
                    conn.commit()
                    return {'error': 'window_expired', 'denied': True, 'window_minutes': window_min, 'elapsed_seconds': int(elapsed)}

            price = float(purchase['price'])
            profit_pct = get_profit_percentage()
            fee = price * (profit_pct / 100.0)
            refund_amount = max(0, price - fee)

            if refund_amount > 0:
                cur.execute(
                    "UPDATE users SET shop_balance = COALESCE(shop_balance, 0) + %s WHERE user_id = %s",
                    (refund_amount, user_id)
                )

            cur.execute(
                "UPDATE cc_shop_purchases SET refunded = TRUE, refund_amount = %s, refunded_at = NOW() WHERE id = %s",
                (refund_amount, purchase_id)
            )

            conn.commit()
            return {
                'success': True,
                'refund_amount': refund_amount,
                'fee': fee,
                'profit_pct': profit_pct
            }
    except Exception as e:
        try:
            conn.rollback()
        except:
            pass
        return {'error': str(e)}
    finally:
        try:
            conn.autocommit = old_autocommit
        except:
            pass


def create_shop_deposit_invoice(user_id, username, amount):
    from modules.oxapay import OXAPAY_API_KEY, OXAPAY_API_URL
    import requests as _requests

    if not OXAPAY_API_KEY:
        return {'error': 'OxaPay API key not configured'}

    try:
        amount = float(amount)
        if amount < 1:
            return {'error': 'Minimum deposit is $1'}
    except:
        return {'error': 'Invalid amount'}

    order_id = f"SHOPBAL-{user_id}-{int(datetime.now().timestamp())}"

    headers = {
        'merchant_api_key': OXAPAY_API_KEY,
        'Content-Type': 'application/json'
    }

    invoice_data = {
        "amount": amount,
        "currency": "USD",
        "lifetime": 60,
        "fee_paid_by_payer": 1,
        "under_paid_coverage": 2.5,
        "order_id": order_id,
        "description": f"Onichan CC Shop - ${amount} balance deposit for @{username}",
        "thanks_message": f"Thank you! ${amount} will be added to your shop balance shortly.",
        "sandbox": False
    }

    try:
        response = _requests.post(OXAPAY_API_URL, json=invoice_data, headers=headers, timeout=30)
        if response.status_code != 200:
            return {'error': f'API error ({response.status_code})'}

        result = response.json()
        api_status = result.get("status")
        data = result.get("data", {})

        if api_status == 200 and data:
            track_id = data.get("track_id")
            payment_url = data.get("payment_url")
        elif result.get("result") == 100:
            track_id = result.get("trackId") or result.get("track_id")
            payment_url = result.get("payLink") or result.get("payment_url")
        else:
            return {'error': result.get('message', 'Unknown error')}

        _execute_with_retry("""
            INSERT INTO cc_shop_deposits (user_id, username, amount, order_id, track_id, payment_url, status)
            VALUES (%s, %s, %s, %s, %s, %s, 'pending')
        """, (user_id, username, amount, order_id, track_id, payment_url))

        return {
            'success': True,
            'order_id': order_id,
            'track_id': track_id,
            'payment_url': payment_url,
            'amount': amount
        }
    except _requests.exceptions.RequestException as e:
        return {'error': f'Request failed: {str(e)}'}


def check_pending_deposits():
    from modules.oxapay import check_payment_status
    pending = _execute_with_retry(
        "SELECT * FROM cc_shop_deposits WHERE status = 'pending'",
        fetch=True
    ) or []

    confirmed = 0
    for dep in pending:
        track_id = dep.get('track_id')
        if not track_id:
            continue
        try:
            status_data = check_payment_status(track_id)
            pay_status = str(status_data.get('status', '') or status_data.get('state', '')).lower()
            if pay_status in ('paid', 'confirmed', 'complete', 'completed', 'sending'):
                amount = float(dep['amount'])
                user_id = dep['user_id']
                add_user_balance(user_id, amount)
                _execute_with_retry(
                    "UPDATE cc_shop_deposits SET status = 'confirmed', confirmed_at = NOW() WHERE id = %s",
                    (dep['id'],)
                )
                confirmed += 1
                print(f"[Shop] Deposit confirmed: ${amount} for user {user_id}")
            elif pay_status in ('expired', 'failed', 'canceled'):
                _execute_with_retry(
                    "UPDATE cc_shop_deposits SET status = %s WHERE id = %s",
                    (pay_status, dep['id'])
                )
        except Exception as e:
            print(f"[Shop] Deposit check error: {e}")

    return confirmed
