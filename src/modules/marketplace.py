"""
Marketplace Module — peer-to-peer digital product marketplace.
Supports fixed-price listings and auction-style bidding.
Wallet (credits) used for all transactions.
"""
from __future__ import annotations
import os
import secrets
import threading
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

from modules.database import _execute_with_retry, get_connection_with_retry, return_connection
from modules.credits import get_balance, add_credits, deduct_credits


def _run_transaction(fn):
    """Run `fn(conn, cur)` inside a real DB transaction (autocommit=False).
    Returns fn's return value on success, or raises on failure (caller handles rollback).
    Guarantees the connection is left with autocommit=True regardless of outcome.
    """
    conn = get_connection_with_retry()
    if not conn:
        raise RuntimeError("DB unavailable")
    try:
        conn.autocommit = False
        with conn.cursor() as cur:
            result = fn(conn, cur)
        conn.commit()
        return result
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        try:
            conn.autocommit = True
        except Exception:
            pass

# ─── constants ───────────────────────────────────────────────────────────────
CATEGORIES = ["Cards", "Accounts", "Combos", "Cookies", "Other"]
LISTING_TYPES = ["fixed", "auction"]
STATUSES = ["active", "sold", "cancelled", "ended"]
DEFAULT_COMMISSION = 10          # percent
AUTOCONFIRM_HOURS  = 24

_bg_thread: Optional[threading.Thread] = None
_bg_lock = threading.Lock()

