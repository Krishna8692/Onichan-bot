import os

# Bot Configuration
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
TENOR_API_KEY = os.environ.get("TENOR_API_KEY", "AIzaSyAyimkuYQYF_FXVALexPuGQctUWRURdCYQ")

# MongoDB Configuration
MONGODB_URI = os.environ.get("MONGODB_URI", "")
USE_MONGODB = bool(MONGODB_URI)

OWNER_ID = int(os.environ.get("OWNER_ID", "0"))
OWNER_USERNAME = os.environ.get("OWNER_USERNAME", "tu_bkl_hai")

TON_WALLET = os.environ.get("TON_WALLET", "")

SUPPORT_USERNAME = "tu_bkl_hai"
CHANNEL_USERNAME = "krishnaslounge"

CHARGED_CARDS_CHANNEL = None
SEND_CHARGED_TO_CHANNEL = False  # Disabled

BOT_USERNAME = "Onichanbabybot"
ALLOW_NEW_USERS = True
REQUIRE_APPROVAL = False

PREMIUM_PRICES = {
    "1_week": "$3",
    "2_weeks": "$5",
    "3_weeks": "$7",
    "1_month": "$10"
}

# ============================================================
# DATABASE CONFIGURATION - All data storage paths
# ============================================================
# Base database directory - use absolute path for persistence across deploys
# This ensures data survives republishing
DATABASE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

# User Management Files
DB_OWNER = f"{DATABASE_DIR}/owner.txt"
DB_PREMIUM = f"{DATABASE_DIR}/paid.txt"
DB_FREE = f"{DATABASE_DIR}/free.txt"
DB_BANNED = f"{DATABASE_DIR}/ban.txt"
DB_PENDING = f"{DATABASE_DIR}/pending.txt"

# Card & Checking Files
DB_APPROVED_CARDS = f"{DATABASE_DIR}/approved_cards.txt"
DB_APPROVED_LOG = f"{DATABASE_DIR}/approved_log.txt"

# Premium System Files
DB_PREMIUM_KEYS = f"{DATABASE_DIR}/premium_keys.txt"
DB_REDEEMED_KEYS = f"{DATABASE_DIR}/redeemed_keys.txt"
DB_PREMIUM_PLANS = f"{DATABASE_DIR}/premium_plans.txt"

# Payment & Invoice Files
DB_INVOICES = f"{DATABASE_DIR}/invoices.txt"
DB_PAYMENTS = f"{DATABASE_DIR}/payments.txt"

# Sites & Custom Data Files
DB_SITES = f"{DATABASE_DIR}/sites.txt"
DB_CUSTOM_GATES = f"{DATABASE_DIR}/custom_gates.txt"
DB_SETTINGS = f"{DATABASE_DIR}/settings.txt"

# Stats & Logs
DB_STATS = f"{DATABASE_DIR}/stats.txt"
DB_CHECK_LOG = f"{DATABASE_DIR}/check_log.txt"

# User Configuration
DB_USER_CONFIGS = f"{DATABASE_DIR}/user_configs.json"
DB_USER_CREDENTIALS = f"{DATABASE_DIR}/user_credentials.json"

# Admin Permissions
DB_ADMIN_PERMISSIONS = f"{DATABASE_DIR}/admin_permissions.json"

# Crypto Payments
DB_CRYPTO_TRANSACTIONS = f"{DATABASE_DIR}/crypto_transactions.txt"
DB_CRYPTO_PENDING = f"{DATABASE_DIR}/crypto_pending.txt"

def init_database():
    """Initialize database directory and files"""
    import os
    
    # Create database directory if not exists
    os.makedirs(DATABASE_DIR, exist_ok=True)
    
    # List of all database files
    db_files = [
        DB_OWNER, DB_PREMIUM, DB_FREE, DB_BANNED, DB_PENDING,
        DB_APPROVED_CARDS, DB_APPROVED_LOG,
        DB_PREMIUM_KEYS, DB_REDEEMED_KEYS, DB_PREMIUM_PLANS,
        DB_INVOICES, DB_PAYMENTS,
        DB_SITES, DB_CUSTOM_GATES, DB_SETTINGS,
        DB_STATS, DB_CHECK_LOG
    ]
    
    # Create files if they don't exist
    for db_file in db_files:
        if not os.path.exists(db_file):
            with open(db_file, 'w', encoding='utf-8') as f:
                pass  # Create empty file
    
    return True

# ============================================================

MASS_CHECK_LIMITS = {
    "free": 50,
    "premium": 999999,
    "owner": 999999
}

SYSTEM_PROXIES = [
    "geo.g-w.info:10080:j1ZAX5jRDN54bU31:kV0bwE8IYByihLls",
    "geo.g-w.info:10080:BWwQZ5bFRqnWmKPm:Qj23ViSE8V90lRaZ",
    "geo.g-w.info:10080:ronCANdBwfj1rzaV:4EjkKwoKREPgEmSh",
    "geo.g-w.info:10080:vSbUtrs0BQPcUM75:PjcT7AWg2onuysF7",
    "geo.g-w.info:10080:KJweQKzGVBvXjmN5:LS8A5YUWXuH2UFUf",
    "geo.g-w.info:10080:DUCdmEg4jbqsQiZ7:vT7wSnt7Gl47cOyb",
    "geo.g-w.info:10080:Cq5X15wjTYufCsid:ahLoNIrYuJpKF2SS",
    "geo.g-w.info:10080:Z5RcVujYO0Oy2qHw:hpuMrTLd3XsuDzjV",
    "geo.g-w.info:10080:DML3AlYhtC7mTt77:edO1JU9tFG8CPrP6",
    "geo.g-w.info:10080:x9OjMx5b76kJlVim:WdYTukGZf3wEA61G",
    "geo.g-w.info:10080:Zn8U8mvLe89v2WOM:aPAGRoYloAFfwbA3",
    "geo.g-w.info:10080:eBAqrXDQ3ZL8qR1w:oEoJVgHxT7FqvCpT",
    "geo.g-w.info:10080:yD78uiRfg9cLiBie:JsoFIhHVE9oNep8t",
    "geo.g-w.info:10080:jF2Wplk0oth9MNPy:vcEfwVVjPZaB9ezE",
    "geo.g-w.info:10080:38K9vLWph46nkMdB:jN4yJ0tlR2Z4L3OA",
    "geo.g-w.info:10080:7ly64bRZ9BWkxeC7:7iUcyzNy2RzSzpih",
    "geo.g-w.info:10080:BcdfOyftUkpCBWYV:BorY8dfAK5gx3ZzV",
    "geo.g-w.info:10080:LirCtV6QTsI9dFFo:l6Z6YyDGhdGq9z1G",
    "geo.g-w.info:10080:7QXwCz8xf8ihXuoD:74D9KhSZ57hqFgIB",
    "geo.g-w.info:10080:xwU5EEa4MwJH7GQE:gfZkUeZuyoQUGM5z",
]

PROXY_MODE_FILE = os.path.join(DATABASE_DIR, "proxy_modes.json")
