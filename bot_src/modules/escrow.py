"""
Escrow Service — peer-to-peer credit escrow for safe trading.
Buyer locks credits → seller confirms deal → credits released.
Admin can intervene at any stage.
"""

import os
import sys
from datetime import datetime, timedelta
from typing import Optional, Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from modules.database import _execute_with_retry, get_connection_with_retry


def init_escrow_tables() -> bool:
    conn = get_connection_with_retry()
    if not conn:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS escrow_deals (
                    id SERIAL PRIMARY KEY,
                    deal_id VARCHAR(12) UNIQUE NOT NULL,
                    buyer_id BIGINT NOT NULL,
                    seller_id BIGINT,
                    credits INTEGER NOT NULL,
                    description TEXT,
                    status VARCHAR(20) NOT NULL DEFAULT 'open',
                    buyer_confirmed BOOLEAN DEFAULT FALSE,
                    seller_confirmed BOOLEAN DEFAULT FALSE,
                    dispute BOOLEAN DEFAULT FALSE,
                    expires_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT NOW(),
                    completed_at TIMESTAMP
                )
            """)
        return True
    except Exception as e:
        print(f"[Escrow] Table init error: {e}")
        return False


def _gen_deal_id() -> str:
    import random, string
    return "ESC-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=8))


def create_deal(buyer_id: int, credits: int, description: str,
                seller_id: Optional[int] = None) -> Optional[Dict]:
    """Buyer locks credits into escrow. Returns deal info."""
    from modules.credits import get_balance, deduct_credits
    balance = get_balance(buyer_id)
    if balance < credits:
        return {"error": f"Insufficient credits — you have {balance}."}
    deal_id = _gen_deal_id()
    expires = datetime.utcnow() + timedelta(days=3)

    def _op(conn):
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO escrow_deals
                    (deal_id, buyer_id, seller_id, credits, description, expires_at)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (deal_id, buyer_id, seller_id, credits, description, expires))
        return True
    ok = _execute_with_retry(_op)
    if not ok:
        return {"error": "Database error."}
    deducted = deduct_credits(buyer_id, credits, "escrow_lock",
                              f"Escrow #{deal_id}")
    if not deducted:
        return {"error": "Failed to lock credits."}
    return {"deal_id": deal_id, "credits": credits, "expires": expires}


def get_deal(deal_id: str) -> Optional[Dict]:
    def _op(conn):
        with conn.cursor() as cur:
            cur.execute("""
                SELECT deal_id, buyer_id, seller_id, credits, description,
                       status, buyer_confirmed, seller_confirmed, dispute, expires_at, created_at
                FROM escrow_deals WHERE deal_id=%s
            """, (deal_id.upper(),))
            row = cur.fetchone()
            if not row:
                return None
            return {
                "deal_id": row[0], "buyer_id": row[1], "seller_id": row[2],
                "credits": row[3], "description": row[4], "status": row[5],
                "buyer_confirmed": row[6], "seller_confirmed": row[7],
                "dispute": row[8], "expires": row[9], "created": row[10]
            }
    return _execute_with_retry(_op)


def join_deal(deal_id: str, seller_id: int) -> tuple:
    deal = get_deal(deal_id)
    if not deal:
        return False, "Deal not found."
    if deal["status"] != "open":
        return False, f"Deal is already {deal['status']}."
    if deal["seller_id"] and deal["seller_id"] != seller_id:
        return False, "This deal is reserved for a specific seller."
    if deal["buyer_id"] == seller_id:
        return False, "You cannot be both buyer and seller."

    def _op(conn):
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE escrow_deals SET seller_id=%s, status='active'
                WHERE deal_id=%s AND status='open'
            """, (seller_id, deal_id.upper()))
            return cur.rowcount > 0
    ok = _execute_with_retry(_op)
    return (True, "Joined deal.") if ok else (False, "Could not join deal.")


