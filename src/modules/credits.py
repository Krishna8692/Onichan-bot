"""
Credit-Based Economy System
Manages user credit wallets, gate-cost deductions, gifting, and voucher codes.
"""

import os
import sys
import random
import string
from datetime import datetime
from typing import Optional, Dict, Any, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from modules.database import get_connection_with_retry, _execute_with_retry, is_db_connected

GATE_CREDIT_COSTS: Dict[str, int] = {
    "pp": 1, "ss": 1, "str": 1, "stm": 2,
    "bu": 2, "sq": 2, "b3": 2, "b3n": 2, "dep": 2,
    "ast": 2, "rz": 2, "asd": 2, "anh": 2, "atf": 2, "auz": 2,
    "sor": 3, "sh6": 3, "sh8": 3, "sh10": 3, "sh13": 3,
    "st5": 3, "st12": 5,
}
DEFAULT_CREDIT_COST = 1


def init_credits_tables() -> bool:
    conn = get_connection_with_retry()
    if not conn:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS user_credits (
                    user_id BIGINT PRIMARY KEY,
                    credits INTEGER NOT NULL DEFAULT 0,
                    total_earned INTEGER NOT NULL DEFAULT 0,
                    total_spent INTEGER NOT NULL DEFAULT 0,
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS credit_vouchers (
                    id SERIAL PRIMARY KEY,
                    code VARCHAR(40) UNIQUE NOT NULL,
                    credits INTEGER NOT NULL DEFAULT 0,
                    days INTEGER NOT NULL DEFAULT 0,
                    max_uses INTEGER NOT NULL DEFAULT 1,
                    uses INTEGER NOT NULL DEFAULT 0,
                    created_by BIGINT,
                    is_active BOOLEAN DEFAULT TRUE,
                    expires_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS credit_transactions (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    amount INTEGER NOT NULL,
                    type VARCHAR(40) NOT NULL,
                    description TEXT,
                    ref_user_id BIGINT,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
        return True
    except Exception as e:
        print(f"[Credits] Table init error: {e}")
        return False


def get_balance(user_id: int) -> int:
    def _op(conn):
        with conn.cursor() as cur:
            cur.execute("SELECT credits FROM user_credits WHERE user_id = %s", (user_id,))
            row = cur.fetchone()
            return row[0] if row else 0
    result = _execute_with_retry(_op)
    return result if result is not None else 0


def add_credits(user_id: int, amount: int, tx_type: str = "add",
                description: str = "", ref_user_id: Optional[int] = None) -> bool:
    if amount <= 0:
        return False
    def _op(conn):
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO user_credits (user_id, credits, total_earned, updated_at)
                VALUES (%s, %s, %s, NOW())
                ON CONFLICT (user_id) DO UPDATE SET
                    credits = user_credits.credits + %s,
                    total_earned = user_credits.total_earned + %s,
                    updated_at = NOW()
            """, (user_id, amount, amount, amount, amount))
            cur.execute("""
                INSERT INTO credit_transactions (user_id, amount, type, description, ref_user_id)
                VALUES (%s, %s, %s, %s, %s)
            """, (user_id, amount, tx_type, description, ref_user_id))
        return True
    return bool(_execute_with_retry(_op))


def deduct_credits(user_id: int, amount: int, tx_type: str = "spend",
                   description: str = "") -> bool:
    if amount <= 0:
        return True
    def _op(conn):
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE user_credits
                SET credits = credits - %s,
                    total_spent = total_spent + %s,
                    updated_at = NOW()
                WHERE user_id = %s AND credits >= %s
            """, (amount, amount, user_id, amount))
            if cur.rowcount == 0:
                return False
            cur.execute("""
                INSERT INTO credit_transactions (user_id, amount, type, description)
                VALUES (%s, %s, %s, %s)
            """, (user_id, -amount, tx_type, description))
            return True
    result = _execute_with_retry(_op)
    return bool(result)


def transfer_credits(from_user: int, to_user: int, amount: int) -> tuple:
    if amount <= 0:
        return False, "Amount must be positive."
    balance = get_balance(from_user)
    if balance < amount:
        return False, f"Insufficient credits — you have {balance} credits."
    if from_user == to_user:
        return False, "You cannot gift credits to yourself."

    def _op(conn):
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE user_credits SET credits = credits - %s,
                    total_spent = total_spent + %s, updated_at = NOW()
                WHERE user_id = %s AND credits >= %s
            """, (amount, amount, from_user, amount))
            if cur.rowcount == 0:
                return False
            cur.execute("""
                INSERT INTO user_credits (user_id, credits, total_earned, updated_at)
                VALUES (%s, %s, %s, NOW())
                ON CONFLICT (user_id) DO UPDATE SET
                    credits = user_credits.credits + %s,
                    total_earned = user_credits.total_earned + %s,
                    updated_at = NOW()
            """, (to_user, amount, amount, amount, amount))
            cur.execute("""
                INSERT INTO credit_transactions (user_id, amount, type, description, ref_user_id)
                VALUES (%s, %s, 'transfer_out', %s, %s),
                       (%s, %s, 'transfer_in', %s, %s)
            """, (from_user, -amount, f"Gift to user {to_user}", to_user,
                  to_user, amount, f"Gift from user {from_user}", from_user))
            return True
    ok = _execute_with_retry(_op)
    return (True, "OK") if ok else (False, "Transfer failed — please try again.")


def generate_credit_voucher(credits: int, days: int = 0, max_uses: int = 1,
                            created_by: Optional[int] = None) -> Optional[str]:
    chars = string.ascii_uppercase + string.digits
    code = "CREDIT-" + "-".join("".join(random.choices(chars, k=4)) for _ in range(3))

    def _op(conn):
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO credit_vouchers (code, credits, days, max_uses, created_by)
                VALUES (%s, %s, %s, %s, %s)
            """, (code, credits, days, max_uses, created_by))
        return code
    return _execute_with_retry(_op)


def redeem_voucher(user_id: int, code: str) -> Dict[str, Any]:
    code = code.strip().upper()
    def _op(conn):
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, credits, days, max_uses, uses, is_active, expires_at
                FROM credit_vouchers WHERE code = %s
            """, (code,))
            row = cur.fetchone()
            if not row:
                return {"success": False, "message": "Invalid voucher code."}
            vid, credits, days, max_uses, uses, is_active, expires_at = row
            if not is_active:
                return {"success": False, "message": "This voucher has been deactivated."}
            if uses >= max_uses:
                return {"success": False, "message": "This voucher has already been fully redeemed."}
            if expires_at and datetime.utcnow() > expires_at:
                return {"success": False, "message": "This voucher has expired."}
            cur.execute("""
                UPDATE credit_vouchers SET uses = uses + 1,
                    is_active = CASE WHEN uses + 1 >= max_uses THEN FALSE ELSE TRUE END
                WHERE id = %s
            """, (vid,))
            return {"success": True, "credits": credits, "days": days}
    return _execute_with_retry(_op) or {"success": False, "message": "Database error."}


def get_gate_cost(gate: str) -> int:
    return GATE_CREDIT_COSTS.get(gate.lower(), DEFAULT_CREDIT_COST)


def get_transaction_history(user_id: int, limit: int = 10) -> List[Dict]:
    def _op(conn):
        with conn.cursor() as cur:
            cur.execute("""
                SELECT amount, type, description, created_at
                FROM credit_transactions WHERE user_id = %s
                ORDER BY created_at DESC LIMIT %s
            """, (user_id, limit))
            return [{"amount": r[0], "type": r[1], "description": r[2], "at": r[3]}
                    for r in cur.fetchall()]
    return _execute_with_retry(_op) or []


def get_all_vouchers(limit: int = 50) -> List[Dict]:
    def _op(conn):
        with conn.cursor() as cur:
            cur.execute("""
                SELECT code, credits, days, max_uses, uses, is_active, created_at
                FROM credit_vouchers ORDER BY created_at DESC LIMIT %s
            """, (limit,))
            return [{"code": r[0], "credits": r[1], "days": r[2],
                     "max_uses": r[3], "uses": r[4], "active": r[5], "created": r[6]}
                    for r in cur.fetchall()]
    return _execute_with_retry(_op) or []