# ─── table init ──────────────────────────────────────────────────────────────
def init_marketplace_tables() -> bool:
    def _op(conn):
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS market_listings (
                    id              SERIAL PRIMARY KEY,
                    seller_id       BIGINT NOT NULL,
                    seller_name     TEXT NOT NULL DEFAULT '',
                    title           TEXT NOT NULL,
                    category        TEXT NOT NULL DEFAULT 'Other',
                    description     TEXT NOT NULL DEFAULT '',
                    listing_type    TEXT NOT NULL DEFAULT 'fixed',
                    price           NUMERIC(12,2) NOT NULL DEFAULT 0,
                    starting_bid    NUMERIC(12,2),
                    current_bid     NUMERIC(12,2),
                    bid_count       INTEGER NOT NULL DEFAULT 0,
                    product_type    TEXT NOT NULL DEFAULT 'text',
                    product_content TEXT,
                    file_path       TEXT,
                    status          TEXT NOT NULL DEFAULT 'active',
                    views           INTEGER NOT NULL DEFAULT 0,
                    auction_end_at  TIMESTAMP WITH TIME ZONE,
                    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_ml_seller ON market_listings(seller_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_ml_status ON market_listings(status)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_ml_category ON market_listings(category)")

            cur.execute("""
                CREATE TABLE IF NOT EXISTS market_bids (
                    id          SERIAL PRIMARY KEY,
                    listing_id  INTEGER NOT NULL REFERENCES market_listings(id) ON DELETE CASCADE,
                    bidder_id   BIGINT NOT NULL,
                    bidder_name TEXT NOT NULL DEFAULT '',
                    amount      NUMERIC(12,2) NOT NULL,
                    hold_active BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_mb_listing ON market_bids(listing_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_mb_bidder ON market_bids(bidder_id)")

            cur.execute("""
                CREATE TABLE IF NOT EXISTS market_purchases (
                    id             SERIAL PRIMARY KEY,
                    listing_id     INTEGER NOT NULL,
                    listing_title  TEXT NOT NULL DEFAULT '',
                    buyer_id       BIGINT NOT NULL,
                    seller_id      BIGINT NOT NULL,
                    amount         NUMERIC(12,2) NOT NULL,
                    commission     NUMERIC(12,2) NOT NULL DEFAULT 0,
                    status         TEXT NOT NULL DEFAULT 'pending',
                    download_token TEXT UNIQUE,
                    confirmed_at   TIMESTAMP WITH TIME ZONE,
                    created_at     TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    dispute_reason TEXT,
                    disputed_at    TIMESTAMP WITH TIME ZONE
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_mp_buyer    ON market_purchases(buyer_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_mp_seller   ON market_purchases(seller_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_mp_token    ON market_purchases(download_token)")
            # Migration: add dispute columns to existing tables
            cur.execute("ALTER TABLE market_purchases ADD COLUMN IF NOT EXISTS dispute_reason TEXT")
            cur.execute("ALTER TABLE market_purchases ADD COLUMN IF NOT EXISTS disputed_at TIMESTAMP WITH TIME ZONE")

            cur.execute("""
                CREATE TABLE IF NOT EXISTS market_reviews (
                    id           SERIAL PRIMARY KEY,
                    purchase_id  INTEGER NOT NULL REFERENCES market_purchases(id) ON DELETE CASCADE,
                    reviewer_id  BIGINT NOT NULL,
                    seller_id    BIGINT NOT NULL,
                    rating       INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
                    comment      TEXT NOT NULL DEFAULT '',
                    created_at   TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_mr_seller ON market_reviews(seller_id)")

            cur.execute("""
                CREATE TABLE IF NOT EXISTS market_settings (
                    key   TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)
            cur.execute("""
                INSERT INTO market_settings (key, value) VALUES ('commission_rate', %s)
                ON CONFLICT (key) DO NOTHING
            """, (str(DEFAULT_COMMISSION),))
        return True
    try:
        return bool(_execute_with_retry(_op))
    except Exception as e:
        print(f"[Marketplace] Table init error: {e}")
        return False


# ─── settings ────────────────────────────────────────────────────────────────
def get_commission_rate() -> float:
    def _op(conn):
        with conn.cursor() as cur:
            cur.execute("SELECT value FROM market_settings WHERE key='commission_rate'")
            row = cur.fetchone()
            return float(row[0]) if row else float(DEFAULT_COMMISSION)
    try:
        return _execute_with_retry(_op) or float(DEFAULT_COMMISSION)
    except Exception:
        return float(DEFAULT_COMMISSION)


def set_commission_rate(rate: float) -> bool:
    def _op(conn):
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO market_settings (key, value) VALUES ('commission_rate', %s)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """, (str(rate),))
        return True
    return bool(_execute_with_retry(_op))


# ─── listings ────────────────────────────────────────────────────────────────
def create_listing(seller_id: int, seller_name: str, title: str, category: str,
                   description: str, listing_type: str, price: float,
                   product_type: str, product_content: str | None,
                   file_path: str | None, starting_bid: float | None = None,
                   auction_hours: int | None = None) -> dict:
    if listing_type not in LISTING_TYPES:
        return {"ok": False, "error": "Invalid listing type"}
    if category not in CATEGORIES:
        category = "Other"
    if listing_type == "fixed" and (price is None or price <= 0):
        return {"ok": False, "error": "Price must be > 0 for fixed listings"}
    if listing_type == "auction" and (starting_bid is None or starting_bid <= 0):
        return {"ok": False, "error": "Starting bid must be > 0 for auctions"}

    auction_end = None
    if listing_type == "auction" and auction_hours:
        auction_end = datetime.now(timezone.utc) + timedelta(hours=int(auction_hours))

    def _op(conn):
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO market_listings
                  (seller_id, seller_name, title, category, description, listing_type,
                   price, starting_bid, current_bid, product_type, product_content,
                   file_path, auction_end_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING id
            """, (seller_id, seller_name, title, category, description,
                  listing_type, price if listing_type == "fixed" else 0,
                  starting_bid, starting_bid, product_type,
                  product_content, file_path, auction_end))
            lid = cur.fetchone()[0]
            return lid
    lid = _execute_with_retry(_op)
    if lid:
        return {"ok": True, "listing_id": lid}
    return {"ok": False, "error": "DB error"}


def get_listing(listing_id: int, increment_view: bool = False) -> dict | None:
    def _op(conn):
        with conn.cursor() as cur:
            if increment_view:
                cur.execute("UPDATE market_listings SET views = views + 1 WHERE id = %s", (listing_id,))
            cur.execute("SELECT * FROM market_listings WHERE id = %s", (listing_id,))
            row = cur.fetchone()
            if not row:
                return None
            cols = [d[0] for d in cur.description]
            return dict(zip(cols, row))
    return _execute_with_retry(_op)


def list_listings(category: str | None = None, listing_type: str | None = None,
                  status: str = "active", search: str | None = None,
                  sort: str = "newest", page: int = 1, per_page: int = 20,
                  seller_id: int | None = None,
                  min_price: float | None = None, max_price: float | None = None,
                  min_rating: float | None = None) -> dict:
    offset = (page - 1) * per_page
    conditions = ["ml.status = %s"]
    params: list = [status]

    if category and category in CATEGORIES:
        conditions.append("ml.category = %s")
        params.append(category)
    if listing_type and listing_type in LISTING_TYPES:
        conditions.append("ml.listing_type = %s")
        params.append(listing_type)
    if search:
        conditions.append("(ml.title ILIKE %s OR ml.description ILIKE %s)")
        params += [f"%{search}%", f"%{search}%"]
    if seller_id:
        conditions.append("ml.seller_id = %s")
        params.append(seller_id)
    if min_price is not None:
        conditions.append("COALESCE(NULLIF(ml.current_bid,0), ml.price) >= %s")
        params.append(min_price)
    if max_price is not None:
        conditions.append("COALESCE(NULLIF(ml.current_bid,0), ml.price) <= %s")
        params.append(max_price)

    # seller rating filter — join market_reviews
    if min_rating is not None:
        conditions.append("""(
            SELECT COALESCE(AVG(r.rating),0)
            FROM market_reviews r WHERE r.seller_id = ml.seller_id
        ) >= %s""")
        params.append(min_rating)

    where = " AND ".join(conditions)
    order = {
        "newest":    "ml.created_at DESC",
        "oldest":    "ml.created_at ASC",
        "price_asc": "ml.price ASC",
        "price_desc":"ml.price DESC",
        "popular":   "ml.views DESC",
    }.get(sort, "ml.created_at DESC")

    def _op(conn):
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM market_listings ml WHERE {where}", params)
            total = (cur.fetchone() or [0])[0]
            cur.execute(
                f"SELECT ml.id, ml.seller_id, ml.seller_name, ml.title, ml.category,"
                f" ml.listing_type, ml.price, ml.starting_bid, ml.current_bid,"
                f" ml.bid_count, ml.product_type, ml.status, ml.views,"
                f" ml.auction_end_at, ml.created_at"
                f" FROM market_listings ml WHERE {where}"
                f" ORDER BY {order} LIMIT %s OFFSET %s",
                params + [per_page, offset]
            )
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
            return {"items": rows, "total": total, "page": page, "per_page": per_page}
    result = _execute_with_retry(_op)
    return result or {"items": [], "total": 0, "page": page, "per_page": per_page}


def cancel_listing(listing_id: int, user_id: int) -> dict:
    listing = get_listing(listing_id)
    if not listing:
        return {"ok": False, "error": "Listing not found"}
    if listing["seller_id"] != user_id:
        return {"ok": False, "error": "Not your listing"}
    if listing["status"] != "active":
        return {"ok": False, "error": "Listing is not active"}
    # Refund any held bids
    _release_all_bid_holds(listing_id, winner_bid_id=None)

    def _op(conn):
        with conn.cursor() as cur:
            cur.execute("UPDATE market_listings SET status='cancelled' WHERE id=%s", (listing_id,))
        return True
    _execute_with_retry(_op)
    return {"ok": True}


# ─── bidding ─────────────────────────────────────────────────────────────────
def place_bid(listing_id: int, bidder_id: int, bidder_name: str, amount: float) -> dict:
    """Place a bid on an auction listing, atomically.

    Uses a single DB transaction with SELECT … FOR UPDATE on the listing row
    to re-validate amount > current_bid under the lock, eliminating the race
    condition where two concurrent bids at the same amount could both succeed.
    Credit hold deduction and previous-bidder refund also happen inside the
    transaction, so there are no partial-state windows.
    """
    # Fast pre-checks (no locks; cheap reads before taking the row lock)
    listing = get_listing(listing_id)
    if not listing:
        return {"ok": False, "error": "Listing not found"}
    if listing["listing_type"] != "auction":
        return {"ok": False, "error": "This listing is not an auction"}
    if listing["seller_id"] == bidder_id:
        return {"ok": False, "error": "You cannot bid on your own listing"}

    amount = float(amount)
    listing_title = listing["title"]
    seller_id = listing["seller_id"]

    prev_bid_id = None
    prev_bidder = None
    prev_amount_int = 0
    new_bid_id = None
    try:
        def _txn(conn, cur):
            nonlocal prev_bid_id, prev_bidder, prev_amount_int

            # Lock listing row — forces concurrent bids to serialize
            cur.execute(
                """SELECT status, listing_type, seller_id, auction_end_at,
                          current_bid, starting_bid
                   FROM market_listings WHERE id=%s FOR UPDATE""",
                (listing_id,)
            )
            row = cur.fetchone()
            if not row:
                raise ValueError("Listing not found")

            status, ltype, s_id, end_at, current_bid, starting_bid = row
            if status != "active":
                raise ValueError("Auction is not active")
            if ltype != "auction":
                raise ValueError("This listing is not an auction")

            # Re-validate auction time under the lock
            if end_at and _now() > _to_utc(end_at):
                raise ValueError("Auction has ended")

            current = float(current_bid or starting_bid or 0)
            if amount <= current:
                raise ValueError(
                    f"Bid must be > {current:.0f} credits (current highest)"
                )

            # Deduct credits from bidder atomically (credits row lock)
            amt_int = int(amount)
            cur.execute(
                """UPDATE user_credits
                   SET credits = credits - %s,
                       total_spent = total_spent + %s,
                       updated_at = NOW()
                   WHERE user_id = %s AND credits >= %s""",
                (amt_int, amt_int, bidder_id, amt_int)
            )
            if cur.rowcount == 0:
                raise ValueError(f"Insufficient credits — need {amt_int}")
            cur.execute(
                "INSERT INTO credit_transactions (user_id, amount, type, description) VALUES (%s,%s,%s,%s)",
                (bidder_id, -amt_int, "bid_hold",
                 f"Bid hold on listing #{listing_id}")
            )

            # Find and refund previous highest bidder (inside lock)
            cur.execute(
                """SELECT id, bidder_id, amount FROM market_bids
                   WHERE listing_id=%s AND hold_active=TRUE
                   ORDER BY amount DESC LIMIT 1""",
                (listing_id,)
            )
            prev = cur.fetchone()
            if prev:
                p_bid_id, p_bidder, p_amount = prev
                prev_bid_id = p_bid_id
                prev_bidder = p_bidder
                prev_amount_int = int(p_amount)
                # Refund previous bidder atomically (upsert guards against missing row)
                cur.execute(
                    """INSERT INTO user_credits (user_id, credits, total_earned, updated_at)
                       VALUES (%s, %s, %s, NOW())
                       ON CONFLICT (user_id) DO UPDATE SET
                           credits = user_credits.credits + %s,
                           total_earned = user_credits.total_earned + %s,
                           updated_at = NOW()""",
                    (p_bidder, prev_amount_int, prev_amount_int,
                     prev_amount_int, prev_amount_int)
                )
                cur.execute(
                    "INSERT INTO credit_transactions (user_id, amount, type, description) VALUES (%s,%s,%s,%s)",
                    (p_bidder, prev_amount_int, "bid_outbid_refund",
                     f"Outbid refund on listing #{listing_id}")
                )
                cur.execute(
                    "UPDATE market_bids SET hold_active=FALSE WHERE id=%s",
                    (p_bid_id,)
                )

            # Insert new bid and update listing
            cur.execute(
                "INSERT INTO market_bids (listing_id, bidder_id, bidder_name, amount) VALUES (%s,%s,%s,%s) RETURNING id",
                (listing_id, bidder_id, bidder_name, amount)
            )
            bid_id = cur.fetchone()[0]
            cur.execute(
                "UPDATE market_listings SET current_bid=%s, bid_count=bid_count+1 WHERE id=%s",
                (amount, listing_id)
            )
            return bid_id

        new_bid_id = _run_transaction(_txn)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    except Exception as exc:
        return {"ok": False, "error": f"Transaction failed — try again ({type(exc).__name__})"}

    # Post-commit notifications (outside transaction — fire-and-forget)
    if prev_bidder:
        _notify(prev_bidder, "outbid", {
            "listing_id": listing_id,
            "listing_title": listing_title,
            "new_amount": amount,
        })
    _notify(seller_id, "new_bid", {
        "listing_id": listing_id,
        "listing_title": listing_title,
        "bidder": bidder_name,
        "amount": amount,
    })
    return {"ok": True, "bid_id": new_bid_id}


def get_listing_bids(listing_id: int, limit: int = 20) -> list:
    def _op(conn):
        with conn.cursor() as cur:
            cur.execute("""
                SELECT bidder_name, amount, created_at
                FROM market_bids WHERE listing_id=%s
                ORDER BY amount DESC LIMIT %s
            """, (listing_id, limit))
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]
    return _execute_with_retry(_op) or []


def _mark_bid_hold_inactive(bid_id: int):
    def _op(conn):
        with conn.cursor() as cur:
            cur.execute("UPDATE market_bids SET hold_active=FALSE WHERE id=%s", (bid_id,))
    _execute_with_retry(_op)


def _release_all_bid_holds(listing_id: int, winner_bid_id: int | None):
    """Refund all active bid holds for a listing (except the winner's).

    Each refund atomically credits the bidder AND deactivates the hold in
    the same DB transaction. If either step fails the transaction rolls back,
    leaving the hold active for retry (no credit-without-deactivation or
    deactivation-without-credit window).
    """
    def _find(conn):
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, bidder_id, amount FROM market_bids WHERE listing_id=%s AND hold_active=TRUE",
                (listing_id,)
            )
            return cur.fetchall()
    bids = _execute_with_retry(_find) or []

    for bid_id, bidder_id, amount in bids:
        if bid_id == winner_bid_id:
            continue   # winner's hold converts to payment

        amt_int = int(amount)
        try:
            def _txn(conn, cur, _bid_id=bid_id, _bidder=bidder_id,
                     _amt=amt_int, _lid=listing_id):
                # Deactivate hold first — if already gone, skip
                cur.execute(
                    "UPDATE market_bids SET hold_active=FALSE WHERE id=%s AND hold_active=TRUE",
                    (_bid_id,)
                )
                if cur.rowcount == 0:
                    return  # Already refunded/deactivated
                # Credit the bidder in the same transaction (upsert to handle new accounts)
                cur.execute(
                    """INSERT INTO user_credits (user_id, credits, total_earned, updated_at)
                       VALUES (%s, %s, %s, NOW())
                       ON CONFLICT (user_id) DO UPDATE SET
                           credits = user_credits.credits + %s,
                           total_earned = user_credits.total_earned + %s,
                           updated_at = NOW()""",
                    (_bidder, _amt, _amt, _amt, _amt)
                )
                cur.execute(
                    "INSERT INTO credit_transactions (user_id, amount, type, description) VALUES (%s,%s,%s,%s)",
                    (_bidder, _amt, "bid_hold_refund",
                     f"Bid refund on listing #{_lid}")
                )
            _run_transaction(_txn)
        except Exception as e:
            print(f"[Marketplace] bid hold refund error bid#{bid_id}: {e}")


# ─── fixed-price purchase ─────────────────────────────────────────────────────
def purchase_fixed(listing_id: int, buyer_id: int) -> dict:
    """Atomically purchase a fixed-price listing.

    Uses a single DB transaction with SELECT … FOR UPDATE to eliminate the
    TOCTOU race condition where two concurrent buyers could both pass the
    status='active' check and both be charged.
    """
    # Fast pre-checks outside the transaction (no locks, cheap reads)
    listing = get_listing(listing_id)
    if not listing:
        return {"ok": False, "error": "Listing not found"}
    if listing["listing_type"] != "fixed":
        return {"ok": False, "error": "Use bidding for auction listings"}
    if listing["seller_id"] == buyer_id:
        return {"ok": False, "error": "You cannot buy your own listing"}

    price = int(listing["price"])
    commission_rate = get_commission_rate()
    commission = round(price * commission_rate / 100)
    token = secrets.token_urlsafe(24)

    # Capture product fields before the transaction (avoids cursor closure issues)
    prod_type = listing.get("product_type", "text")
    prod_content = listing.get("product_content", "")
    seller_id = listing["seller_id"]
    listing_title = listing["title"]

    pid = None
    try:
        def _txn(conn, cur):
            # Lock listing row so no concurrent buyer can sneak through
            cur.execute(
                "SELECT status, price FROM market_listings WHERE id=%s FOR UPDATE",
                (listing_id,)
            )
            row = cur.fetchone()
            if not row or row[0] != "active":
                raise ValueError("Listing is not available")

            locked_price = int(row[1])

            # Atomically deduct credits (also locks the credits row)
            cur.execute(
                """UPDATE user_credits
                   SET credits = credits - %s,
                       total_spent = total_spent + %s,
                       updated_at = NOW()
                   WHERE user_id = %s AND credits >= %s""",
                (locked_price, locked_price, buyer_id, locked_price)
            )
            if cur.rowcount == 0:
                raise ValueError(f"Insufficient credits — need {locked_price}")
            cur.execute(
                "INSERT INTO credit_transactions (user_id, amount, type, description) VALUES (%s,%s,%s,%s)",
                (buyer_id, -locked_price, "market_purchase",
                 f"Purchase listing #{listing_id}: {listing_title}")
            )

            # Record purchase and mark listing sold in same transaction
            cur.execute(
                """INSERT INTO market_purchases
                     (listing_id, listing_title, buyer_id, seller_id, amount,
                      commission, status, download_token)
                   VALUES (%s,%s,%s,%s,%s,%s,'pending',%s) RETURNING id""",
                (listing_id, listing_title, buyer_id, seller_id,
                 locked_price, commission, token)
            )
            pid_inner = cur.fetchone()[0]
            cur.execute(
                "UPDATE market_listings SET status='sold' WHERE id=%s",
                (listing_id,)
            )
            return pid_inner

        pid = _run_transaction(_txn)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    except Exception as exc:
        return {"ok": False, "error": f"Transaction failed — try again ({type(exc).__name__})"}

    _notify(seller_id, "fixed_sale", {
        "listing_id": listing_id,
        "listing_title": listing_title,
        "amount": price,
    })
    _notify(buyer_id, "buyer_purchased", {
        "listing_id": listing_id,
        "listing_title": listing_title,
        "amount": price,
        "token": token,
        "product_type": prod_type,
        "product_content": prod_content,
    })
    return {"ok": True, "purchase_id": pid, "download_token": token}


# ─── auction finalization ─────────────────────────────────────────────────────
def finalize_auction(listing_id: int) -> dict:
    """Finalize an expired auction: find winner, create purchase, refund losers.

    The purchase insert + listing update + winner-bid deactivation all happen
    inside a single transaction.  Notifications and loser refunds only fire
    AFTER the transaction commits successfully.
    """
    listing = get_listing(listing_id)
    if not listing:
        return {"ok": False, "error": "Listing not found"}
    if listing["listing_type"] != "auction" or listing["status"] != "active":
        return {"ok": False, "error": "Not an active auction"}

    # Find the highest active bid
    def _find_winner(conn):
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, bidder_id, bidder_name, amount FROM market_bids
                WHERE listing_id=%s AND hold_active=TRUE
                ORDER BY amount DESC, created_at ASC LIMIT 1
            """, (listing_id,))
            return cur.fetchone()
    winner = _execute_with_retry(_find_winner)

    if not winner:
        # No bids — mark ended
        def _no_bids(conn):
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE market_listings SET status='ended' WHERE id=%s",
                    (listing_id,)
                )
        _execute_with_retry(_no_bids)
        return {"ok": True, "winner": None}

    win_bid_id, win_buyer, win_name, win_amount = winner
    win_amount = int(win_amount)
    commission_rate = get_commission_rate()
    commission = round(win_amount * commission_rate / 100)
    token = secrets.token_urlsafe(24)
    listing_title = listing["title"]
    seller_id = listing["seller_id"]

    # Atomic: lock listing, re-check status, record purchase, mark sold
    pid = None
    try:
        def _txn(conn, cur):
            # Lock listing row under the transaction — serializes concurrent finalizers
            cur.execute(
                "SELECT status FROM market_listings WHERE id=%s FOR UPDATE",
                (listing_id,)
            )
            lst_row = cur.fetchone()
            if not lst_row or lst_row[0] != "active":
                raise ValueError("Auction already finalized by another process")

            cur.execute(
                """INSERT INTO market_purchases
                     (listing_id, listing_title, buyer_id, seller_id, amount,
                      commission, status, download_token)
                   VALUES (%s,%s,%s,%s,%s,%s,'pending',%s) RETURNING id""",
                (listing_id, listing_title, win_buyer, seller_id,
                 win_amount, commission, token)
            )
            pid_inner = cur.fetchone()[0]
            # Use guarded UPDATE — only marks 'sold' if still 'active'
            cur.execute(
                "UPDATE market_listings SET status='sold' WHERE id=%s AND status='active'",
                (listing_id,)
            )
            if cur.rowcount == 0:
                raise ValueError("Listing status changed concurrently")
            cur.execute(
                "UPDATE market_bids SET hold_active=FALSE WHERE id=%s",
                (win_bid_id,)
            )
            return pid_inner

        pid = _run_transaction(_txn)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    except Exception as exc:
        return {"ok": False, "error": f"Finalization DB error: {type(exc).__name__}"}

    # Only after successful commit: refund all other bidders
    _release_all_bid_holds(listing_id, winner_bid_id=win_bid_id)

    # Notify winner with both the win headline and product content
    _notify(win_buyer, "auction_won", {
        "listing_id": listing_id,
        "listing_title": listing_title,
        "amount": win_amount,
        "token": token,
    })
    _notify(win_buyer, "buyer_purchased", {
        "listing_id": listing_id,
        "listing_title": listing_title,
        "amount": win_amount,
        "token": token,
        "product_type": listing.get("product_type", "text"),
        "product_content": listing.get("product_content", ""),
    })
    _notify(seller_id, "auction_sold", {
        "listing_id": listing_id,
        "listing_title": listing_title,
        "buyer": win_name,
        "amount": win_amount,
    })
    return {"ok": True, "winner": win_buyer, "purchase_id": pid, "token": token}


# ─── product reveal & download ────────────────────────────────────────────────
def reveal_product(download_token: str, user_id: int) -> dict:
    def _op(conn):
        with conn.cursor() as cur:
            cur.execute("""
                SELECT mp.id, mp.buyer_id, mp.listing_id, mp.status,
                       ml.product_type, ml.product_content, ml.file_path, ml.title
                FROM market_purchases mp
                JOIN market_listings ml ON ml.id = mp.listing_id
                WHERE mp.download_token = %s
            """, (download_token,))
            row = cur.fetchone()
            if not row:
                return None
            cols = [d[0] for d in cur.description]
            return dict(zip(cols, row))
    purchase = _execute_with_retry(_op)
    if not purchase:
        return {"ok": False, "error": "Invalid token"}
    if purchase["buyer_id"] != user_id:
        return {"ok": False, "error": "Access denied"}
    return {"ok": True, **purchase}


# ─── auto-confirm background thread ──────────────────────────────────────────
def _autoconfirm_loop():
    while True:
        try:
            _run_autoconfirm()
            _run_auction_finalizer()
        except Exception as e:
            print(f"[Marketplace] autoconfirm error: {e}")
        time.sleep(300)   # check every 5 minutes


def _run_autoconfirm():
    """Confirm pending purchases and pay sellers atomically.

    For each eligible purchase, a single transaction:
      1. Transitions status pending → confirmed (guarded UPDATE; skips if
         another process already confirmed it, making this fully idempotent).
      2. Credits the seller in the same transaction.

    If the transaction fails, the purchase stays 'pending' and will be
    retried on the next loop — no payout is silently dropped.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=AUTOCONFIRM_HOURS)

    def _find(conn):
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, seller_id, amount, commission, listing_id, listing_title
                FROM market_purchases
                WHERE status='pending' AND created_at < %s
                LIMIT 50
            """, (cutoff,))
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]
    pending = _execute_with_retry(_find) or []

    for p in pending:
        seller_payout = int(p["amount"]) - int(p["commission"])
        pid = p["id"]
        sid = p["seller_id"]
        listing_title = p["listing_title"]
        listing_id = p["listing_id"]

        try:
            def _txn(conn, cur, _pid=pid, _sid=sid, _payout=seller_payout,
                     _title=listing_title, _lid=listing_id):
                # Atomically claim this row; skip if already confirmed
                cur.execute(
                    """UPDATE market_purchases
                       SET status='confirmed', confirmed_at=NOW()
                       WHERE id=%s AND status='pending'""",
                    (_pid,)
                )
                if cur.rowcount == 0:
                    return None  # Already processed by another runner
                # Credit seller in the same transaction (upsert to handle new accounts)
                cur.execute(
                    """INSERT INTO user_credits (user_id, credits, total_earned, updated_at)
                       VALUES (%s, %s, %s, NOW())
                       ON CONFLICT (user_id) DO UPDATE SET
                           credits = user_credits.credits + %s,
                           total_earned = user_credits.total_earned + %s,
                           updated_at = NOW()""",
                    (_sid, _payout, _payout, _payout, _payout)
                )
                cur.execute(
                    "INSERT INTO credit_transactions (user_id, amount, type, description) VALUES (%s,%s,%s,%s)",
                    (_sid, _payout, "market_sale",
                     f"Sale: {_title} (listing #{_lid})")
                )
                return _payout

            result = _run_transaction(_txn)
            if result is not None:
                _notify(sid, "auto_confirmed", {
                    "listing_title": listing_title,
                    "payout": seller_payout,
                })
        except Exception as e:
            print(f"[Marketplace] autoconfirm error purchase#{pid}: {e}")


def _run_auction_finalizer():
    now = datetime.now(timezone.utc)

    def _op(conn):
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id FROM market_listings
                WHERE listing_type='auction' AND status='active'
                  AND auction_end_at IS NOT NULL AND auction_end_at <= %s
            """, (now,))
            return [r[0] for r in cur.fetchall()]
    ended = _execute_with_retry(_op) or []
    for lid in ended:
        finalize_auction(lid)


def start_background_thread():
    global _bg_thread
    with _bg_lock:
        if _bg_thread and _bg_thread.is_alive():
            return
        _bg_thread = threading.Thread(target=_autoconfirm_loop, daemon=True, name="marketplace-bg")
        _bg_thread.start()
        print("[Marketplace] Background thread started")


# ─── reviews ─────────────────────────────────────────────────────────────────
def submit_review(purchase_id: int, reviewer_id: int, rating: int, comment: str) -> dict:
    if not 1 <= rating <= 5:
        return {"ok": False, "error": "Rating must be 1–5"}

    def _op(conn):
        with conn.cursor() as cur:
            cur.execute("""
                SELECT buyer_id, seller_id FROM market_purchases
                WHERE id=%s AND status='confirmed'
            """, (purchase_id,))
            row = cur.fetchone()
            if not row:
                return None, "Purchase not found or not confirmed yet"
            buyer_id, seller_id = row
            if buyer_id != reviewer_id:
                return None, "Only the buyer can leave a review"
            cur.execute("SELECT id FROM market_reviews WHERE purchase_id=%s", (purchase_id,))
            if cur.fetchone():
                return None, "You have already reviewed this purchase"
            cur.execute("""
                INSERT INTO market_reviews (purchase_id, reviewer_id, seller_id, rating, comment)
                VALUES (%s,%s,%s,%s,%s) RETURNING id
            """, (purchase_id, reviewer_id, seller_id, rating, comment))
            rid = cur.fetchone()[0]
            return rid, None
    result = _execute_with_retry(_op)
    if result is None:
        return {"ok": False, "error": "DB error"}
    rid, err = result
    if err:
        return {"ok": False, "error": err}
    return {"ok": True, "review_id": rid}


def get_seller_reviews(seller_id: int, limit: int = 20) -> list:
    def _op(conn):
        with conn.cursor() as cur:
            cur.execute("""
                SELECT rating, comment, reviewer_id, created_at
                FROM market_reviews WHERE seller_id=%s
                ORDER BY created_at DESC LIMIT %s
            """, (seller_id, limit))
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]
    return _execute_with_retry(_op) or []


def get_seller_rating(seller_id: int) -> tuple[float, int]:
    def _op(conn):
        with conn.cursor() as cur:
            cur.execute("""
                SELECT AVG(rating)::NUMERIC(3,1), COUNT(*)
                FROM market_reviews WHERE seller_id=%s
            """, (seller_id,))
            row = cur.fetchone()
            return (float(row[0]) if row and row[0] else 0.0, int(row[1]) if row else 0)
    return _execute_with_retry(_op) or (0.0, 0)


# ─── seller stats ─────────────────────────────────────────────────────────────
def get_seller_stats(seller_id: int) -> dict:
    def _op(conn):
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*), status FROM market_listings WHERE seller_id=%s GROUP BY status",
                        (seller_id,))
            listing_counts = {r[1]: r[0] for r in cur.fetchall()}
            cur.execute("""
                SELECT COUNT(*), COALESCE(SUM(amount-commission),0)
                FROM market_purchases WHERE seller_id=%s AND status='confirmed'
            """, (seller_id,))
            row = cur.fetchone()
            sales_count = int(row[0]) if row else 0
            total_earned = float(row[1]) if row else 0.0
            cur.execute("""
                SELECT COUNT(*), COALESCE(SUM(amount-commission),0)
                FROM market_purchases WHERE seller_id=%s AND status='pending'
            """, (seller_id,))
            row2 = cur.fetchone()
            pending_count  = int(row2[0]) if row2 else 0
            pending_payout = float(row2[1]) if row2 else 0.0
            return {
                "listing_counts": listing_counts,
                "sales_count": sales_count,
                "total_earned": total_earned,
                "pending_count": pending_count,
                "pending_payout": pending_payout,
            }
    return _execute_with_retry(_op) or {}


