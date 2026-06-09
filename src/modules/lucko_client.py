"""
Lucko.ai Casino API Client
Staging: https://staging.aig1234.com
Production: https://api.aigapi.com

Signing algorithm (MD5):
  1. Collect all non-empty params (including agent_id, excluding sign)
  2. Sort by ASCII key
  3. Join as key1=val1&key2=val2...
  4. Prepend secret: SECRET&key1=val1&...
  5. md5(above string) → sign

All requests: POST JSON with Content-Type: application/json
Game list:    GET with query params
Balance:      GET with query params
"""
import os
import hashlib
import time
import requests as _http
from typing import Dict, Any, Optional

_SESSION = _http.Session()
_SESSION.headers.update({'Content-Type': 'application/json'})


def _cfg():
    agent_id = os.environ.get('LUCKO_AGENT_ID', '').strip()
    secret   = os.environ.get('LUCKO_SECRET',   '').strip()
    base     = os.environ.get('LUCKO_BASE_URL', '').strip()
    if not base:
        base = 'https://api.aigapi.com' if agent_id else 'https://staging.aig1234.com'
    return agent_id, secret, base.rstrip('/')


def is_configured() -> bool:
    a, s, _ = _cfg()
    return bool(a and s)


def _sign(secret: str, params: dict) -> str:
    """md5(SECRET&key1=v1&key2=v2...) — non-empty params only, sorted by ASCII key."""
    non_empty = {k: v for k, v in params.items() if v is not None and str(v) != ''}
    sorted_pairs = '&'.join(f"{k}={non_empty[k]}" for k in sorted(non_empty))
    raw = f"{secret}&{sorted_pairs}"
    return hashlib.md5(raw.encode('utf-8')).hexdigest()


def _ts() -> int:
    return int(time.time() * 1000)


def _post(endpoint: str, extra: dict, timeout: int = 15) -> Dict[str, Any]:
    agent_id, secret, base = _cfg()
    if not agent_id or not secret:
        return {'code': -1, 'message': 'Lucko API credentials not configured'}
    params = {'agent_id': agent_id, 'timestamp': _ts(), **extra}
    params['sign'] = _sign(secret, params)
    url = f"{base}/{endpoint.lstrip('/')}"
    try:
        r = _SESSION.post(url, json=params, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except _http.exceptions.Timeout:
        return {'code': -2, 'message': 'Request timed out'}
    except _http.exceptions.HTTPError as e:
        return {'code': -3, 'message': f'HTTP {e.response.status_code}'}
    except Exception as e:
        return {'code': -1, 'message': str(e)}


def _get(endpoint: str, extra: dict, timeout: int = 15) -> Dict[str, Any]:
    agent_id, secret, base = _cfg()
    if not agent_id or not secret:
        return {'code': -1, 'message': 'Lucko API credentials not configured'}
    params = {'agent_id': agent_id, 'timestamp': _ts(), **extra}
    params['sign'] = _sign(secret, params)
    url = f"{base}/{endpoint.lstrip('/')}"
    try:
        r = _SESSION.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except _http.exceptions.Timeout:
        return {'code': -2, 'message': 'Request timed out'}
    except _http.exceptions.HTTPError as e:
        return {'code': -3, 'message': f'HTTP {e.response.status_code}'}
    except Exception as e:
        return {'code': -1, 'message': str(e)}


# ── Member ────────────────────────────────────────────────────────────────────

def create_member(user_id: str, user_name: str = '') -> Dict[str, Any]:
    """Register a member. code=700102 means already registered (safe to ignore)."""
    return _post('api/member/create', {
        'user_id':   str(user_id),
        'user_name': user_name or str(user_id),
    })


def guest_login(platform: str = 'web') -> Dict[str, Any]:
    """Get a session token for a guest user.  Returns data.token."""
    return _post('api/guest/login', {'platform': platform})


def member_login(user_id: str, token: str, platform: str = 'web') -> Dict[str, Any]:
    """
    Get a personalised game URL for user_id.
    token   — session token obtained from guest_login().
    Returns data.url  (full H5 game lobby URL) and data.token (refreshed token).
    """
    return _post('api/member/login', {
        'user_id':  str(user_id),
        'token':    token,
        'platform': platform,
    })


def member_logout(user_id: str) -> Dict[str, Any]:
    return _post('api/member/logout', {'user_id': str(user_id)})


# ── Wallet ────────────────────────────────────────────────────────────────────

def deposit(user_id: str, amount: float, txn_id: str) -> Dict[str, Any]:
    """Credit user's Lucko wallet (transfer in from agent)."""
    return _post('api/wallet/deposit', {
        'user_id': str(user_id),
        'amount':  f"{amount:.2f}",
        'txn_id':  str(txn_id),
    })


def withdraw(user_id: str, amount: float, txn_id: str) -> Dict[str, Any]:
    """Debit user's Lucko wallet (transfer back to agent)."""
    return _post('api/wallet/withdraw', {
        'user_id': str(user_id),
        'amount':  f"{amount:.2f}",
        'txn_id':  str(txn_id),
    })


def get_balance(user_id: str) -> Optional[float]:
    """Return the user's current Lucko wallet balance, or None on error."""
    res = _get('api/wallet/balance', {'user_id': str(user_id)})
    if res.get('code') == 200:
        try:
            return float(res.get('data', {}).get('balance', 0))
        except (TypeError, ValueError):
            return None
    return None


# ── Games ─────────────────────────────────────────────────────────────────────

def get_game_list() -> Dict[str, Any]:
    """
    Returns all game categories with their rooms.
    Response shape:
      data.list[]: {game_id, game_name:{en-US, zh-CN}, rooms:[{inst_id, cover, ...}]}
    """
    return _get('api/game/list', {})


def get_latest_transactions(last_time: int = 0) -> Dict[str, Any]:
    """
    Poll bet/payout events since last_time (ms epoch).
    NOTE: user_id must be excluded from the sign for this endpoint.
    Returns data.transactions[]: {user_id, game_id, inst_id, bet_amount, win_amount, ...}
    """
    agent_id, secret, base = _cfg()
    if not agent_id or not secret:
        return {'code': -1, 'message': 'Lucko API credentials not configured'}
    params_for_sign = {'agent_id': agent_id, 'timestamp': _ts(), 'last_time': int(last_time)}
    sign_val = _sign(secret, params_for_sign)
    query_params = {**params_for_sign, 'sign': sign_val}
    url = f"{base}/api/game/transaction/latest"
    try:
        r = _SESSION.get(url, params=query_params, timeout=20)
        r.raise_for_status()
        return r.json()
    except _http.exceptions.Timeout:
        return {'code': -2, 'message': 'Request timed out'}
    except _http.exceptions.HTTPError as e:
        return {'code': -3, 'message': f'HTTP {e.response.status_code}'}
    except Exception as e:
        return {'code': -1, 'message': str(e)}


def ping() -> Dict[str, Any]:
    """Health-check: create a test member; code=200 or 700102 means API is up."""
    return create_member('ping_probe', 'ping_probe')
