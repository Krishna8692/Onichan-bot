"""
Account Creator — auto-create accounts on target sites using
generated identity + disposable email inboxes.
"""

import os
import sys
import re
import time
import random
import string
import asyncio
import requests
from typing import Optional, Dict, Any, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
]

TEMP_MAIL_DOMAINS = [
    "guerrillamail.com", "mailinator.com", "yopmail.com",
    "trashmail.com", "tempmail.plus", "sharklasers.com",
]

SUPPORTED_SITES = {
    "shopify":    "Creates a Shopify customer account",
    "netflix":    "Creates a Netflix free-trial account (requires card)",
    "amazon":     "Creates an Amazon account",
    "ebay":       "Creates an eBay account",
    "paypal":     "Creates a PayPal personal account",
}


def get_spoofed_headers() -> Dict[str, str]:
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": random.choice([
            "en-US,en;q=0.9", "en-GB,en;q=0.8", "fr-FR,fr;q=0.9",
        ]),
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }


def _gen_temp_email(name: str) -> str:
    suffix = "".join(random.choices(string.digits, k=4))
    domain = random.choice(TEMP_MAIL_DOMAINS)
    return f"{name.lower().replace(' ', '')}{suffix}@{domain}"


def _gen_password(length: int = 14) -> str:
    chars = string.ascii_letters + string.digits + "!@#$"
    pwd = (
        random.choice(string.uppercase_letters if hasattr(string, 'uppercase_letters') else string.ascii_uppercase) +
        random.choice(string.digits) +
        random.choice("!@#$") +
        "".join(random.choices(chars, k=length - 3))
    )
    return "".join(random.sample(pwd, len(pwd)))


def generate_account_details(country: str = "US") -> Dict[str, str]:
    try:
        from faker import Faker
        locale_map = {
            "US": "en_US", "UK": "en_GB", "CA": "en_CA",
            "AU": "en_AU", "DE": "de_DE", "FR": "fr_FR",
        }
        locale = locale_map.get(country.upper(), "en_US")
        fake = Faker(locale)
        first = fake.first_name()
        last = fake.last_name()
        name = f"{first} {last}"
        email = _gen_temp_email(f"{first}{last[0]}")
        password = _gen_password()
        phone = fake.phone_number()
        street = fake.street_address()
        city = fake.city()
        postcode = fake.postcode()
        return {
            "name": name, "first": first, "last": last,
            "email": email, "password": password,
            "phone": phone, "street": street, "city": city,
            "postcode": postcode, "country": country.upper()
        }
    except ImportError:
        # fallback without Faker
        first = random.choice(["James", "Emma", "Noah", "Olivia", "Liam"])
        last = random.choice(["Smith", "Johnson", "Williams", "Brown", "Jones"])
        name = f"{first} {last}"
        email = _gen_temp_email(f"{first}{last[0]}")
        return {
            "name": name, "first": first, "last": last,
            "email": email, "password": _gen_password(),
            "phone": f"+1{''.join(random.choices(string.digits, k=10))}",
            "street": "123 Main St", "city": "New York", "postcode": "10001",
            "country": "US"
        }


def create_mailinator_inbox(username: str) -> str:
    """Return a Mailinator email address (no API key needed for basic use)."""
    return f"{username}@mailinator.com"


async def poll_inbox_for_verification(email: str, timeout: int = 60) -> Optional[str]:
    """
    Poll Mailinator public API for a verification link/code.
    Returns the first URL or OTP code found in the inbox.
    """
    username = email.split("@")[0]
    url = f"https://www.mailinator.com/api/v2/domains/mailinator.com/inboxes/{username}/messages"
    headers = get_spoofed_headers()
    deadline = time.time() + timeout

    while time.time() < deadline:
        try:
            resp = requests.get(url, headers=headers, timeout=8)
            if resp.status_code == 200:
                msgs = resp.json().get("msgs", [])
                if msgs:
                    msg_id = msgs[0].get("id", "")
                    detail_url = (
                        f"https://www.mailinator.com/api/v2/domains/mailinator.com"
                        f"/inboxes/{username}/messages/{msg_id}"
                    )
                    detail = requests.get(detail_url, headers=headers, timeout=8)
                    if detail.status_code == 200:
                        body = detail.json().get("data", {}).get("parts", [{}])[0].get("body", "")
                        urls = re.findall(r'https?://[^\s"\'<>]+', body)
                        if urls:
                            return urls[0]
                        otps = re.findall(r'\b\d{4,8}\b', body)
                        if otps:
                            return otps[0]
        except Exception:
            pass
        await asyncio.sleep(5)
    return None


def create_shopify_account(store_url: str, details: Dict[str, str],
                           proxy: Optional[str] = None) -> Dict[str, Any]:
    """Create a Shopify customer account on a given store."""
    store = store_url.rstrip("/")
    if not store.startswith("http"):
        store = f"https://{store}"
    url = f"{store}/account"
    headers = get_spoofed_headers()
    proxies = {"http": proxy, "https": proxy} if proxy else None

    try:
        sess = requests.Session()
        resp = sess.get(url, headers=headers, proxies=proxies, timeout=10)
        token_match = re.search(
            r'name="authenticity_token"\s+value="([^"]+)"', resp.text)
        token = token_match.group(1) if token_match else ""

        payload = {
            "form_type": "create_customer",
            "utf8": "✓",
            "authenticity_token": token,
            "customer[first_name]": details["first"],
            "customer[last_name]": details["last"],
            "customer[email]": details["email"],
            "customer[password]": details["password"],
            "customer[password_confirmation]": details["password"],
        }
        r = sess.post(
            f"{store}/account", data=payload,
            headers=headers, proxies=proxies, timeout=15,
            allow_redirects=True
        )
        success = "account" in r.url.lower() and r.status_code in (200, 302)
        return {
            "success": success,
            "email": details["email"],
            "password": details["password"],
            "status_code": r.status_code,
            "message": "Account created" if success else f"HTTP {r.status_code}",
        }
    except Exception as e:
        return {"success": False, "message": str(e)}


def format_account_result(result: Dict[str, Any], details: Dict[str, str]) -> str:
    status = "✅ Created" if result.get("success") else "❌ Failed"
    return (
        f"{status}\n"
        f"📧 Email: <code>{details.get('email', 'N/A')}</code>\n"
        f"🔑 Pass: <code>{details.get('password', 'N/A')}</code>\n"
        f"👤 Name: {details.get('name', 'N/A')}\n"
        f"ℹ️ {result.get('message', '')}"
    )