def get_monthly_earnings(seller_id: int, months: int = 6) -> list:
    """Return list of {month, credits} for the last N months (oldest first)."""
    def _op(conn):
        with conn.cursor() as cur:
            interval = f"{int(months)} months"
            cur.execute("""
                SELECT TO_CHAR(created_at, 'YYYY-MM') AS mo,
                       COALESCE(SUM(amount - commission), 0) AS earned
                FROM market_purchases
                WHERE seller_id = %s AND status = 'confirmed'
                  AND created_at >= NOW() - CAST(%s AS INTERVAL)
                GROUP BY mo
                ORDER BY mo
            """, (seller_id, interval))
            return [{"month": r[0], "credits": int(r[1])} for r in cur.fetchall()]
    return _execute_with_retry(_op) or []


# ─── buyer history ────────────────────────────────────────────────────────────
def get_buyer_orders(buyer_id: int, page: int = 1, per_page: int = 20) -> dict:
    offset = (page - 1) * per_page

    def _op(conn):
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM market_purchases WHERE buyer_id=%s", (buyer_id,))
            total = (cur.fetchone() or [0])[0]
            cur.execute("""
                SELECT mp.id, mp.listing_id, mp.listing_title, mp.amount, mp.status,
                       mp.download_token, mp.created_at,
                       ml.product_type, ml.seller_name,
                       (SELECT id FROM market_reviews WHERE purchase_id=mp.id LIMIT 1) AS reviewed,
                       mp.dispute_reason, mp.disputed_at
                FROM market_purchases mp
                LEFT JOIN market_listings ml ON ml.id = mp.listing_id
                WHERE mp.buyer_id=%s
                ORDER BY mp.created_at DESC
                LIMIT %s OFFSET %s
            """, (buyer_id, per_page, offset))
            cols = [d[0] for d in cur.description]
            return {"items": [dict(zip(cols, r)) for r in cur.fetchall()],
                    "total": total, "page": page, "per_page": per_page}
    return _execute_with_retry(_op) or {"items": [], "total": 0, "page": page, "per_page": per_page}