def confirm_deal(deal_id: str, user_id: int) -> tuple:
    deal = get_deal(deal_id)
    if not deal:
        return False, "Deal not found."
    if deal["status"] not in ("active",):
        return False, f"Deal status is '{deal['status']}' — cannot confirm."
    if user_id not in (deal["buyer_id"], deal["seller_id"]):
        return False, "You are not part of this deal."

    is_buyer = user_id == deal["buyer_id"]
    field = "buyer_confirmed" if is_buyer else "seller_confirmed"

    def _op(conn):
        with conn.cursor() as cur:
            cur.execute(f"""
                UPDATE escrow_deals SET {field}=TRUE WHERE deal_id=%s
            """, (deal_id.upper(),))
            cur.execute("""
                SELECT buyer_confirmed, seller_confirmed FROM escrow_deals WHERE deal_id=%s
            """, (deal_id.upper(),))
            row = cur.fetchone()
            return row
    row = _execute_with_retry(_op)
    if not row:
        return False, "Database error."

    buyer_ok, seller_ok = row
    if buyer_ok and seller_ok:
        return _release_deal(deal_id, deal["seller_id"], deal["credits"])
    side = "Buyer" if is_buyer else "Seller"
    return True, f"{side} confirmed. Waiting for the other party."


def _release_deal(deal_id: str, seller_id: int, credits: int) -> tuple:
    from modules.credits import add_credits
    def _op(conn):
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE escrow_deals SET status='completed', completed_at=NOW()
                WHERE deal_id=%s
            """, (deal_id.upper(),))
        return True
    ok = _execute_with_retry(_op)
    if ok:
        add_credits(seller_id, credits, "escrow_release",
                    f"Escrow #{deal_id} completed")
        return True, f"✅ Deal complete! {credits} credits released to seller."
    return False, "Release failed — contact admin."


def dispute_deal(deal_id: str, user_id: int) -> tuple:
    deal = get_deal(deal_id)
    if not deal:
        return False, "Deal not found."
    if user_id not in (deal["buyer_id"], deal["seller_id"]):
        return False, "You are not part of this deal."
    if deal["status"] != "active":
        return False, "Only active deals can be disputed."

    def _op(conn):
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE escrow_deals SET dispute=TRUE, status='disputed' WHERE deal_id=%s
            """, (deal_id.upper(),))
        return True
    ok = _execute_with_retry(_op)
    return (True, "Dispute raised. Admin will review.") if ok else (False, "Error.")


def admin_resolve_deal(deal_id: str, winner: str) -> tuple:
    """winner = 'buyer' or 'seller'"""
    deal = get_deal(deal_id)
    if not deal:
        return False, "Deal not found."
    if deal["status"] != "disputed":
        return False, "Deal is not in dispute."
    from modules.credits import add_credits
    if winner == "seller":
        add_credits(deal["seller_id"], deal["credits"], "escrow_admin_release",
                    f"Admin resolved #{deal_id} — seller wins")
        msg = f"Credits ({deal['credits']}) sent to seller."
    else:
        add_credits(deal["buyer_id"], deal["credits"], "escrow_refund",
                    f"Admin resolved #{deal_id} — buyer refunded")
        msg = f"Credits ({deal['credits']}) refunded to buyer."

    def _op(conn):
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE escrow_deals SET status='resolved', completed_at=NOW() WHERE deal_id=%s
            """, (deal_id.upper(),))
        return True
    ok = _execute_with_retry(_op)
    return (True, msg) if ok else (False, "DB error.")


def get_user_deals(user_id: int, limit: int = 10) -> List[Dict]:
    def _op(conn):
        with conn.cursor() as cur:
            cur.execute("""
                SELECT deal_id, buyer_id, seller_id, credits, description, status, created_at
                FROM escrow_deals
                WHERE buyer_id=%s OR seller_id=%s
                ORDER BY created_at DESC LIMIT %s
            """, (user_id, user_id, limit))
            return [{"id": r[0], "buyer": r[1], "seller": r[2], "credits": r[3],
                     "desc": r[4], "status": r[5], "created": r[6]}
                    for r in cur.fetchall()]
    return _execute_with_retry(_op) or []


def get_disputed_deals() -> List[Dict]:
    def _op(conn):
        with conn.cursor() as cur:
            cur.execute("""
                SELECT deal_id, buyer_id, seller_id, credits, description, created_at
                FROM escrow_deals WHERE status='disputed' ORDER BY created_at DESC
            """)
            return [{"id": r[0], "buyer": r[1], "seller": r[2], "credits": r[3],
                     "desc": r[4], "created": r[5]}
                    for r in cur.fetchall()]
    return _execute_with_retry(_op) or []
