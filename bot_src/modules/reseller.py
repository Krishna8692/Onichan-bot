"""
Reseller / White-Label Sub-Account System
Resellers can onboard clients, set pricing, and earn commissions.
"""

import os
import sys
import random
import string
from datetime import datetime
from typing import Optional, Dict, Any, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from modules.database import _execute_with_retry, get_connection_with_retry


def init_reseller_tables() -> bool:
    conn = get_connection_with_retry()
    if not conn:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS resellers (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT UNIQUE NOT NULL,
                    username VARCHAR(255),
                    credit_limit INTEGER NOT NULL DEFAULT 500,
                    commission_pct INTEGER NOT NULL DEFAULT 10,
                    balance DECIMAL(10,2) NOT NULL DEFAULT 0,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_by BIGINT,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS reseller_clients (
                    id SERIAL PRIMARY KEY,
                    reseller_id BIGINT NOT NULL,
                    client_user_id BIGINT NOT NULL,
                    credit_limit INTEGER NOT NULL DEFAULT 100,
                    credits_used INTEGER NOT NULL DEFAULT 0,
                    price_per_credit DECIMAL(6,4) DEFAULT 0.10,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT NOW(),
                    UNIQUE(reseller_id, client_user_id)
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS reseller_transactions (
                    id SERIAL PRIMARY KEY,
                    reseller_id BIGINT NOT NULL,
                    client_user_id BIGINT,
                    amount DECIMAL(10,2) NOT NULL,
                    type VARCHAR(40) NOT NULL,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
        return True
    except Exception as e:
        print(f"[Reseller] Table init error: {e}")
        return False


def is_reseller(user_id: int) -> bool:
    def _op(conn):
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM resellers WHERE user_id=%s AND is_active=TRUE", (user_id,))
            return cur.fetchone() is not None
    return bool(_execute_with_retry(_op))


def add_reseller(user_id: int, username: str, credit_limit: int = 500,
                 commission_pct: int = 10, created_by: Optional[int] = None) -> bool:
    def _op(conn):
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO resellers (user_id, username, credit_limit, commission_pct, created_by)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                    is_active = TRUE, credit_limit = %s, commission_pct = %s, username = %s
            """, (user_id, username, credit_limit, commission_pct, created_by,
                  credit_limit, commission_pct, username))
        return True
    return bool(_execute_with_retry(_op))


def remove_reseller(user_id: int) -> bool:
    def _op(conn):
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE resellers SET is_active=FALSE WHERE user_id=%s", (user_id,))
        return True
    return bool(_execute_with_retry(_op))


def get_reseller_info(user_id: int) -> Optional[Dict]:
    def _op(conn):
        with conn.cursor() as cur:
            cur.execute("""
                SELECT user_id, username, credit_limit, commission_pct, balance, is_active, created_at
                FROM resellers WHERE user_id=%s
            """, (user_id,))
            row = cur.fetchone()
            if not row:
                return None
            return {
                "user_id": row[0], "username": row[1], "credit_limit": row[2],
                "commission_pct": row[3], "balance": float(row[4]),
                "active": row[5], "created": row[6]
            }
    return _execute_with_retry(_op)


def add_client(reseller_id: int, client_user_id: int,
               credit_limit: int = 100, price_per_credit: float = 0.10) -> bool:
    def _op(conn):
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO reseller_clients
                    (reseller_id, client_user_id, credit_limit, price_per_credit)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (reseller_id, client_user_id) DO UPDATE SET
                    credit_limit=%s, price_per_credit=%s, is_active=TRUE
            """, (reseller_id, client_user_id, credit_limit, price_per_credit,
                  credit_limit, price_per_credit))
        return True
    return bool(_execute_with_retry(_op))


def get_clients(reseller_id: int) -> List[Dict]:
    def _op(conn):
        with conn.cursor() as cur:
            cur.execute("""
                SELECT client_user_id, credit_limit, credits_used, price_per_credit, is_active, created_at
                FROM reseller_clients WHERE reseller_id=%s ORDER BY created_at DESC
            """, (reseller_id,))
            return [{"user_id": r[0], "limit": r[1], "used": r[2],
                     "price": float(r[3]), "active": r[4], "created": r[5]}
                    for r in cur.fetchall()]
    return _execute_with_retry(_op) or []


def get_reseller_of_client(client_user_id: int) -> Optional[int]:
    def _op(conn):
        with conn.cursor() as cur:
            cur.execute("""
                SELECT reseller_id FROM reseller_clients
                WHERE client_user_id=%s AND is_active=TRUE LIMIT 1
            """, (client_user_id,))
            row = cur.fetchone()
            return row[0] if row else None
    return _execute_with_retry(_op)


def record_client_spend(reseller_id: int, client_user_id: int,
                        credits_used: int, price_per_credit: float) -> bool:
    earning = round(credits_used * price_per_credit, 4)
    def _op(conn):
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE reseller_clients SET credits_used = credits_used + %s
                WHERE reseller_id=%s AND client_user_id=%s
            """, (credits_used, reseller_id, client_user_id))
            cur.execute("""
                UPDATE resellers SET balance = balance + %s WHERE user_id=%s
            """, (earning, reseller_id))
            cur.execute("""
                INSERT INTO reseller_transactions (reseller_id, client_user_id, amount, type, description)
                VALUES (%s, %s, %s, 'commission', %s)
            """, (reseller_id, client_user_id, earning,
                  f"Commission: {credits_used} credits @ ${price_per_credit:.4f}"))
        return True
    return bool(_execute_with_retry(_op))


def get_all_resellers() -> List[Dict]:
    def _op(conn):
        with conn.cursor() as cur:
            cur.execute("""
                SELECT r.user_id, r.username, r.credit_limit, r.commission_pct,
                       r.balance, r.is_active,
                       COUNT(c.id) as client_count
                FROM resellers r
                LEFT JOIN reseller_clients c ON c.reseller_id = r.user_id AND c.is_active=TRUE
                GROUP BY r.user_id, r.username, r.credit_limit, r.commission_pct, r.balance, r.is_active
                ORDER BY r.created_at DESC
            """)
            return [{"user_id": r[0], "username": r[1], "limit": r[2],
                     "commission": r[3], "balance": float(r[4]),
                     "active": r[5], "clients": r[6]}
                    for r in cur.fetchall()]
    return _execute_with_retry(_op) or []