# ─── dispute system ───────────────────────────────────────────────────────────
DISPUTE_WINDOW_HOURS = 72   # buyer may open a dispute within 72h of purchase

def open_dispute(purchase_id: int, buyer_id: int, reason: str) -> dict:
    """Buyer opens a dispute on a pending purchase (within the dispute window).

    Transitions status: pending → disputed.
    _run_autoconfirm() skips rows with status != 'pending', so disputed purchases
    are held indefinitely until an admin resolves them.
    """
    reason = (reason or "").strip()[:1000]
    if not reason:
        return {"ok": False, "error": "Please provide a reason for the dispute."}

    def _txn(conn, cur):
        cur.execute("""
            SELECT buyer_id, seller_id, status, amount, listing_title, created_at
            FROM market_purchases WHERE id=%s
        """, (purchase_id,))
        row = cur.fetchone()
        if not row:
            raise ValueError("Purchase not found.")
        db_buyer, seller_id, status, amount, listing_title, created_at = row
        if db_buyer != buyer_id:
            raise ValueError("Not authorised.")
        if status != "pending":
            raise ValueError(
                "Only pending purchases can be disputed."
                if status != "disputed" else "Already disputed."
            )
        created_utc = _to_utc(created_at)
        if _now() - created_utc > timedelta(hours=DISPUTE_WINDOW_HOURS):
            raise ValueError(
                f"Dispute window has closed ({DISPUTE_WINDOW_HOURS}h after purchase)."
            )
        cur.execute(
            """UPDATE market_purchases
               SET status='disputed', dispute_reason=%s, disputed_at=NOW()
               WHERE id=%s AND status='pending'""",
            (reason, purchase_id)
        )
        if cur.rowcount == 0:
            raise ValueError("Purchase status changed — please refresh.")
        return {"seller_id": seller_id, "listing_title": listing_title, "amount": float(amount)}

    try:
        info = _run_transaction(_txn)
        if info:
            _notify(info["seller_id"], "dispute_opened", {
                "listing_title": info["listing_title"],
                "amount": info["amount"],
                "purchase_id": purchase_id,
            })
        return {"ok": True}
    except ValueError as e:
        return {"ok": False, "error": str(e)}


