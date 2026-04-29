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
                    created_at     TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_mp_buyer  ON market_purchases(buyer_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_mp_seller ON market_purchases(seller_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_mp_token  ON market_purchases(download_token)")

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
                  seller_id: int | None = None) -> dict:
    offset = (page - 1) * per_page
    conditions = ["status = %s"]
    params: list = [status]

    if category and category in CATEGORIES:
        conditions.append("category = %s")
        params.append(category)
    if listing_type and listing_type in LISTING_TYPES:
        conditions.append("listing_type = %s")
        params.append(listing_type)
    if search:
        conditions.append("(title ILIKE %s OR description ILIKE %s)")
        params += [f"%{search}%", f"%{search}%"]
    if seller_id:
        conditions.append("seller_id = %s")
        params.append(seller_id)

    where = " AND ".join(conditions)
    order = {
        "newest":    "created_at DESC",
        "oldest":    "created_at ASC",
        "price_asc": "price ASC",
        "price_desc":"price DESC",
        "popular":   "views DESC",
    }.get(sort, "created_at DESC")

    def _op(conn):
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM market_listings WHERE {where}", params)
            total = (cur.fetchone() or [0])[0]
            cur.execute(
                f"SELECT id, seller_id, seller_name, title, category, listing_type, price,"
                f" starting_bid, current_bid, bid_count, product_type, status, views,"
                f" auction_end_at, created_at FROM market_listings WHERE {where}"
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
    listing = get_listing(listing_id)
    if not listing:
        return {"ok": False, "error": "Listing not found"}
    if listing["listing_type"] != "auction":
        return {"ok": False, "error": "This listing is not an auction"}
    if listing["status"] != "active":
        return {"ok": False, "error": "Auction is not active"}
    if listing["seller_id"] == bidder_id:
        return {"ok": False, "error": "You cannot bid on your own listing"}

    end = listing.get("auction_end_at")
    if end and _now() > _to_utc(end):
        return {"ok": False, "error": "Auction has ended"}

    current = float(listing["current_bid"] or listing["starting_bid"] or 0)
    if amount <= current:
        return {"ok": False, "error": f"Bid must be > {current:.0f} credits (current highest)"}

    balance = get_balance(bidder_id)
    if balance < int(amount):
        return {"ok": False, "error": f"Insufficient credits — you have {balance}"}

    # Deduct bid amount as hold
    ok = deduct_credits(bidder_id, int(amount), tx_type="bid_hold",
                        description=f"Bid hold on listing #{listing_id}")
    if not ok:
        return {"ok": False, "error": "Failed to hold credits — try again"}

    def _op(conn):
        with conn.cursor() as cur:
            # Get previous highest bidder to refund
            cur.execute("""
                SELECT id, bidder_id, amount FROM market_bids
                WHERE listing_id=%s AND hold_active=TRUE
                ORDER BY amount DESC LIMIT 1
            """, (listing_id,))
            prev = cur.fetchone()

            # Insert new bid
            cur.execute("""
                INSERT INTO market_bids (listing_id, bidder_id, bidder_name, amount)
                VALUES (%s,%s,%s,%s) RETURNING id
            """, (listing_id, bidder_id, bidder_name, amount))
            new_bid_id = cur.fetchone()[0]

            # Update listing current bid
            cur.execute("""
                UPDATE market_listings
                SET current_bid=%s, bid_count=bid_count+1
                WHERE id=%s
            """, (amount, listing_id))
            return prev, new_bid_id
    result = _execute_with_retry(_op)
    if not result:
        # Rollback hold if DB failed
        add_credits(bidder_id, int(amount), tx_type="bid_hold_refund",
                    description=f"Bid hold refund (DB error) listing #{listing_id}")
        return {"ok": False, "error": "DB error — bid hold refunded"}

    prev, new_bid_id = result
    # Refund previous highest bidder
    if prev:
        prev_bid_id, prev_bidder, prev_amount = prev
        add_credits(prev_bidder, int(prev_amount), tx_type="bid_outbid_refund",
                    description=f"Outbid refund on listing #{listing_id}")
        _mark_bid_hold_inactive(prev_bid_id)
        _notify(prev_bidder, "outbid", {"listing_id": listing_id,
                                         "listing_title": listing["title"],
                                         "new_amount": amount})
    _notify(listing["seller_id"], "new_bid", {"listing_id": listing_id,
                                               "listing_title": listing["title"],
                                               "bidder": bidder_name,
                                               "amount": amount})
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
    def _op(conn):
        with conn.cursor() as cur:
            q = "SELECT id, bidder_id, amount FROM market_bids WHERE listing_id=%s AND hold_active=TRUE"
            cur.execute(q, (listing_id,))
            return cur.fetchall()
    bids = _execute_with_retry(_op) or []
    for bid_id, bidder_id, amount in bids:
        if bid_id == winner_bid_id:
            continue   # winner's hold becomes payment
        add_credits(bidder_id, int(amount), tx_type="bid_hold_refund",
                    description=f"Bid refund on listing #{listing_id}")
        _mark_bid_hold_inactive(bid_id)


# ─── fixed-price purchase ─────────────────────────────────────────────────────
def purchase_fixed(listing_id: int, buyer_id: int) -> dict:
    listing = get_listing(listing_id)
    if not listing:
        return {"ok": False, "error": "Listing not found"}
    if listing["listing_type"] != "fixed":
        return {"ok": False, "error": "Use bidding for auction listings"}
    if listing["status"] != "active":
        return {"ok": False, "error": "Listing is not available"}
    if listing["seller_id"] == buyer_id:
        return {"ok": False, "error": "You cannot buy your own listing"}

    price = int(listing["price"])
    balance = get_balance(buyer_id)
    if balance < price:
        return {"ok": False, "error": f"Insufficient credits — you have {balance}, need {price}"}

    commission_rate = get_commission_rate()
    commission = round(price * commission_rate / 100)
    token = secrets.token_urlsafe(24)

    ok = deduct_credits(buyer_id, price, tx_type="market_purchase",
                        description=f"Purchase listing #{listing_id}: {listing['title']}")
    if not ok:
        return {"ok": False, "error": "Failed to deduct credits — try again"}

    def _op(conn):
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO market_purchases
                  (listing_id, listing_title, buyer_id, seller_id, amount, commission,
                   status, download_token)
                VALUES (%s,%s,%s,%s,%s,%s,'pending',%s) RETURNING id
            """, (listing_id, listing["title"], buyer_id, listing["seller_id"],
                  price, commission, token))
            pid = cur.fetchone()[0]
            cur.execute("UPDATE market_listings SET status='sold' WHERE id=%s", (listing_id,))
            return pid
    pid = _execute_with_retry(_op)
    if not pid:
        add_credits(buyer_id, price, tx_type="market_purchase_refund",
                    description=f"Purchase refund (DB error) listing #{listing_id}")
        return {"ok": False, "error": "DB error — credits refunded"}

    _notify(listing["seller_id"], "fixed_sale", {
        "listing_id": listing_id,
        "listing_title": listing["title"],
        "amount": price,
    })
    return {"ok": True, "purchase_id": pid, "download_token": token}


# ─── auction finalization ─────────────────────────────────────────────────────
def finalize_auction(listing_id: int) -> dict:
    listing = get_listing(listing_id)
    if not listing:
        return {"ok": False, "error": "Listing not found"}
    if listing["listing_type"] != "auction" or listing["status"] != "active":
        return {"ok": False, "error": "Not an active auction"}

    def _op(conn):
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, bidder_id, bidder_name, amount FROM market_bids
                WHERE listing_id=%s AND hold_active=TRUE
                ORDER BY amount DESC, created_at ASC LIMIT 1
            """, (listing_id,))
            return cur.fetchone()
    winner = _execute_with_retry(_op)

    if not winner:
        def _no_bids(conn):
            with conn.cursor() as cur:
                cur.execute("UPDATE market_listings SET status='ended' WHERE id=%s", (listing_id,))
        _execute_with_retry(_no_bids)
        return {"ok": True, "winner": None}

    win_bid_id, win_buyer, win_name, win_amount = winner
    win_amount = int(win_amount)
    commission_rate = get_commission_rate()
    commission = round(win_amount * commission_rate / 100)
    token = secrets.token_urlsafe(24)

    def _op2(conn):
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO market_purchases
                  (listing_id, listing_title, buyer_id, seller_id, amount, commission,
                   status, download_token)
                VALUES (%s,%s,%s,%s,%s,%s,'pending',%s) RETURNING id
            """, (listing_id, listing["title"], win_buyer, listing["seller_id"],
                  win_amount, commission, token))
            pid = cur.fetchone()[0]
            cur.execute("UPDATE market_listings SET status='sold' WHERE id=%s", (listing_id,))
            cur.execute("UPDATE market_bids SET hold_active=FALSE WHERE id=%s", (win_bid_id,))
            return pid
    pid = _execute_with_retry(_op2)

    # Refund all other bid holds
    _release_all_bid_holds(listing_id, winner_bid_id=win_bid_id)

    _notify(win_buyer, "auction_won", {
        "listing_id": listing_id,
        "listing_title": listing["title"],
        "amount": win_amount,
        "token": token,
    })
    _notify(listing["seller_id"], "auction_sold", {
        "listing_id": listing_id,
        "listing_title": listing["title"],
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
    cutoff = datetime.now(timezone.utc) - timedelta(hours=AUTOCONFIRM_HOURS)

    def _op(conn):
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, seller_id, amount, commission, listing_id, listing_title
                FROM market_purchases
                WHERE status='pending' AND created_at < %s
            """, (cutoff,))
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]
    pending = _execute_with_retry(_op) or []

    commission_rate = get_commission_rate()
    for p in pending:
        seller_payout = int(p["amount"]) - int(p["commission"])
        add_credits(p["seller_id"], seller_payout, tx_type="market_sale",
                    description=f"Sale: {p['listing_title']} (listing #{p['listing_id']})")

        def _confirm(conn, pid=p["id"]):
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE market_purchases SET status='confirmed', confirmed_at=NOW()
                    WHERE id=%s
                """, (pid,))
        _execute_with_retry(_confirm)
        _notify(p["seller_id"], "auto_confirmed", {
            "listing_title": p["listing_title"],
            "payout": seller_payout,
        })


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
                       (SELECT id FROM market_reviews WHERE purchase_id=mp.id LIMIT 1) AS reviewed
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


# ─── notifications ────────────────────────────────────────────────────────────
def _notify(user_id: int, event: str, ctx: dict):
    try:
        import requests as _req
        token = os.environ.get("BOT_TOKEN", "")
        if not token:
            return
        msgs = {
            "new_bid":      (f"🏷 <b>New Bid on Your Listing!</b>\n\n"
                             f"📦 <b>{ctx.get('listing_title','')}</b>\n"
                             f"💰 New bid: <b>{int(ctx.get('amount',0))} credits</b> by {ctx.get('bidder','')}\n"
                             f"🔗 <a href='/user/market/listing/{ctx.get('listing_id','')}'>View Listing</a>"),
            "outbid":       (f"⚡ <b>You've Been Outbid!</b>\n\n"
                             f"📦 <b>{ctx.get('listing_title','')}</b>\n"
                             f"💰 New highest bid: <b>{int(ctx.get('new_amount',0))} credits</b>\n"
                             f"Place a higher bid to stay in the race!"),
            "auction_won":  (f"🏆 <b>You Won the Auction!</b>\n\n"
                             f"📦 <b>{ctx.get('listing_title','')}</b>\n"
                             f"💰 Amount paid: <b>{int(ctx.get('amount',0))} credits</b>\n"
                             f"🔑 Your product is ready — visit the marketplace to download it."),
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
        }
        text = msgs.get(event, "")
        if not text:
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
