"""
================================================================================
  Premium Key Generation & Redemption System
  Uses _execute_with_retry for all database operations
================================================================================
"""

import os
import sys
import random
import string
import time
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.database import (
    get_connection_with_retry,
    is_db_connected,
    set_premium_sync,
    init_database_sync,
    _execute_with_retry
)

def ensure_db():
    """Ensure database is connected - always try to reconnect"""
    try:
        if not is_db_connected():
            print("[KeyGen] DB not connected, initializing...")
            init_database_sync()
        return True
    except Exception as e:
        print(f"[KeyGen] ensure_db error: {e}")
        return True

def generate_key(days, key_type="PREMIUM"):
    """Generate a random premium key with ONICHAN prefix"""
    chars = string.ascii_uppercase + string.digits
    part1 = ''.join(random.choices(chars, k=4))
    part2 = ''.join(random.choices(chars, k=4))
    part3 = ''.join(random.choices(chars, k=4))
    return f"ONICHAN-{part1}-{part2}-{part3}"

def create_batch_keys(count, days, created_by):
    """Generate multiple premium keys at once"""
    ensure_db()
    
    keys = []
    print(f"[KeyGen] Creating {count} keys for {days} days by {created_by}")
    
    for i in range(count):
        key_data = create_key(days, created_by)
        if key_data:
            keys.append(key_data)
            print(f"[KeyGen] Created key {i+1}/{count}")
        else:
            print(f"[KeyGen] Failed to create key {i+1}/{count}")
    
    print(f"[KeyGen] Total keys created: {len(keys)}")
    return keys

def format_keys_display(keys, days):
    """Format keys in a nice display format"""
    if not keys:
        return "No keys generated."
    
    output = f"""🔥 <b>ONICHAN Premium</b> 🔥

🎁 <b>Gift card codes are available:</b>

"""
    for i, key_data in enumerate(keys, 1):
        output += f"  {i} .  <code>{key_data['key']}</code>\n"
    
    output += f"""
⏰ <b>Duration:</b> {days} Days Subscription

💡 Type <code>/redeem CODE</code> in the chat.
✨ Enjoy your premium experience! 🎉"""
    
    return output