def get_disputed_purchases(limit: int = 100) -> list:
    """Return all disputed purchases for the admin panel."""
    def _op(conn):
        with conn.cursor() as cur:
            cur.execute("""
                SELECT mp.id, mp.listing_id, mp.listing_title, mp.buyer_id,
                       mp.seller_id, mp.amount, mp.dispute_reason, mp.disputed_at,
                       mp.created_at
                FROM market_purchases mp
                WHERE mp.status='disputed'
                ORDER BY mp.disputed_at DESC
                LIMIT %s
            """, (limit,))
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]
    return _execute_with_retry(_op) or []


def admin_resolve_dispute_release(purchase_id: int) -> dict:
    """Admin: resolve dispute in seller's favour — confirm purchase and pay seller."""
    try:
        def _txn(conn, cur):
            cur.execute(
                """SELECT seller_id, amount, commission, listing_title, listing_id
                   FROM market_purchases WHERE id=%s AND status='disputed'""",
                (purchase_id,)
            )
            row = cur.fetchone()
            if not row:
                raise ValueError("Purchase not found or not disputed.")
            seller_id, amount, commission, listing_title, listing_id = row
            seller_payout = int(amount) - int(commission)

            cur.execute(
                """UPDATE market_purchases
                   SET status='confirmed', confirmed_at=NOW()
                   WHERE id=%s AND status='disputed'""",
                (purchase_id,)
            )
            if cur.rowcount == 0:
                raise ValueError("Dispute status changed — please refresh.")

            # Credit seller (upsert)
            cur.execute(
                """INSERT INTO user_credits (user_id, credits, total_earned, updated_at)
                   VALUES (%s, %s, %s, NOW())
                   ON CONFLICT (user_id) DO UPDATE SET
                       credits = user_credits.credits + %s,
                       total_earned = user_credits.total_earned + %s,
                       updated_at = NOW()""",
                (seller_id, seller_payout, seller_payout, seller_payout, seller_payout)
            )
            cur.execute(
                "INSERT INTO credit_transactions (user_id, amount, type, description) VALUES (%s,%s,%s,%s)",
                (seller_id, seller_payout, "dispute_resolved_seller",
                 f"Dispute resolved (seller): {listing_title} (#{listing_id})")
            )
            return {"seller_id": seller_id, "listing_title": listing_title, "payout": seller_payout}

        info = _run_transaction(_txn)
        if info:
            _notify(info["seller_id"], "dispute_resolved_seller", {
                "listing_title": info["listing_title"],
                "payout": info["payout"],
            })
        return {"ok": True}
    except ValueError as e:
        return {"ok": False, "error": str(e)}


