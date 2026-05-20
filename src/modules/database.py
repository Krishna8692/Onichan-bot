#!/usr/bin/env python3
"""
PostgreSQL Database Layer for Onichan Bot
High-performance pooled connections with thread-local re-use.

Performance notes:
- Uses ThreadedConnectionPool (no per-call `SELECT 1` health-check ping).
- Each worker thread keeps a persistent thread-local connection so the
  bot's many concurrent handlers do not contend on a single shared socket.
- Autocommit is enabled by default; failures cause lazy reconnect.
"""
import os
import threading
import psycopg2
from psycopg2 import pool as _pgpool
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import time

DATABASE_URL = os.environ.get("DATABASE_URL", "")

# Global pool + thread-local connection holder
_pool: Optional[_pgpool.ThreadedConnectionPool] = None
_pool_lock = threading.Lock()
_tls = threading.local()
_db_connected = False
_last_connect_attempt = 0

# Pool sizing: background threads + Flask handlers.
# Keep headroom modest — thread-local connections are held for the thread
# lifetime, so a large max drains Supabase limits and starves new requests.
_POOL_MIN = 2
_POOL_MAX = 25


def _ensure_pool() -> bool:
    """Lazily create the global threaded connection pool."""
    global _pool, _db_connected, _last_connect_attempt
    if _pool is not None:
        return True
    if not DATABASE_URL:
        print("❌ DATABASE_URL not found in environment")
        return False

    now = time.time()
    if (now - _last_connect_attempt) < 2 and _pool is None:
        # avoid reconnect-storm if DB is currently unreachable
        return False
    _last_connect_attempt = now

    with _pool_lock:
        if _pool is not None:
            return True
        try:
            _pool = _pgpool.ThreadedConnectionPool(
                _POOL_MIN, _POOL_MAX,
                dsn=DATABASE_URL,
                connect_timeout=10,
                keepalives=1,
                keepalives_idle=30,
                keepalives_interval=10,
                keepalives_count=5,
                options="-c statement_timeout=30000",
            )
            _db_connected = True
            return True
        except Exception as e:
            print(f"❌ Database pool init failed: {e}")
            _db_connected = False
            _pool = None
            return False


def _new_thread_conn():
    """Acquire a fresh connection from the pool for this thread."""
    if not _ensure_pool():
        return None
    try:
        # maxwait=3s: fail fast instead of blocking forever when pool exhausted
        conn = _pool.getconn()
        conn.autocommit = True
        return conn
    except _pgpool.PoolError as e:
        print(f"❌ Pool getconn failed: {e}")
        return None
    except Exception as e:
        print(f"❌ Pool getconn failed: {e}")
        return None


def _drop_thread_conn():
    """Discard the current thread's connection (after error)."""
    conn = getattr(_tls, "conn", None)
    if conn is None:
        return
    try:
        if _pool is not None:
            # Close the broken connection so the pool replaces it
            try:
                conn.close()
            except Exception:
                pass
            try:
                _pool.putconn(conn, close=True)
            except Exception:
                pass
    finally:
        _tls.conn = None


def get_connection(force_reconnect=False):
    """Return a persistent per-thread DB connection (no ping check)."""
    global _db_connected
    if force_reconnect:
        _drop_thread_conn()

    conn = getattr(_tls, "conn", None)
    if conn is not None and not conn.closed:
        return conn

    conn = _new_thread_conn()
    if conn is None:
        return None
    _tls.conn = conn
    _db_connected = True
    return conn


def get_connection_with_retry():
    """Same as get_connection but with bounded retry on failure."""
    for attempt in range(3):
        conn = get_connection()
        if conn is not None:
            return conn
        time.sleep(0.3)
    return None


def return_connection(conn):
    """Kept for API compatibility — connection stays bound to this thread."""
    pass


def is_db_connected():
    """Cheap connectivity check (does not ping)."""
    return _db_connected and _pool is not None