def create_key(days, created_by, key_type="PREMIUM"):
    """Create and save a premium key to PostgreSQL - with retry and duplicate handling"""
    max_attempts = 5
    
    for attempt in range(max_attempts):
        try:
            ensure_db()
            
            key = generate_key(days, key_type)
            
            # Handle creator_id conversion robustly
            creator_id = None
            if created_by is not None:
                try:
                    creator_id = int(created_by)
                except (ValueError, TypeError):
                    creator_id = None
            
            print(f"[KeyGen] Attempting to insert key: {key[:15]}... for {days} days by {creator_id}")
            
            result = _execute_with_retry("""
                INSERT INTO premium_keys (key, days, created_by, used, created_at)
                VALUES (%s, %s, %s, FALSE, NOW())
                RETURNING id, key
            """, (key, days, creator_id), fetch_one=True)
            
            print(f"[KeyGen] Insert result: {result}, type: {type(result)}")
            
            # Check result more robustly - RealDictCursor returns RealDictRow
            if result is not None:
                result_id = result.get('id') if hasattr(result, 'get') else (result['id'] if 'id' in result else None)
                if result_id:
                    print(f"[KeyGen] Successfully created key: {key}")
                    return {
                        "key": key,
                        "days": days,
                        "type": key_type,
                        "created_by": created_by,
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
            
            print(f"[KeyGen] Insert returned no id, attempt {attempt + 1}/{max_attempts}")
                
        except Exception as e:
            import traceback
            print(f"[KeyGen] Exception on attempt {attempt + 1}/{max_attempts}: {type(e).__name__}: {e}")
            print(f"[KeyGen] Traceback: {traceback.format_exc()}")
        
        time.sleep(0.3)
    
    print(f"[KeyGen] Failed after {max_attempts} attempts to create key")
    return None

def validate_key(key):
    """Check if key is valid and not redeemed using _execute_with_retry"""
    key = key.strip().upper()
    
    if not ensure_db():
        return None
    
    result = _execute_with_retry(
        "SELECT key, days, used, created_by, created_at FROM premium_keys WHERE key = %s",
        (key,), fetch_one=True
    )
    
    if result and not result.get("used"):
        return {
            "key": result["key"],
            "days": result["days"],
            "type": "PREMIUM",
            "created_by": str(result["created_by"]) if result.get("created_by") else "system",
            "timestamp": result["created_at"].strftime("%Y-%m-%d %H:%M:%S") if result.get("created_at") else ""
        }
    return None

def redeem_key(key, user_id, username):
    """Redeem a premium key and grant premium - uses rowcount to prevent race conditions"""
    key = key.strip().upper()
    
    if not ensure_db():
        return {"success": False, "message": "Database connection error!"}
    
    # First validate the key exists and is not used
    key_data = validate_key(key)
    if not key_data:
        return {"success": False, "message": "Invalid or already redeemed key!"}
    
    # Atomically mark key as used - returns rowcount
    rows_affected = _execute_with_retry("""
        UPDATE premium_keys
        SET used = TRUE, used_by = %s, used_at = NOW()
        WHERE key = %s AND used = FALSE
    """, (user_id, key), return_rowcount=True)
    
    # Check if we actually updated the row (race condition protection)
    if not rows_affected or rows_affected == 0:
        return {"success": False, "message": "Key already redeemed by another user!"}
    
    # Grant premium only after confirming key was marked as used
    set_premium_sync(user_id, key_data['days'])
    expiry_date = datetime.now() + timedelta(days=key_data['days'])
    
    return {
        "success": True,
        "days": key_data['days'],
        "expiry_date": expiry_date.strftime("%Y-%m-%d"),
        "message": f"✅ Key redeemed! {key_data['days']} days premium activated."
    }

def get_all_keys():
    """Get all generated keys using _execute_with_retry"""
    if not ensure_db():
        return []
    
    results = _execute_with_retry("""
        SELECT key, days, created_by, created_at, used
        FROM premium_keys ORDER BY created_at DESC
    """, fetch=True)
    
    if not results:
        return []
    
    return [{
        "key": row["key"],
        "days": str(row["days"]),
        "type": "PREMIUM",
        "created_by": str(row["created_by"]) if row.get("created_by") else "system",
        "timestamp": row["created_at"].strftime("%Y-%m-%d %H:%M:%S") if row.get("created_at") else "",
        "status": "REDEEMED" if row.get("used") else "ACTIVE"
    } for row in results]

def get_active_keys():
    """Get all active (unredeemed) keys"""
    return [k for k in get_all_keys() if k['status'] == 'ACTIVE']

def get_redeemed_keys():
    """Get all redeemed keys"""
    return [k for k in get_all_keys() if k['status'] == 'REDEEMED']

def get_key_stats():
    """Get key statistics using _execute_with_retry"""
    if not ensure_db():
        return {"total": 0, "active": 0, "redeemed": 0}
    
    total_result = _execute_with_retry("SELECT COUNT(*) as count FROM premium_keys", fetch_one=True)
    active_result = _execute_with_retry("SELECT COUNT(*) as count FROM premium_keys WHERE used = FALSE", fetch_one=True)
    
    total = total_result.get("count", 0) if total_result else 0
    active = active_result.get("count", 0) if active_result else 0
    
    return {"total": total, "active": active, "redeemed": total - active}

def burn_unused_keys():
    """Delete all unused (unredeemed) keys from database"""
    if not ensure_db():
        return {"success": False, "count": 0, "message": "Database connection error!"}
    
    try:
        count_result = _execute_with_retry(
            "SELECT COUNT(*) as count FROM premium_keys WHERE used = FALSE",
            fetch_one=True
        )
        count = count_result.get("count", 0) if count_result else 0
        
        if count == 0:
            return {"success": True, "count": 0, "message": "No unused keys to burn."}
        
        rows_deleted = _execute_with_retry(
            "DELETE FROM premium_keys WHERE used = FALSE",
            return_rowcount=True
        )
        
        return {
            "success": True,
            "count": rows_deleted or count,
            "message": f"Successfully burned {rows_deleted or count} unused keys!"
        }
    except Exception as e:
        print(f"[KeyGen] burn_unused_keys error: {e}")
        return {"success": False, "count": 0, "message": f"Error: {str(e)}"}