def admin_resolve_dispute_refund(purchase_id: int) -> dict:
    """Admin: resolve dispute in buyer's favour — refund buyer and void purchase."""
    try:
        def _txn(conn, cur):
            cur.execute(
                """SELECT buyer_id, seller_id, amount, listing_title, listing_id
                   FROM market_purchases WHERE id=%s AND status='disputed'""",
                (purchase_id,)
            )
            row = cur.fetchone()
            if not row:
                raise ValueError("Purchase not found or not disputed.")
            buyer_id, seller_id, amount, listing_title, listing_id = row
            refund_amt = int(amount)

            cur.execute(
                """UPDATE market_purchases
                   SET status='refunded', confirmed_at=NOW()
                   WHERE id=%s AND status='disputed'""",
                (purchase_id,)
            )
            if cur.rowcount == 0:
                raise ValueError("Dispute status changed — please refresh.")

            # Refund buyer (upsert)
            cur.execute(
                """INSERT INTO user_credits (user_id, credits, total_earned, updated_at)
                   VALUES (%s, %s, %s, NOW())
                   ON CONFLICT (user_id) DO UPDATE SET
                       credits = user_credits.credits + %s,
                       total_earned = user_credits.total_earned + %s,
                       updated_at = NOW()""",
                (buyer_id, refund_amt, refund_amt, refund_amt, refund_amt)
            )
            cur.execute(
                "INSERT INTO credit_transactions (user_id, amount, type, description) VALUES (%s,%s,%s,%s)",
                (buyer_id, refund_amt, "dispute_refund",
                 f"Dispute refund: {listing_title} (#{listing_id})")
            )
            return {
                "buyer_id": buyer_id,
                "seller_id": seller_id,
                "listing_title": listing_title,
                "refund": refund_amt,
            }

        info = _run_transaction(_txn)
        if info:
            _notify(info["buyer_id"], "dispute_resolved_buyer", {
                "listing_title": info["listing_title"],
                "refund": info["refund"],
            })
            _notify(info["seller_id"], "dispute_resolved_seller_loss", {
                "listing_title": info["listing_title"],
            })
        return {"ok": True}
    except ValueError as e:
        return {"ok": False, "error": str(e)}


