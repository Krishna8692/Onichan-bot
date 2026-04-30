import json
import os
import base64
import hashlib
from datetime import datetime
from cryptography.fernet import Fernet, InvalidToken
from modules.database import _execute_with_retry, get_connection_with_retry

_SECRET = os.environ.get("SESSION_SECRET", "")
if not _SECRET:
    raise RuntimeError("SESSION_SECRET environment variable is required for BIN Shop encryption")
_FERNET_KEY = base64.urlsafe_b64encode(hashlib.sha256(_SECRET.encode()).digest())
_fernet = Fernet(_FERNET_KEY)


def _enc(data: str) -> str:
    if not data:
        return _fernet.encrypt(b"").decode("utf-8")
    return _fernet.encrypt(data.encode("utf-8")).decode("utf-8")


def _dec(data: str) -> str:
    if not data:
        return ""
    try:
        return _fernet.decrypt(data.encode("utf-8")).decode("utf-8")
    except (InvalidToken, Exception):
        return ""


def init_bin_shop_tables():
    _execute_with_retry("""
        CREATE TABLE IF NOT EXISTS bin_shop_listings (
            id SERIAL PRIMARY KEY,
            bin_encrypted TEXT NOT NULL,
            brand_encrypted TEXT NOT NULL,
            level_encrypted TEXT NOT NULL,
            bank_encrypted TEXT NOT NULL,
            country VARCHAR(64),
            country_code VARCHAR(8),
            card_type VARCHAR(32),
            price NUMERIC(10,2) DEFAULT 5.00,
            sites_encrypted TEXT NOT NULL,
            method_note_encrypted TEXT NOT NULL,
            has_method BOOLEAN DEFAULT FALSE,
            public_description TEXT,
            status VARCHAR(16) DEFAULT 'available',
            sold_count INT DEFAULT 0,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    _execute_with_retry("""
        CREATE TABLE IF NOT EXISTS bin_shop_purchases (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            listing_id INT REFERENCES bin_shop_listings(id),
            price_paid NUMERIC(10,2),
            purchased_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(user_id, listing_id)
        )
    """)


try:
    init_bin_shop_tables()
except Exception:
    pass


def create_bin_listing(bin_number, brand, country, country_code, card_type,
                       card_level, bank, price, sites, method_note, public_description):
    """
    sites: list of dicts [{name, url, description, success_rate}]
    method_note: plain text string (can be empty)
    """
    bin_enc = _enc(str(bin_number).strip())
    brand_enc = _enc(str(brand).strip())
    level_enc = _enc(str(card_level).strip())
    bank_enc = _enc(str(bank).strip())
    sites_enc = _enc(json.dumps(sites))
    note = str(method_note).strip()
    note_enc = _enc(note)
    has_method = bool(note)

    result = _execute_with_retry("""
        INSERT INTO bin_shop_listings
            (bin_encrypted, brand_encrypted, level_encrypted, bank_encrypted,
             country, country_code, card_type, price,
             sites_encrypted, method_note_encrypted, has_method, public_description)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        RETURNING id
    """, (
        bin_enc, brand_enc, level_enc, bank_enc,
        str(country).strip(), str(country_code).strip().upper(), str(card_type).strip(),
        float(price),
        sites_enc, note_enc, has_method, str(public_description).strip()
    ), fetch_one=True)
    return result.get('id') if result else None


def get_bin_listings(page=1, per_page=20, filters=None):
    if filters is None:
        filters = {}
    conditions = ["status = 'available'"]
    params = []

    if filters.get('country'):
        conditions.append("LOWER(country) LIKE %s")
        params.append(f"%{filters['country'].lower()}%")
    if filters.get('card_type'):
        conditions.append("LOWER(card_type) LIKE %s")
        params.append(f"%{filters['card_type'].lower()}%")

    where = " AND ".join(conditions)
    offset = (page - 1) * per_page

    count = _execute_with_retry(
        f"SELECT COUNT(*) as cnt FROM bin_shop_listings WHERE {where}",
        params, fetch_one=True
    )
    total = (count.get('cnt', 0) or 0) if count else 0

    rows = _execute_with_retry(f"""
        SELECT id, country, country_code, card_type, price,
               has_method, public_description, sold_count,
               sites_encrypted
        FROM bin_shop_listings
        WHERE {where}
        ORDER BY created_at DESC
        LIMIT %s OFFSET %s
    """, params + [per_page, offset], fetch=True)

    listings = []
    for r in (rows or []):
        r = dict(r)
        r['display_bin'] = 'x' * 7
        r['display_brand'] = '—'
        r['display_level'] = '—'
        r['display_bank'] = '—'
        try:
            sites = json.loads(_dec(r.get('sites_encrypted', '')))
            r['site_count'] = len(sites)
            r['site_names'] = [s.get('name', '') for s in sites if s.get('name')]
        except Exception:
            r['site_count'] = 0
            r['site_names'] = []
        r.pop('sites_encrypted', None)
        listings.append(r)

    return {
        'listings': listings,
        'total': total,
        'page': page,
        'pages': max(1, (total + per_page - 1) // per_page)
    }


def get_purchased_bin_ids(user_id):
    rows = _execute_with_retry(
        "SELECT listing_id FROM bin_shop_purchases WHERE user_id = %s",
        (user_id,), fetch=True
    )
    return {r['listing_id'] for r in (rows or [])}


def buy_bin(user_id, listing_id):
    from psycopg2.extras import RealDictCursor
    conn = get_connection_with_retry()
    if not conn:
        raise ValueError("Database connection failed")

    old_autocommit = conn.autocommit
    try:
        conn.autocommit = False
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM bin_shop_listings WHERE id = %s AND status = 'available' FOR UPDATE",
                (listing_id,)
            )
            listing = cur.fetchone()
            if not listing:
                conn.rollback()
                raise ValueError("BIN listing not available")

            cur.execute(
                "SELECT 1 FROM bin_shop_purchases WHERE user_id = %s AND listing_id = %s",
                (user_id, listing_id)
            )
            if cur.fetchone():
                conn.rollback()
                raise ValueError("You already own this BIN")

            price = float(listing['price'])
            cur.execute(
                "SELECT shop_balance FROM users WHERE user_id = %s FOR UPDATE",
                (user_id,)
            )
            user = cur.fetchone()
            if not user:
                conn.rollback()
                raise ValueError("User not found")

            balance = float(user.get('shop_balance', 0) or 0)
            if balance < price:
                conn.rollback()
                raise ValueError(f"Insufficient balance. Need ${price:.2f}, have ${balance:.2f}")

            cur.execute(
                "UPDATE users SET shop_balance = shop_balance - %s, updated_at = NOW() WHERE user_id = %s",
                (price, user_id)
            )
            cur.execute(
                "INSERT INTO bin_shop_purchases (user_id, listing_id, price_paid) VALUES (%s, %s, %s)",
                (user_id, listing_id, price)
            )
            cur.execute(
                "UPDATE bin_shop_listings SET sold_count = sold_count + 1 WHERE id = %s",
                (listing_id,)
            )

        conn.commit()

        listing = dict(listing)
        listing['bin_number'] = _dec(listing.get('bin_encrypted', ''))
        listing['brand'] = _dec(listing.get('brand_encrypted', ''))
        listing['card_level'] = _dec(listing.get('level_encrypted', ''))
        listing['bank'] = _dec(listing.get('bank_encrypted', ''))
        try:
            listing['sites'] = json.loads(_dec(listing.get('sites_encrypted', '')))
        except Exception:
            listing['sites'] = []
        listing['method_note'] = _dec(listing.get('method_note_encrypted', ''))
        listing['price_paid'] = price
        listing['new_balance'] = balance - price
        return listing

    except ValueError:
        raise
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        raise ValueError(f"Purchase failed: {str(e)}")
    finally:
        conn.autocommit = old_autocommit


def get_purchased_bins(user_id):
    rows = _execute_with_retry("""
        SELECT l.*, p.price_paid, p.purchased_at as bought_at
        FROM bin_shop_purchases p
        JOIN bin_shop_listings l ON p.listing_id = l.id
        WHERE p.user_id = %s
        ORDER BY p.purchased_at DESC
    """, (user_id,), fetch=True)

    result = []
    for r in (rows or []):
        r = dict(r)
        r['bin_number'] = _dec(r.get('bin_encrypted', ''))
        r['brand'] = _dec(r.get('brand_encrypted', ''))
        r['card_level'] = _dec(r.get('level_encrypted', ''))
        r['bank'] = _dec(r.get('bank_encrypted', ''))
        try:
            r['sites'] = json.loads(_dec(r.get('sites_encrypted', '')))
        except Exception:
            r['sites'] = []
        r['method_note'] = _dec(r.get('method_note_encrypted', ''))
        result.append(r)
    return result


def remove_bin_listing(listing_id):
    _execute_with_retry(
        "UPDATE bin_shop_listings SET status = 'removed' WHERE id = %s",
        (listing_id,)
    )


def get_all_bin_listings_admin():
    rows = _execute_with_retry("""
        SELECT id, country, country_code, card_type, price,
               has_method, public_description, sold_count, status, created_at
        FROM bin_shop_listings
        ORDER BY created_at DESC
    """, fetch=True)
    result = []
    for r in (rows or []):
        r = dict(r)
        r['display_bin'] = 'x' * 7
        result.append(r)
    return result


def parse_sites_textarea(text):
    """Parse sites from textarea: one per line: Name | https://url | notes | 94%"""
    sites = []
    for line in text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split('|')]
        if len(parts) >= 2:
            sites.append({
                'name': parts[0] if len(parts) > 0 else '',
                'url': parts[1] if len(parts) > 1 else '',
                'description': parts[2] if len(parts) > 2 else '',
                'success_rate': parts[3] if len(parts) > 3 else '',
            })
    return sites


