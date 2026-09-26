"""
================================================================================
  Premium Plans & Payment System
  Manage premium subscriptions and generate invoices
================================================================================
"""

import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DB_PREMIUM_PLANS, DB_INVOICES, DB_PAYMENTS, DATABASE_DIR

PLANS_FILE = DB_PREMIUM_PLANS
INVOICES_FILE = DB_INVOICES
PAYMENTS_FILE = DB_PAYMENTS

# Premium Plans Configuration
PREMIUM_PLANS = {
    "1_week": {
        "name": "1 Week Premium",
        "duration_days": 7,
        "price": 3,
        "currency": "$",
        "features": [
            "20 cards per mass check",
            "All 18 charge gates",
            "Priority support",
            "No cooldown"
        ]
    },
    "2_weeks": {
        "name": "2 Weeks Premium",
        "duration_days": 14,
        "price": 5,
        "currency": "$",
        "features": [
            "20 cards per mass check",
            "All 18 charge gates",
            "Priority support",
            "No cooldown",
            "Save $1"
        ]
    },
    "1_month": {
        "name": "1 Month Premium",
        "duration_days": 30,
        "price": 10,
        "currency": "$",
        "features": [
            "20 cards per mass check",
            "All 18 charge gates",
            "Priority support",
            "No cooldown",
            "Save $2",
            "Best Value!"
        ]
    },
    "3_months": {
        "name": "3 Months Premium",
        "duration_days": 90,
        "price": 25,
        "currency": "$",
        "features": [
            "20 cards per mass check",
            "All 18 charge gates",
            "Priority support",
            "No cooldown",
            "Save $5",
            "VIP Support"
        ]
    }
}

def generate_invoice(user_id, username, plan_key, payment_method="Manual"):
    """Generate invoice for premium purchase"""
    try:
        os.makedirs(DATABASE_DIR, exist_ok=True)
        
        plan = PREMIUM_PLANS.get(plan_key)
        if not plan:
            return None
        
        # Generate invoice number
        invoice_number = f"INV-{datetime.now().strftime('%Y%m%d%H%M%S')}-{user_id}"
        
        # Calculate dates
        purchase_date = datetime.now()
        expiry_date = purchase_date + timedelta(days=plan['duration_days'])
        
        # Create invoice
        invoice = f"""
╔══════════════════════════════════════════════════════════╗
║              🎀 ONICHAN BOT - INVOICE 🎀              ║
╚══════════════════════════════════════════════════════════╝

📋 <b>Invoice Number:</b> <code>{invoice_number}</code>
📅 <b>Date:</b> {purchase_date.strftime('%Y-%m-%d %H:%M:%S')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

👤 <b>CUSTOMER INFORMATION</b>

<b>User ID:</b> <code>{user_id}</code>
<b>Username:</b> @{username}
<b>Telegram:</b> <a href="tg://user?id={user_id}">View Profile</a>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💎 <b>PLAN DETAILS</b>

<b>Plan:</b> {plan['name']}
<b>Duration:</b> {plan['duration_days']} days
<b>Start Date:</b> {purchase_date.strftime('%Y-%m-%d')}
<b>Expiry Date:</b> {expiry_date.strftime('%Y-%m-%d')}

<b>Features Included:</b>
"""
        
        for feature in plan['features']:
            invoice += f"  ✅ {feature}\n"
        
        invoice += f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💰 <b>PAYMENT DETAILS</b>

<b>Plan Price:</b> {plan['currency']}{plan['price']}
<b>Payment Method:</b> {payment_method}
<b>Status:</b> ✅ PAID

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📞 <b>SUPPORT</b>

<b>Contact:</b> @tu_bkl_hai
<b>Channel:</b> @krishnaslounge

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>Thank you for your purchase!</b>
Your premium access has been activated.

© 2025 Onichan Bot
"""
        
        # Save invoice
        invoice_record = f"{invoice_number}|{user_id}|@{username}|{plan_key}|{plan['price']}|{purchase_date}|{expiry_date}|{payment_method}\n"
        with open(INVOICES_FILE, 'a', encoding='utf-8') as f:
            f.write(invoice_record)
        
        # Save payment record
        payment_record = f"{datetime.now()}|{user_id}|@{username}|{plan['name']}|{plan['currency']}{plan['price']}|{payment_method}|SUCCESS\n"
        with open(PAYMENTS_FILE, 'a', encoding='utf-8') as f:
            f.write(payment_record)
        
        return {
            "invoice": invoice,
            "invoice_number": invoice_number,
            "expiry_date": expiry_date.strftime('%Y-%m-%d')
        }
    except Exception as e:
        print(f"Error generating invoice: {e}")
        return None

def get_plan_info(plan_key):
    """Get plan information"""
    return PREMIUM_PLANS.get(plan_key)

def get_all_plans():
    """Get all available plans"""
    return PREMIUM_PLANS

def get_total_revenue():
    """Calculate total revenue"""
    try:
        if not os.path.exists(PAYMENTS_FILE):
            return 0
        
        total = 0
        with open(PAYMENTS_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                parts = line.strip().split('|')
                if len(parts) >= 5:
                    price_str = parts[4].replace('$', '').strip()
                    try:
                        total += float(price_str)
                    except:
                        pass
        return total
    except:
        return 0

def get_payment_stats():
    """Get payment statistics"""
    try:
        if not os.path.exists(PAYMENTS_FILE):
            return {"total": 0, "count": 0, "plans": {}}
        
        stats = {"total": 0, "count": 0, "plans": {}}
        
        with open(PAYMENTS_FILE, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            stats["count"] = len(lines)
            
            for line in lines:
                parts = line.strip().split('|')
                if len(parts) >= 5:
                    plan_name = parts[3]
                    price_str = parts[4].replace('$', '').strip()
                    try:
                        price = float(price_str)
                        stats["total"] += price
                        stats["plans"][plan_name] = stats["plans"].get(plan_name, 0) + 1
                    except:
                        pass
        
        return stats
    except:
        return {"total": 0, "count": 0, "plans": {}}