def _create_tables():
    """Create required database tables if they don't exist"""
    conn = get_connection()
    if not conn:
        return False
    
    try:
        with conn.cursor() as cur:
            # Users table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT UNIQUE NOT NULL,
                    username VARCHAR(255),
                    status VARCHAR(50) DEFAULT 'pending',
                    premium BOOLEAN DEFAULT FALSE,
                    premium_expiry TIMESTAMP,
                    is_owner BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """)
            
            # Premium keys table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS premium_keys (
                    id SERIAL PRIMARY KEY,
                    key VARCHAR(255) UNIQUE NOT NULL,
                    days INTEGER NOT NULL,
                    created_by BIGINT,
                    used BOOLEAN DEFAULT FALSE,
                    used_by BIGINT,
                    used_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            
            # Card logs table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS card_logs (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    card_bin VARCHAR(20),
                    result VARCHAR(50),
                    gate VARCHAR(50),
                    response TEXT,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            
            # Payments table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS payments (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    amount DECIMAL(10, 2),
                    currency VARCHAR(10),
                    status VARCHAR(50),
                    payment_method VARCHAR(50),
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            
            # Settings table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    id SERIAL PRIMARY KEY,
                    key VARCHAR(255) UNIQUE NOT NULL,
                    value TEXT,
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """)

            # Wallet addresses table (Telegram ID ↔ on-chain address mapping)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS wallet_addresses (
                    id SERIAL PRIMARY KEY,
                    telegram_id BIGINT NOT NULL,
                    chain VARCHAR(50) NOT NULL,
                    address TEXT NOT NULL,
                    username VARCHAR(255),
                    avatar_url TEXT,
                    registered_at TIMESTAMP DEFAULT NOW(),
                    UNIQUE(telegram_id, chain)
                )
            """)

            cur.execute("""
                ALTER TABLE users ADD COLUMN IF NOT EXISTS shop_balance DECIMAL(10,2) DEFAULT 0.00
            """)

            # Custodial wallet — internal balances per asset
            cur.execute("""
                CREATE TABLE IF NOT EXISTS wallet_balances (
                    id SERIAL PRIMARY KEY,
                    telegram_id BIGINT NOT NULL,
                    asset VARCHAR(32) NOT NULL,
                    balance NUMERIC(40, 18) NOT NULL DEFAULT 0,
                    updated_at TIMESTAMP DEFAULT NOW(),
                    UNIQUE(telegram_id, asset)
                )
            """)

            # Custodial wallet — transaction ledger (deposits, withdrawals, transfers)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS wallet_transactions (
                    id SERIAL PRIMARY KEY,
                    telegram_id BIGINT NOT NULL,
                    counterparty_id BIGINT,
                    tx_type VARCHAR(24) NOT NULL,
                    chain VARCHAR(50),
                    asset VARCHAR(32) NOT NULL,
                    amount NUMERIC(40, 18) NOT NULL,
                    fee NUMERIC(40, 18) DEFAULT 0,
                    address TEXT,
                    tx_hash TEXT,
                    status VARCHAR(20) DEFAULT 'pending',
                    note TEXT,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """)
            # Throttle column for owner notifications about parked/blocked
            # withdrawals. Persisting this on the row (instead of in-memory
            # in the worker thread) prevents re-spamming the owner every
            # time the bot restarts while a withdrawal is still pending.
            cur.execute(
                "ALTER TABLE wallet_transactions "
                "ADD COLUMN IF NOT EXISTS last_notified_at TIMESTAMP"
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_wtx_tg ON wallet_transactions(telegram_id, created_at DESC)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_wtx_status ON wallet_transactions(status)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_wtx_hash ON wallet_transactions(tx_hash)")
            # Idempotency for on-chain deposit credits: a given (chain, tx_hash) deposit
            # can only be inserted once. The deposit notifier relies on the matching
            # ON CONFLICT (chain, tx_hash) WHERE tx_type='deposit' clause.
            cur.execute(
                """CREATE UNIQUE INDEX IF NOT EXISTS wallet_tx_deposit_uniq_idx
                   ON wallet_transactions (chain, tx_hash)
                   WHERE tx_type = 'deposit' AND tx_hash IS NOT NULL"""
            )

            # Custodial wallet — HD-derived deposit addresses per user/chain
            cur.execute("""
                CREATE TABLE IF NOT EXISTS wallet_deposit_addresses (
                    id SERIAL PRIMARY KEY,
                    telegram_id BIGINT NOT NULL,
                    chain VARCHAR(50) NOT NULL,
                    address TEXT NOT NULL,
                    derivation_index INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW(),
                    UNIQUE(telegram_id, chain),
                    UNIQUE(chain, address)
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_wda_addr ON wallet_deposit_addresses(chain, address)")

            # Atomic, race-safe HD derivation-index allocator.
            # Each new user gets a unique index via nextval() — no SELECT MAX races.
            cur.execute("CREATE SEQUENCE IF NOT EXISTS wallet_hd_index_seq START WITH 1")

            cur.execute("""
                CREATE TABLE IF NOT EXISTS cc_shop_stock (
                    id SERIAL PRIMARY KEY,
                    cc_number TEXT NOT NULL,
                    mm VARCHAR(4) NOT NULL,
                    yy VARCHAR(10) NOT NULL,
                    cvv TEXT NOT NULL,
                    bin6 VARCHAR(8),
                    country VARCHAR(100),
                    country_code VARCHAR(5),
                    brand VARCHAR(50),
                    card_type VARCHAR(50),
                    card_level VARCHAR(100),
                    bank VARCHAR(200),
                    price DECIMAL(10,2) DEFAULT 5.00,
                    status VARCHAR(20) DEFAULT 'available',
                    uploaded_at TIMESTAMP DEFAULT NOW(),
                    sold_to BIGINT,
                    sold_at TIMESTAMP,
                    card_fingerprint VARCHAR(64)
                )
            """)
            cur.execute("ALTER TABLE cc_shop_stock ALTER COLUMN cvv TYPE TEXT")
            cur.execute("ALTER TABLE cc_shop_stock ALTER COLUMN yy TYPE VARCHAR(10)")
            cur.execute("ALTER TABLE cc_shop_stock ALTER COLUMN mm TYPE VARCHAR(4)")
            cur.execute("ALTER TABLE cc_shop_stock ALTER COLUMN bin6 TYPE VARCHAR(8)")
            cur.execute("ALTER TABLE cc_shop_stock ADD COLUMN IF NOT EXISTS card_fingerprint VARCHAR(64)")
            cur.execute("""
                DO $$ BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'cc_shop_stock_card_fingerprint_key') THEN
                        ALTER TABLE cc_shop_stock ADD CONSTRAINT cc_shop_stock_card_fingerprint_key UNIQUE (card_fingerprint);
                    END IF;
                END $$;
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS cc_shop_purchases (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    card_id INTEGER REFERENCES cc_shop_stock(id),
                    price DECIMAL(10,2) NOT NULL,
                    purchased_at TIMESTAMP DEFAULT NOW(),
                    holder_name VARCHAR(200),
                    holder_email VARCHAR(200),
                    holder_phone VARCHAR(50),
                    holder_address TEXT,
                    refunded BOOLEAN DEFAULT FALSE,
                    refund_amount DECIMAL(10,2),
                    refunded_at TIMESTAMP
                )
            """)
            cur.execute("ALTER TABLE cc_shop_purchases ADD COLUMN IF NOT EXISTS refunded BOOLEAN DEFAULT FALSE")
            cur.execute("ALTER TABLE cc_shop_purchases ADD COLUMN IF NOT EXISTS refund_amount DECIMAL(10,2)")
            cur.execute("ALTER TABLE cc_shop_purchases ADD COLUMN IF NOT EXISTS refunded_at TIMESTAMP")
            cur.execute("ALTER TABLE cc_shop_purchases ADD COLUMN IF NOT EXISTS refund_denial_reason VARCHAR(50)")

            cur.execute("""
                CREATE TABLE IF NOT EXISTS cc_shop_settings (
                    id SERIAL PRIMARY KEY,
                    key VARCHAR(100) UNIQUE NOT NULL,
                    value TEXT,
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """)

            cur.execute("""
                INSERT INTO cc_shop_settings (key, value, updated_at)
                VALUES ('refund_window_minutes', '5', NOW())
                ON CONFLICT (key) DO NOTHING
            """)
            cur.execute("""
                INSERT INTO cc_shop_settings (key, value, updated_at)
                VALUES ('non_refundable_banks', '["JP Morgan Chase", "Capital One"]', NOW())
                ON CONFLICT (key) DO NOTHING
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS cc_shop_price_rules (
                    id SERIAL PRIMARY KEY,
                    rule_type VARCHAR(20) NOT NULL,
                    target VARCHAR(100) NOT NULL,
                    price DECIMAL(10,2) NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW(),
                    UNIQUE(rule_type, target)
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS cc_shop_deposits (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    username VARCHAR(100),
                    amount DECIMAL(10,2) NOT NULL,
                    crypto VARCHAR(10),
                    order_id VARCHAR(100) UNIQUE,
                    track_id VARCHAR(100),
                    payment_url TEXT,
                    status VARCHAR(20) DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT NOW(),
                    confirmed_at TIMESTAMP
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS proxy_plans (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    proxy_type VARCHAR(10) NOT NULL,
                    bandwidth_gb DECIMAL(10,2) NOT NULL,
                    price DECIMAL(10,2) NOT NULL,
                    duration_days INTEGER DEFAULT 30,
                    country VARCHAR(100) DEFAULT '',
                    description TEXT DEFAULT '',
                    category VARCHAR(20) DEFAULT 'datacenter',
                    source_type VARCHAR(10) DEFAULT 'vps',
                    active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            cur.execute("ALTER TABLE proxy_plans ADD COLUMN IF NOT EXISTS duration_days INTEGER DEFAULT 30")
            cur.execute("ALTER TABLE proxy_plans ADD COLUMN IF NOT EXISTS country VARCHAR(100) DEFAULT ''")
            cur.execute("ALTER TABLE proxy_plans ADD COLUMN IF NOT EXISTS category VARCHAR(20) DEFAULT 'datacenter'")
            cur.execute("ALTER TABLE proxy_plans ADD COLUMN IF NOT EXISTS source_type VARCHAR(10) DEFAULT 'vps'")

            cur.execute("SELECT COUNT(*) FROM proxy_plans")
            plan_count = cur.fetchone()[0]
            if plan_count == 0:
                default_plans = [
                    ('Datacenter HTTP - Basic', 'HTTP', '', 30, 50, 1.00, 'datacenter', 'pool'),
                    ('Datacenter HTTP - Standard', 'HTTP', '', 30, 100, 3.00, 'datacenter', 'pool'),
                    ('Datacenter HTTP - Pro', 'HTTP', '', 30, 500, 5.00, 'datacenter', 'pool'),
                    ('Residential HTTP - Basic', 'HTTP', '', 30, 30, 1.00, 'residential', 'pool'),
                    ('Residential HTTP - Standard', 'HTTP', '', 30, 80, 3.00, 'residential', 'pool'),
                    ('Residential HTTP - Pro', 'HTTP', '', 30, 200, 5.00, 'residential', 'pool'),
                    ('Rotating 10x HTTP - Basic', 'HTTP', '', 30, 100, 1.00, 'rotating', 'pool'),
                    ('Rotating 10x HTTP - Standard', 'HTTP', '', 30, 300, 3.00, 'rotating', 'pool'),
                    ('Rotating 10x HTTP - Pro', 'HTTP', '', 30, 1000, 5.00, 'rotating', 'pool'),
                ]
                for p in default_plans:
                    cur.execute("""
                        INSERT INTO proxy_plans (name, proxy_type, country, duration_days, bandwidth_gb, price, category, source_type, active)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, TRUE)
                    """, p)
                print("📦 Default proxy plans seeded")

            cur.execute("""
                CREATE TABLE IF NOT EXISTS proxy_servers (
                    id SERIAL PRIMARY KEY,
                    host VARCHAR(255) NOT NULL,
                    port INTEGER NOT NULL,
                    proxy_type VARCHAR(10) NOT NULL,
                    username VARCHAR(255) DEFAULT '',
                    password VARCHAR(255) DEFAULT '',
                    country VARCHAR(100) DEFAULT '',
                    max_bandwidth_gb DECIMAL(10,2) DEFAULT 0,
                    used_bandwidth_gb DECIMAL(10,2) DEFAULT 0,
                    label VARCHAR(100) DEFAULT '',
                    active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            cur.execute("ALTER TABLE proxy_servers ADD COLUMN IF NOT EXISTS max_bandwidth_gb DECIMAL(10,2) DEFAULT 0")
            cur.execute("ALTER TABLE proxy_servers ADD COLUMN IF NOT EXISTS used_bandwidth_gb DECIMAL(10,2) DEFAULT 0")

            cur.execute("""
                CREATE TABLE IF NOT EXISTS proxy_nodes (
                    id SERIAL PRIMARY KEY,
                    label VARCHAR(100) DEFAULT '',
                    host VARCHAR(255) NOT NULL,
                    api_port INTEGER DEFAULT 8899,
                    api_key VARCHAR(255) NOT NULL,
                    proxy_ports TEXT DEFAULT '{"http":8080,"socks5":1080}',
                    protocols TEXT DEFAULT 'HTTP,SOCKS5',
                    country VARCHAR(100) DEFAULT '',
                    max_bandwidth_gb DECIMAL(12,2) DEFAULT 0,
                    used_bandwidth_gb DECIMAL(12,2) DEFAULT 0,
                    connected_users INTEGER DEFAULT 0,
                    status VARCHAR(20) DEFAULT 'offline',
                    last_seen TIMESTAMP,
                    active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS proxy_pool (
                    id SERIAL PRIMARY KEY,
                    host VARCHAR(255) NOT NULL,
                    port INTEGER NOT NULL,
                    proxy_type VARCHAR(10) NOT NULL,
                    username VARCHAR(255) DEFAULT '',
                    password VARCHAR(255) DEFAULT '',
                    country VARCHAR(100) DEFAULT '',
                    country_code VARCHAR(5) DEFAULT '',
                    isp VARCHAR(255) DEFAULT '',
                    speed_ms INTEGER DEFAULT 0,
                    anonymity VARCHAR(20) DEFAULT 'unknown',
                    hosting BOOLEAN DEFAULT FALSE,
                    classification VARCHAR(20) DEFAULT 'unknown',
                    fraud_score INTEGER DEFAULT 0,
                    alive BOOLEAN DEFAULT TRUE,
                    last_checked TIMESTAMP DEFAULT NOW(),
                    source VARCHAR(100) DEFAULT '',
                    created_at TIMESTAMP DEFAULT NOW(),
                    UNIQUE(host, port)
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS proxy_purchases (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    plan_id INTEGER REFERENCES proxy_plans(id),
                    server_id INTEGER,
                    node_id INTEGER,
                    pool_proxy_id INTEGER,
                    proxy_host VARCHAR(255) NOT NULL,
                    proxy_port INTEGER NOT NULL,
                    proxy_user VARCHAR(255) NOT NULL,
                    proxy_pass VARCHAR(255) NOT NULL,
                    proxy_type VARCHAR(10) NOT NULL,
                    bandwidth_gb DECIMAL(10,2) NOT NULL,
                    bandwidth_used_gb DECIMAL(10,2) DEFAULT 0,
                    price DECIMAL(10,2) NOT NULL,
                    source_type VARCHAR(10) DEFAULT 'vps',
                    status VARCHAR(20) DEFAULT 'active',
                    purchased_at TIMESTAMP DEFAULT NOW(),
                    expires_at TIMESTAMP
                )
            """)
            cur.execute("ALTER TABLE proxy_purchases ADD COLUMN IF NOT EXISTS node_id INTEGER")
            cur.execute("ALTER TABLE proxy_purchases ADD COLUMN IF NOT EXISTS pool_proxy_id INTEGER")
            cur.execute("ALTER TABLE proxy_purchases ADD COLUMN IF NOT EXISTS source_type VARCHAR(10) DEFAULT 'vps'")
            cur.execute("ALTER TABLE proxy_purchases ADD COLUMN IF NOT EXISTS proxy_list TEXT DEFAULT ''")

            cur.execute("ALTER TABLE proxy_pool ADD COLUMN IF NOT EXISTS classification VARCHAR(20) DEFAULT 'unknown'")
            cur.execute("ALTER TABLE proxy_pool ADD COLUMN IF NOT EXISTS fraud_score INTEGER DEFAULT 0")

            cur.execute("""
                CREATE TABLE IF NOT EXISTS scrape_sources (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100) UNIQUE NOT NULL,
                    url TEXT NOT NULL,
                    proxy_type VARCHAR(10) NOT NULL DEFAULT 'HTTP',
                    enabled BOOLEAN DEFAULT TRUE,
                    json_mode BOOLEAN DEFAULT FALSE,
                    json_path TEXT DEFAULT '',
                    interval_minutes INTEGER DEFAULT 20,
                    last_run TIMESTAMP,
                    last_count INTEGER DEFAULT 0,
                    last_alive INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS scrape_history (
                    id SERIAL PRIMARY KEY,
                    source_name VARCHAR(100),
                    total_scraped INTEGER DEFAULT 0,
                    total_alive INTEGER DEFAULT 0,
                    total_stored INTEGER DEFAULT 0,
                    duration_seconds DECIMAL(10,2) DEFAULT 0,
                    error TEXT DEFAULT '',
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)

            cur.execute("CREATE INDEX IF NOT EXISTS idx_users_premium_expiry ON users(premium, premium_expiry)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_users_status ON users(status)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_cc_shop_stock_status ON cc_shop_stock(status)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_cc_shop_deposits_user ON cc_shop_deposits(user_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_cc_shop_deposits_status ON cc_shop_deposits(status)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_card_logs_user ON card_logs(user_id, created_at DESC)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_proxy_pool_alive ON proxy_pool(alive, classification)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_bin_shop_listings_status ON bin_shop_listings(status)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_bin_shop_purchases_user ON bin_shop_purchases(user_id, purchased_at DESC)")

            # Signal feedback table — stores profit/loss outcomes with indicator snapshots
            cur.execute("""
                CREATE TABLE IF NOT EXISTS signal_feedback (
                    id SERIAL PRIMARY KEY,
                    telegram_id BIGINT NOT NULL,
                    asset TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    timeframe_minutes INTEGER NOT NULL,
                    rsi FLOAT,
                    macd_cross TEXT,
                    bb_position TEXT,
                    ema_trend TEXT,
                    patterns TEXT,
                    outcome TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_sfb_asset ON signal_feedback(asset, direction, created_at DESC)")

        # Casino tables
        from modules.casino import _init_casino_tables, start_cleanup_scheduler
        _init_casino_tables()
        start_cleanup_scheduler()

        return True
    except Exception as e:
        print(f"Table creation error: {e}")
        return False

def init_database_sync():
    """Initialize database connection and create tables"""
    global _db_connected
    
    if not DATABASE_URL:
        print("❌ No DATABASE_URL found")
        return False
    
    conn = get_connection()
    if conn:
        _db_connected = True
        _create_tables()
        print("🗄️ PostgreSQL: Connected")
        return True
    
    print("❌ Failed to connect to PostgreSQL")
    return False

async def init_database():
    return init_database_sync()

def _execute_with_retry(query, params=None, fetch=False, fetch_one=False, return_rowcount=False):
    """Execute a query with retry logic using the pooled per-thread connection.

    Supports two calling conventions:
    1. SQL string:   _execute_with_retry("SELECT ...", (params,), fetch=True)
    2. Callable op:  _execute_with_retry(lambda conn: ...)  — used by newer modules
    """
    if callable(query):
        _op_func = query
        for attempt in range(3):
            try:
                conn = get_connection_with_retry()
                if not conn:
                    time.sleep(0.3)
                    continue
                if not conn.autocommit:
                    conn.autocommit = True
                return _op_func(conn)
            except (psycopg2.InterfaceError, psycopg2.OperationalError) as e:
                print(f"[DB] Connection error (op), reconnecting: {e}")
                _drop_thread_conn()
                time.sleep(0.3)
            except Exception as e:
                print(f"[DB] Op error attempt {attempt + 1}/3: {type(e).__name__}: {e}")
                msg = str(e).lower()
                if "closed" in msg or "ssl" in msg or "connection" in msg:
                    _drop_thread_conn()
                time.sleep(0.2)
        return None

    for attempt in range(3):
        try:
            conn = get_connection_with_retry()
            if not conn:
                time.sleep(0.3)
                continue

            if not conn.autocommit:
                conn.autocommit = True

            use_dict_cursor = fetch or fetch_one
            with conn.cursor(cursor_factory=RealDictCursor if use_dict_cursor else None) as cur:
                cur.execute(query, params)
                if fetch_one:
                    return cur.fetchone()
                if fetch:
                    return cur.fetchall()
                if return_rowcount:
                    return cur.rowcount
                return True
        except (psycopg2.InterfaceError, psycopg2.OperationalError) as e:
            print(f"[DB] Connection error, will reconnect: {e}")
            _drop_thread_conn()
            time.sleep(0.3)
        except Exception as e:
            msg = str(e).lower()
            if "statement timeout" in msg or "canceling statement" in msg:
                print(f"[DB] Statement timeout on query: {query[:80] if isinstance(query, str) else '(callable)'}...")
                return None if fetch or fetch_one else (0 if return_rowcount else False)
            print(f"[DB] Query error attempt {attempt + 1}/3: {type(e).__name__}: {e}")
            if "closed" in msg or "ssl" in msg or "connection" in msg:
                _drop_thread_conn()
            time.sleep(0.2)

    print(f"[DB] Query failed after 3 attempts: {query[:60] if isinstance(query, str) else '(callable)'}...")
    return None if fetch or fetch_one else (0 if return_rowcount else False)

def is_user_premium_sync(user_id: int) -> bool:
    """Check if user has premium access - robust with proper timezone handling"""
    if user_id in [8119946836, 8268257476, 8271254197]:
        return True
    
    try:
        result = _execute_with_retry(
            "SELECT premium, premium_expiry, is_owner FROM users WHERE user_id = %s",
            (user_id,), fetch_one=True
        )
        
        if result:
            if result.get("is_owner"):
                return True
            if not result.get("premium"):
                return False
            expiry = result.get("premium_expiry")
            if expiry:
                try:
                    if isinstance(expiry, str):
                        expiry = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
                    if hasattr(expiry, 'tzinfo') and expiry.tzinfo:
                        expiry_naive = expiry.replace(tzinfo=None)
                    else:
                        expiry_naive = expiry
                    now_utc = datetime.utcnow()
                    is_valid = expiry_naive > now_utc
                    return is_valid
                except Exception as e:
                    print(f"[DB] Premium expiry check error for {user_id}: {e}")
                    return True
            return True
        return False
    except Exception as e:
        print(f"[DB] is_user_premium_sync error for {user_id}: {e}")
        return False

def is_user_approved_sync(user_id: int) -> bool:
    """Check if user is approved"""
    result = _execute_with_retry(
        "SELECT status, is_owner FROM users WHERE user_id = %s",
        (user_id,), fetch_one=True
    )
    if result:
        if result.get("is_owner"):
            return True
        return result.get("status") == "approved"
    return False

def is_user_banned_sync(user_id: int) -> bool:
    """Check if user is banned"""
    result = _execute_with_retry(
        "SELECT status FROM users WHERE user_id = %s",
        (user_id,), fetch_one=True
    )
    if result:
        return result.get("status") == "banned"
    return False

def is_user_owner_sync(user_id: int) -> bool:
    """Check if user is an owner"""
    result = _execute_with_retry(
        "SELECT is_owner FROM users WHERE user_id = %s",
        (user_id,), fetch_one=True
    )
    if result:
        return result.get("is_owner", False)
    return False

def add_user_sync(user_id, username=None, status="pending"):
    """Add or update user - status upgrades from pending to approved but never downgrades"""
    return _execute_with_retry("""
        INSERT INTO users (user_id, username, status, updated_at)
        VALUES (%s, %s, %s, NOW())
        ON CONFLICT (user_id) DO UPDATE SET
            username = COALESCE(EXCLUDED.username, users.username),
            status = CASE
                WHEN EXCLUDED.status = 'approved' THEN 'approved'
                WHEN users.status = 'banned' THEN 'banned'
                ELSE users.status
            END,
            updated_at = NOW()
    """, (user_id, username, status))

def approve_user_sync(user_id):
    """Approve a user"""
    return _execute_with_retry("""
        UPDATE users SET status = 'approved', updated_at = NOW()
        WHERE user_id = %s
    """, (user_id,))

def ban_user_sync(user_id):
    """Ban a user"""
    return _execute_with_retry("""
        UPDATE users SET status = 'banned', updated_at = NOW()
        WHERE user_id = %s
    """, (user_id,))

def unban_user_sync(user_id):
    """Unban a user (set to approved)"""
    return approve_user_sync(user_id)

def _get_premium_file_path():
    try:
        from config import DB_PREMIUM
        return DB_PREMIUM
    except ImportError:
        import os
        return os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "paid.txt")

def _sync_premium_to_file(user_id, expiry_str):
    import os
    db_premium = _get_premium_file_path()
    os.makedirs(os.path.dirname(db_premium), exist_ok=True)
    lines = []
    if os.path.exists(db_premium):
        with open(db_premium, 'r') as f:
            lines = f.readlines()
    new_lines = []
    found = False
    for line in lines:
        parts = line.strip().split()
        if parts and parts[0].isdigit() and int(parts[0]) == user_id:
            new_lines.append(f"{user_id} {expiry_str}\n")
            found = True
        else:
            new_lines.append(line if line.endswith('\n') else line + '\n')
    if not found:
        new_lines.append(f"{user_id} {expiry_str}\n")
    with open(db_premium, 'w') as f:
        f.writelines(new_lines)

def _remove_from_premium_file(user_id):
    import os
    db_premium = _get_premium_file_path()
    if not os.path.exists(db_premium):
        return
    with open(db_premium, 'r') as f:
        lines = f.readlines()
    new_lines = [line for line in lines if not (line.strip().split() and line.strip().split()[0].isdigit() and int(line.strip().split()[0]) == user_id)]
    with open(db_premium, 'w') as f:
        f.writelines(new_lines)

def set_premium_sync(user_id, days):
    """Set premium for user and sync to local backup file. days can be int or datetime.
    If user already has active premium, extends from current expiry instead of replacing."""
    if isinstance(days, datetime):
        expiry = days
    else:
        num_days = int(days)
        current = _execute_with_retry(
            "SELECT premium_expiry FROM users WHERE user_id = %s AND premium = TRUE",
            (user_id,), fetch_one=True
        )
        if current and current.get("premium_expiry") and current["premium_expiry"] > datetime.utcnow():
            expiry = current["premium_expiry"] + timedelta(days=num_days)
        else:
            expiry = datetime.utcnow() + timedelta(days=num_days)
    result = _execute_with_retry("""
        INSERT INTO users (user_id, status, premium, premium_expiry, updated_at)
        VALUES (%s, 'approved', TRUE, %s, NOW())
        ON CONFLICT (user_id) DO UPDATE SET
            status = 'approved',
            premium = TRUE,
            premium_expiry = %s,
            updated_at = NOW()
    """, (user_id, expiry, expiry))
    
    try:
        expiry_str = expiry.strftime("%Y-%m-%d")
        _sync_premium_to_file(user_id, expiry_str)
    except Exception as e:
        print(f"[DB] Failed to sync premium to local file: {e}")
    
    return result

def remove_premium_sync(user_id):
    """Remove premium from user and clean up local files"""
    result = _execute_with_retry("""
        UPDATE users SET premium = FALSE, premium_expiry = NULL, updated_at = NOW()
        WHERE user_id = %s
    """, (user_id,))
    try:
        _remove_from_premium_file(user_id)
    except Exception as e:
        print(f"[DB] Failed to remove premium from paid.txt: {e}")
    try:
        import os
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        legacy_paths = [
            os.path.join(base_dir, "data", "premium.txt"),
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "premium.txt"),
        ]
        for lp in legacy_paths:
            if not os.path.exists(lp):
                continue
            with open(lp, 'r') as f:
                lines = f.readlines()
            new_lines = [line for line in lines if not (line.strip().split() and line.strip().split()[0].isdigit() and int(line.strip().split()[0]) == user_id)]
            with open(lp, 'w') as f:
                f.writelines(new_lines)
    except Exception as e:
        print(f"[DB] Failed to remove premium from legacy premium.txt: {e}")
    return result

def get_expired_premium_users():
    """Get users whose premium has expired but still marked as premium"""
    result = _execute_with_retry(
        "SELECT user_id, premium_expiry FROM users WHERE premium = TRUE AND premium_expiry IS NOT NULL AND premium_expiry < NOW()",
        fetch=True
    )
    return result or []

def get_approved_users_sync():
    """Get all approved users"""
    result = _execute_with_retry(
        "SELECT user_id FROM users WHERE status = 'approved'",
        fetch=True
    )
    return [u["user_id"] for u in (result or [])]

def get_banned_users_sync():
    """Get all banned users"""
    result = _execute_with_retry(
        "SELECT user_id FROM users WHERE status = 'banned'",
        fetch=True
    )
    return [u["user_id"] for u in (result or [])]

def get_premium_users_sync():
    """Get all premium users"""
    result = _execute_with_retry(
        "SELECT user_id FROM users WHERE premium = TRUE",
        fetch=True
    )
    return [u["user_id"] for u in (result or [])]

def get_owner_users_sync():
    """Get all owner users"""
    result = _execute_with_retry(
        "SELECT user_id FROM users WHERE is_owner = TRUE",
        fetch=True
    )
    return [u["user_id"] for u in (result or [])]

def sync_log_card_check(user_id, card, result_status, gate=None, response=None):
    """Log a card check"""
    bin_num = card.split("|")[0][:6] if "|" in card else card[:6]
    return _execute_with_retry("""
        INSERT INTO card_logs (user_id, card_bin, result, gate, response)
        VALUES (%s, %s, %s, %s, %s)
    """, (user_id, bin_num, result_status, gate, str(response)[:500] if response else None))

def sync_get_all_users():
    """Get all users"""
    result = _execute_with_retry(
        "SELECT * FROM users ORDER BY created_at DESC",
        fetch=True
    )
    return result or []

def sync_get_pending_users():
    """Get pending users"""
    result = _execute_with_retry(
        "SELECT * FROM users WHERE status = 'pending' ORDER BY created_at DESC",
        fetch=True
    )
    return result or []

def get_user_info(user_id):
    """Get full user info"""
    return _execute_with_retry(
        "SELECT * FROM users WHERE user_id = %s",
        (user_id,), fetch_one=True
    )

# Backwards compatibility aliases
init_mongodb = init_database
init_supabase = init_database
mongodb_connected = is_db_connected
supabase_connected = is_db_connected

mongo_is_premium = is_user_premium_sync
mongo_is_approved = is_user_approved_sync
mongo_is_banned = is_user_banned_sync
mongo_add_user = add_user_sync
mongo_approve_user = approve_user_sync
mongo_ban_user = ban_user_sync
mongo_unban_user = unban_user_sync
mongo_set_premium = set_premium_sync
mongo_remove_premium = remove_premium_sync
mongo_get_premium_users = get_premium_users_sync
mongo_log_card = sync_log_card_check
mongo_get_all_users = sync_get_all_users
mongo_get_pending_users = sync_get_pending_users
mongo_is_owner = lambda uid, oid: uid == oid

supabase_is_premium = is_user_premium_sync
supabase_is_approved = is_user_approved_sync
supabase_is_banned = is_user_banned_sync
supabase_add_user = add_user_sync
supabase_get_approved_users = get_approved_users_sync
supabase_get_banned_users = get_banned_users_sync
supabase_get_premium_users = get_premium_users_sync

def get_user_check_stats(user_id):
    """Get user's card check statistics"""
    try:
        result = _execute_with_retry("""
            SELECT 
                COUNT(*) as total_checks,
                COUNT(CASE WHEN result IN ('approved', 'charged', 'live', 'cvv') THEN 1 END) as approved,
                COUNT(CASE WHEN result IN ('declined', 'dead', 'die') THEN 1 END) as declined,
                MIN(created_at) as first_check
            FROM card_logs 
            WHERE user_id = %s
        """, (user_id,), fetch_one=True)
        
        if result:
            total = result.get('total_checks', 0) or 0
            approved = result.get('approved', 0) or 0
            declined = result.get('declined', 0) or 0
            first_check = result.get('first_check')
            success_rate = round((approved / total * 100), 1) if total > 0 else 0
            return {
                'total': total,
                'approved': approved,
                'declined': declined,
                'success_rate': success_rate,
                'first_check': first_check
            }
    except Exception as e:
        print(f"[DB] Error getting user stats: {e}")
    
    return {'total': 0, 'approved': 0, 'declined': 0, 'success_rate': 0, 'first_check': None}


# ═══════════════════════════════════════════════════════════
# EXTENSION KEYS — Onichan Bypasser Chrome Extension Auth
# ═══════════════════════════════════════════════════════════

def _ensure_extension_keys_table():
    """Create extension_keys table if it doesn't exist."""
    _execute_with_retry("""
        CREATE TABLE IF NOT EXISTS extension_keys (
            key        TEXT PRIMARY KEY,
            user_id    BIGINT NOT NULL,
            created_at TIMESTAMP DEFAULT NOW(),
            active     BOOLEAN DEFAULT TRUE
        )
    """)

def create_extension_key(user_id: int) -> str:
    """Generate a fresh extension activation key for a user (deactivates old ones)."""
    import secrets, string
    token = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(22))
    key = f"ONIX-{token}"
    _ensure_extension_keys_table()
    _execute_with_retry(
        "UPDATE extension_keys SET active = FALSE WHERE user_id = %s",
        (user_id,)
    )
    _execute_with_retry(
        "INSERT INTO extension_keys (key, user_id) VALUES (%s, %s) ON CONFLICT (key) DO NOTHING",
        (key, user_id)
    )
    return key

def validate_extension_key(key: str) -> dict:
    """Return {valid, user_id, is_premium, expires_at, expires_ts} or {valid: False}."""
    from datetime import datetime, timedelta, timezone
    _ensure_extension_keys_table()
    row = _execute_with_retry(
        "SELECT user_id, active FROM extension_keys WHERE key = %s",
        (key,),
        fetch_one=True
    )
    if not row or not row.get('active'):
        return {"valid": False}
    user_id = row['user_id']
    user = _execute_with_retry(
        "SELECT premium, premium_expiry FROM users WHERE user_id = %s",
        (user_id,),
        fetch_one=True
    )
    now = datetime.utcnow()
    if user and user.get('premium') and user.get('premium_expiry'):
        expiry = user['premium_expiry']
        if hasattr(expiry, 'tzinfo') and expiry.tzinfo:
            expiry = expiry.replace(tzinfo=None)
        is_premium = expiry > now
        expires_ts = int(expiry.timestamp() * 1000)
        expires_iso = expiry.isoformat()
    else:
        default_expiry = now + timedelta(days=30)
        is_premium = False
        expires_ts = int(default_expiry.timestamp() * 1000)
        expires_iso = default_expiry.isoformat()
    return {
        "valid": True,
        "user_id": user_id,
        "is_premium": is_premium,
        "expires_at": expires_iso,
        "expires_ts": expires_ts
    }

def revoke_extension_key(user_id: int) -> bool:
    """Revoke all active extension keys for a user."""
    _ensure_extension_keys_table()
    return bool(_execute_with_retry(
        "UPDATE extension_keys SET active = FALSE WHERE user_id = %s",
        (user_id,)
    ))