# ─── admin stats ──────────────────────────────────────────────────────────────
def get_admin_market_stats() -> dict:
    def _op(conn):
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*), status FROM market_listings GROUP BY status")
            listing_counts = {r[1]: r[0] for r in cur.fetchall()}
            cur.execute("SELECT COUNT(*), COALESCE(SUM(amount),0), COALESCE(SUM(commission),0) FROM market_purchases")
            row = cur.fetchone()
            return {
                "listing_counts": listing_counts,
                "total_sales": int(row[0]) if row else 0,
                "total_volume": float(row[1]) if row else 0.0,
                "total_commission": float(row[2]) if row else 0.0,
            }
    return _execute_with_retry(_op) or {}


def admin_list_listings(search: str | None = None, status_filter: str | None = None,
                        page: int = 1, per_page: int = 30) -> dict:
    offset = (page - 1) * per_page
    conditions, params = [], []
    if status_filter and status_filter in STATUSES:
        conditions.append("status = %s"); params.append(status_filter)
    if search:
        conditions.append("(title ILIKE %s OR seller_name ILIKE %s)")
        params += [f"%{search}%", f"%{search}%"]
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    def _op(conn):
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM market_listings {where}", params)
            total = (cur.fetchone() or [0])[0]
            cur.execute(
                f"SELECT id, seller_id, seller_name, title, category, listing_type,"
                f" price, current_bid, bid_count, status, views, created_at"
                f" FROM market_listings {where} ORDER BY created_at DESC LIMIT %s OFFSET %s",
                params + [per_page, offset]
            )
            cols = [d[0] for d in cur.description]
            return {"items": [dict(zip(cols, r)) for r in cur.fetchall()],
                    "total": total, "page": page, "per_page": per_page}
    return _execute_with_retry(_op) or {"items": [], "total": 0, "page": page, "per_page": per_page}


def admin_remove_listing(listing_id: int) -> dict:
    listing = get_listing(listing_id)
    if not listing:
        return {"ok": False, "error": "Not found"}
    _release_all_bid_holds(listing_id, winner_bid_id=None)

    def _op(conn):
        with conn.cursor() as cur:
            cur.execute("UPDATE market_listings SET status='cancelled' WHERE id=%s", (listing_id,))
    _execute_with_retry(_op)
    return {"ok": True}


def admin_reinstate_listing(listing_id: int) -> dict:
    """Reinstate a cancelled or ended listing back to active status."""
    listing = get_listing(listing_id)
    if not listing:
        return {"ok": False, "error": "Not found"}
    if listing["status"] not in ("cancelled", "ended"):
        return {"ok": False, "error": "Only cancelled or ended listings can be reinstated"}

    def _op(conn):
        with conn.cursor() as cur:
            cur.execute("UPDATE market_listings SET status='active' WHERE id=%s", (listing_id,))
    _execute_with_retry(_op)
    return {"ok": True}