def sites_to_textarea(sites):
    """Convert a sites list back to the textarea format: Name | url | notes | rate"""
    lines = []
    for s in (sites or []):
        parts = [
            str(s.get('name', '') or ''),
            str(s.get('url', '') or ''),
            str(s.get('description', '') or ''),
            str(s.get('success_rate', '') or ''),
        ]
        lines.append(' | '.join(parts))
    return '\n'.join(lines)


def get_bin_listing_for_edit(listing_id):
    """Return a single listing with all fields decrypted for the admin edit form."""
    row = _execute_with_retry(
        "SELECT * FROM bin_shop_listings WHERE id = %s",
        (listing_id,), fetch_one=True
    )
    if not row:
        return None
    r = dict(row)
    r['bin_number'] = _dec(r.get('bin_encrypted', ''))
    r['brand'] = _dec(r.get('brand_encrypted', ''))
    r['card_level'] = _dec(r.get('level_encrypted', ''))
    r['bank'] = _dec(r.get('bank_encrypted', ''))
    try:
        r['sites'] = json.loads(_dec(r.get('sites_encrypted', '')))
    except Exception:
        r['sites'] = []
    r['method_note'] = _dec(r.get('method_note_encrypted', ''))
    return r


def update_bin_listing(listing_id, bin_number, brand, country, country_code,
                       card_type, card_level, bank, price, sites, method_note,
                       public_description):
    """Update an existing BIN listing, re-encrypting all sensitive fields."""
    bin_enc = _enc(str(bin_number).strip())
    brand_enc = _enc(str(brand).strip())
    level_enc = _enc(str(card_level).strip())
    bank_enc = _enc(str(bank).strip())
    sites_enc = _enc(json.dumps(sites))
    note = str(method_note).strip()
    note_enc = _enc(note)
    has_method = bool(note)

    _execute_with_retry("""
        UPDATE bin_shop_listings
        SET bin_encrypted = %s,
            brand_encrypted = %s,
            level_encrypted = %s,
            bank_encrypted = %s,
            country = %s,
            country_code = %s,
            card_type = %s,
            price = %s,
            sites_encrypted = %s,
            method_note_encrypted = %s,
            has_method = %s,
            public_description = %s
        WHERE id = %s
    """, (
        bin_enc, brand_enc, level_enc, bank_enc,
        str(country).strip(), str(country_code).strip().upper(), str(card_type).strip(),
        float(price),
        sites_enc, note_enc, has_method, str(public_description).strip(),
        listing_id
    ))
