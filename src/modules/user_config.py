"""
================================================================================
  User Configuration Module
  Store user-specific settings for Shopify sites and proxies
================================================================================
"""

import os
import sys
import json
import requests
import asyncio
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DATABASE_DIR

USER_CONFIG_FILE = f"{DATABASE_DIR}/user_configs.json"

def ensure_config_file():
    """Create config file if it doesn't exist"""
    os.makedirs(DATABASE_DIR, exist_ok=True)
    if not os.path.exists(USER_CONFIG_FILE):
        with open(USER_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump({}, f)

def load_all_configs():
    """Load all user configs"""
    ensure_config_file()
    try:
        with open(USER_CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}

def save_all_configs(configs):
    """Save all user configs"""
    ensure_config_file()
    with open(USER_CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(configs, f, indent=2)

def get_user_config(user_id):
    """Get config for a specific user"""
    configs = load_all_configs()
    user_id_str = str(user_id)
    
    if user_id_str not in configs:
        return {
            'site': None,
            'proxy': None,
            'sites': [],
            'proxies': []
        }
    return configs[user_id_str]

async def check_proxy_live(proxy):
    """Check if proxy is working by making a test request"""
    try:
        proxy_str = proxy.strip()
        if not proxy_str:
            return False, "Empty proxy"
        
        # Parse proxy format: ip:port or ip:port:user:pass or user:pass@ip:port
        proxies_dict = None
        
        if '@' in proxy_str:
            # Format: user:pass@ip:port
            auth, addr = proxy_str.rsplit('@', 1)
            proxies_dict = {
                'http': f'http://{auth}@{addr}',
                'https': f'http://{auth}@{addr}'
            }
        elif proxy_str.count(':') == 3:
            # Format: ip:port:user:pass
            parts = proxy_str.split(':')
            proxies_dict = {
                'http': f'http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}',
                'https': f'http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}'
            }
        elif proxy_str.count(':') == 1:
            # Format: ip:port
            proxies_dict = {
                'http': f'http://{proxy_str}',
                'https': f'http://{proxy_str}'
            }
        else:
            return False, "Invalid proxy format"
        
        # Test proxy with multiple endpoints
        test_urls = [
            'https://httpbin.org/ip',
            'http://httpbin.org/ip',
            'https://api.ipify.org?format=json'
        ]
        
        for test_url in test_urls:
            try:
                response = requests.get(test_url, proxies=proxies_dict, timeout=10, verify=False)
                if response.status_code == 200:
                    try:
                        data = response.json()
                        ip = data.get('origin') or data.get('ip') or 'Working'
                        return True, ip
                    except:
                        return True, "Working"
            except:
                continue
        
        return False, "No response from proxy"
    except Exception as e:
        return False, str(e)[:50]


def is_valid_site(site_url):
    """Check if URL looks like a valid Shopify site (not a proxy)"""
    if ':' in site_url:
        parts = site_url.replace('https://', '').replace('http://', '').split(':')
        if len(parts) > 2:
            return False
        if len(parts) == 2:
            try:
                port = int(parts[1].split('/')[0])
                if port > 443 and port != 8080:
                    return False
            except:
                return False
    if site_url.count(':') >= 3:
        return False
    return True


def set_user_site(user_id, site_url):
    """Set default Shopify site for user"""
    if not is_valid_site(site_url):
        return False
    
    configs = load_all_configs()
    user_id_str = str(user_id)
    
    if user_id_str not in configs:
        configs[user_id_str] = {'site': None, 'proxy': None, 'sites': [], 'proxies': []}
    
    if not site_url.startswith('http'):
        site_url = f'https://{site_url}'
    site_url = site_url.rstrip('/')
    
    configs[user_id_str]['site'] = site_url
    
    if site_url not in configs[user_id_str].get('sites', []):
        if 'sites' not in configs[user_id_str]:
            configs[user_id_str]['sites'] = []
        configs[user_id_str]['sites'].append(site_url)
        if len(configs[user_id_str]['sites']) > 10:
            configs[user_id_str]['sites'] = configs[user_id_str]['sites'][-10:]
    
    save_all_configs(configs)
    return True

def set_user_proxy(user_id, proxy):
    """Set proxy for user"""
    configs = load_all_configs()
    user_id_str = str(user_id)
    
    if user_id_str not in configs:
        configs[user_id_str] = {'site': None, 'proxy': None, 'sites': [], 'proxies': []}
    
    configs[user_id_str]['proxy'] = proxy
    
    if proxy and proxy not in configs[user_id_str].get('proxies', []):
        if 'proxies' not in configs[user_id_str]:
            configs[user_id_str]['proxies'] = []
        configs[user_id_str]['proxies'].append(proxy)
        if len(configs[user_id_str]['proxies']) > 5:
            configs[user_id_str]['proxies'] = configs[user_id_str]['proxies'][-5:]
    
    save_all_configs(configs)
    return True

def clear_user_site(user_id):
    """Clear default site for user"""
    configs = load_all_configs()
    user_id_str = str(user_id)
    
    if user_id_str in configs:
        configs[user_id_str]['site'] = None
        save_all_configs(configs)
    return True

def clear_user_proxy(user_id):
    """Clear proxy for user"""
    configs = load_all_configs()
    user_id_str = str(user_id)
    
    if user_id_str in configs:
        configs[user_id_str]['proxy'] = None
        save_all_configs(configs)
    return True

def get_user_sites(user_id):
    """Get saved sites for user"""
    config = get_user_config(user_id)
    return config.get('sites', [])

def get_user_proxies(user_id):
    """Get saved proxies for user"""
    config = get_user_config(user_id)
    return config.get('proxies', [])

def remove_user_site(user_id, site_url):
    """Remove a site from user's saved sites"""
    configs = load_all_configs()
    user_id_str = str(user_id)
    
    if user_id_str in configs and 'sites' in configs[user_id_str]:
        if site_url in configs[user_id_str]['sites']:
            configs[user_id_str]['sites'].remove(site_url)
            if configs[user_id_str]['site'] == site_url:
                configs[user_id_str]['site'] = None
            save_all_configs(configs)
            return True
    return False

def remove_user_proxy(user_id, proxy):
    """Remove a proxy from user's saved proxies"""
    configs = load_all_configs()
    user_id_str = str(user_id)
    
    if user_id_str in configs and 'proxies' in configs[user_id_str]:
        if proxy in configs[user_id_str]['proxies']:
            configs[user_id_str]['proxies'].remove(proxy)
            if configs[user_id_str]['proxy'] == proxy:
                configs[user_id_str]['proxy'] = None
            save_all_configs(configs)
            return True
    return False


def clear_all_sites(user_id):
    """Clear all saved sites for user"""
    configs = load_all_configs()
    user_id_str = str(user_id)
    
    if user_id_str in configs:
        configs[user_id_str]['site'] = None
        configs[user_id_str]['sites'] = []
        save_all_configs(configs)
    return True


def clear_all_proxies(user_id):
    """Clear all saved proxies for user"""
    configs = load_all_configs()
    user_id_str = str(user_id)
    
    if user_id_str in configs:
        configs[user_id_str]['proxy'] = None
        configs[user_id_str]['proxies'] = []
        save_all_configs(configs)
    return True


def clean_invalid_sites(user_id):
    """Remove invalid sites (proxies saved as sites)"""
    configs = load_all_configs()
    user_id_str = str(user_id)
    
    if user_id_str in configs and 'sites' in configs[user_id_str]:
        valid_sites = [s for s in configs[user_id_str]['sites'] if is_valid_site(s)]
        removed = len(configs[user_id_str]['sites']) - len(valid_sites)
        configs[user_id_str]['sites'] = valid_sites
        if configs[user_id_str].get('site') and not is_valid_site(configs[user_id_str]['site']):
            configs[user_id_str]['site'] = None
        save_all_configs(configs)
        return removed
    return 0


def get_user_email(user_id):
    """Get user's billing email for checkout"""
    configs = load_all_configs()
    user_id_str = str(user_id)
    if user_id_str in configs:
        return configs[user_id_str].get('billing_email')
    return None


def set_user_email(user_id, email):
    """Set user's billing email for checkout"""
    configs = load_all_configs()
    user_id_str = str(user_id)
    if user_id_str not in configs:
        configs[user_id_str] = {'site': None, 'proxy': None, 'sites': [], 'proxies': []}
    configs[user_id_str]['billing_email'] = email
    save_all_configs(configs)
    return True


def clear_user_email(user_id):
    """Clear user's billing email"""
    configs = load_all_configs()
    user_id_str = str(user_id)
    if user_id_str in configs:
        configs[user_id_str]['billing_email'] = None
        save_all_configs(configs)
    return True


def get_captcha_key(user_id):
    """Get user's captcha solver API key"""
    configs = load_all_configs()
    user_id_str = str(user_id)
    if user_id_str in configs:
        return configs[user_id_str].get('captcha_key')
    return None


def set_captcha_key(user_id, api_key):
    """Set user's captcha solver API key"""
    configs = load_all_configs()
    user_id_str = str(user_id)
    if user_id_str not in configs:
        configs[user_id_str] = {'site': None, 'proxy': None, 'sites': [], 'proxies': []}
    configs[user_id_str]['captcha_key'] = api_key
    save_all_configs(configs)
    return True


def clear_captcha_key(user_id):
    """Clear user's captcha solver API key"""
    configs = load_all_configs()
    user_id_str = str(user_id)
    if user_id_str in configs:
        configs[user_id_str]['captcha_key'] = None
        save_all_configs(configs)
    return True