def get_active_auctions() -> list:
    """Return all active auction listings ordered by soonest ending first."""
    def _op(conn):
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, title, seller_name, starting_bid, current_bid,
                       bid_count, auction_end_at, views
                FROM market_listings
                WHERE listing_type='auction' AND status='active'
                ORDER BY auction_end_at ASC NULLS LAST
            """)
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]
    return _execute_with_retry(_op) or []


# ─── notifications ────────────────────────────────────────────────────────────
def _get_base_url() -> str:
    """Return the primary public base URL for this deployment (no trailing slash)."""
    domains = os.environ.get("REPLIT_DOMAINS", "")
    if domains:
        primary = domains.split(",")[0].strip()
        if primary:
            return f"https://{primary}"
    dev = os.environ.get("REPLIT_DEV_DOMAIN", "")
    if dev:
        return f"https://{dev}"
    return ""


def _notify(user_id: int, event: str, ctx: dict):
    try:
        import requests as _req
        token = os.environ.get("BOT_TOKEN", "")
        if not token:
            return
        base = _get_base_url()
        lid = ctx.get("listing_id", "")
        listing_url = f"{base}/user/market/listing/{lid}" if base and lid else ""
        view_link = f'\n🔗 <a href="{listing_url}">View Listing</a>' if listing_url else ""
        msgs = {
            "new_bid":      (f"🏷 <b>New Bid on Your Listing!</b>\n\n"
                             f"📦 <b>{ctx.get('listing_title','')}</b>\n"
                             f"💰 New bid: <b>{int(ctx.get('amount',0))} credits</b> by {ctx.get('bidder','')}"
                             + view_link),
            "outbid":       (f"⚡ <b>You've Been Outbid!</b>\n\n"
                             f"📦 <b>{ctx.get('listing_title','')}</b>\n"
                             f"💰 New highest bid: <b>{int(ctx.get('new_amount',0))} credits</b>\n"
                             f"Place a higher bid to stay in the race!"),
            "auction_won":  (f"🏆 <b>You Won the Auction!</b>\n\n"
                             f"📦 <b>{ctx.get('listing_title','')}</b>\n"
                             f"💰 Amount paid: <b>{int(ctx.get('amount',0))} credits</b>\n"
                             f"🔑 Your product is ready — check Telegram for delivery or visit the marketplace."
                             + view_link),
            "buyer_purchased": "__SPECIAL__",
            "auction_sold": (f"✅ <b>Your Auction Sold!</b>\n\n"
                             f"📦 <b>{ctx.get('listing_title','')}</b>\n"
                             f"👤 Buyer: {ctx.get('buyer','')}\n"
                             f"💰 Amount: <b>{int(ctx.get('amount',0))} credits</b>\n"
                             f"⏳ Payout releases in {AUTOCONFIRM_HOURS}h automatically."),
            "fixed_sale":   (f"✅ <b>Your Listing Was Purchased!</b>\n\n"
                             f"📦 <b>{ctx.get('listing_title','')}</b>\n"
                             f"💰 Amount: <b>{int(ctx.get('amount',0))} credits</b>\n"
                             f"⏳ Payout releases in {AUTOCONFIRM_HOURS}h automatically."),
            "auto_confirmed":(f"💰 <b>Payout Released!</b>\n\n"
                              f"📦 <b>{ctx.get('listing_title','')}</b>\n"
                              f"✅ <b>{int(ctx.get('payout',0))} credits</b> have been added to your balance."),
            "dispute_opened": (f"⚠️ <b>Dispute Opened on Your Sale!</b>\n\n"
                               f"📦 <b>{ctx.get('listing_title','')}</b>\n"
                               f"💰 Amount: <b>{int(ctx.get('amount',0))} credits</b>\n"
                               f"An admin will review the dispute. Funds are held pending resolution."),
            "dispute_resolved_seller": (f"✅ <b>Dispute Resolved — Funds Released to You!</b>\n\n"
                                        f"📦 <b>{ctx.get('listing_title','')}</b>\n"
                                        f"💰 <b>{int(ctx.get('payout',0))} credits</b> have been added to your balance."),
            "dispute_resolved_buyer":  (f"✅ <b>Dispute Resolved — Refund Issued!</b>\n\n"
                                        f"📦 <b>{ctx.get('listing_title','')}</b>\n"
                                        f"💰 <b>{int(ctx.get('refund',0))} credits</b> have been refunded to your balance."),
            "dispute_resolved_seller_loss": (f"❌ <b>Dispute Resolved — Refund Issued to Buyer</b>\n\n"
                                             f"📦 <b>{ctx.get('listing_title','')}</b>\n"
                                             f"The admin ruled in the buyer's favour. No payout will be released."),
        }
        text = msgs.get(event, "")
        if not text:
            return

        if text == "__SPECIAL__":
            # buyer_purchased: deliver product via DM
            prod_type = ctx.get("product_type", "text")
            prod_content = ctx.get("product_content", "")
            title = ctx.get("listing_title", "")
            amount = int(ctx.get("amount", 0))
            token_dl = ctx.get("token", "")

            # Build delivery line depending on product type
            if prod_type == "text" and prod_content:
                delivery_line = "📋 <b>Your product content is below:</b>"
            elif token_dl and base:
                dl_url = f"{base}/user/market/download/{token_dl}"
                delivery_line = f'📁 <b>Download your file:</b> <a href="{dl_url}">{dl_url}</a>'
            elif token_dl:
                delivery_line = f"📁 <b>Your download token:</b> <code>{token_dl}</code>"
            else:
                delivery_line = "📁 Visit the marketplace to access your file."

            header = (
                f"🎉 <b>Purchase Successful!</b>\n\n"
                f"📦 <b>{title}</b>\n"
                f"💰 Amount paid: <b>{amount} credits</b>\n\n"
                + delivery_line
            )
            _req.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": user_id, "text": header,
                      "parse_mode": "HTML", "disable_web_page_preview": False},
                timeout=6,
            )
            if prod_type == "text" and prod_content:
                # Send content in 4000-char chunks inside <pre> blocks
                chunks = [prod_content[i:i+4000]
                          for i in range(0, len(prod_content), 4000)]
                for chunk in chunks:
                    _req.post(
                        f"https://api.telegram.org/bot{token}/sendMessage",
                        json={"chat_id": user_id,
                              "text": f"<pre>{chunk}</pre>",
                              "parse_mode": "HTML",
                              "disable_web_page_preview": True},
                        timeout=6,
                    )
            return

        _req.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": user_id, "text": text,
                  "parse_mode": "HTML", "disable_web_page_preview": True},
            timeout=6,
        )
    except Exception:
        pass


# ─── helpers ──────────────────────────────────────────────────────────────────
def _now() -> datetime:
    return datetime.now(timezone.utc)


def _to_utc(dt) -> datetime:
    if dt is None:
        return _now()
    if hasattr(dt, "tzinfo") and dt.tzinfo:
        return dt.astimezone(timezone.utc)
    return dt.replace(tzinfo=timezone.utc)


def time_left_str(auction_end) -> str:
    if not auction_end:
        return ""
    end = _to_utc(auction_end)
    now = _now()
    if now >= end:
        return "Ended"
    delta = end - now
    h, rem = divmod(int(delta.total_seconds()), 3600)
    m = rem // 60
    if h >= 24:
        return f"{h//24}d {h%24}h left"
    if h:
        return f"{h}h {m}m left"
    return f"{m}m left"
