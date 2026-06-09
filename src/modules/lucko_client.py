"""
Lucko.ai Casino API Client
MD5-signed requests to api.aigapi.com (prod) or staging.aig1234.com (staging).

Signing algorithm:
  md5(SECRET + "&" + sorted_key=value_pairs_joined_by_&)
All requests: POST JSON, gzip-compressed responses.
"""
import os
import hashlib
import requests as _http
from typing import Dict, Any, Optional

_SESSION = _http.Session()
_SESSION.headers.update({'Content-Type': 'application/json'})


def _cfg():
    agent_id = os.environ.get('LUCKO_AGENT_ID', '').strip()
    secret = os.environ.get('LUCKO_SECRET', '').strip()
    base = os.environ.get('LUCKO_BASE_URL', '').strip()
    if not base:
        base = 'https://api.aigapi.com' if agent_id else 'https://staging.aig1234.com'
    return agent_id, secret, base


def is_configured() -> bool:
    a, s, _ = _cfg()
    return bool(a and s)


def _sign(secret: str, params: dict) -> str:
    """md5(SECRET&key1=v1&key2=v2...) — params sorted by ASCII key."""
    sorted_pairs = '&'.join(f"{k}={params[k]}" for k in sorted(params))
    raw = f"{secret}&{sorted_pairs}"
    return hashlib.md5(raw.encode('utf-8')).hexdigest()


def _call(endpoint: str, params: dict, timeout: int = 15) -> Dict[str, Any]:
    agent_id, secret, base_url = _cfg()
    if not agent_id or not secret:
        return {'code': -1, 'msg': 'Lucko API credentials not configured (LUCKO_AGENT_ID / LUCKO_SECRET missing)'}
    payload = dict(params)
    payload['agent_id'] = agent_id
    payload['sign'] = _sign(secret, payload)
    url = f"{base_url.rstrip('/')}/{endpoint.lstrip('/')}"
    try:
        resp = _SESSION.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except _http.exceptions.Timeout:
        return {'code': -2, 'msg': 'Lucko API request timed out'}
    except _http.exceptions.HTTPError as e:
        return {'code': -3, 'msg': f'HTTP error: {e}'}
    except Exception as e:
        return {'code': -1, 'msg': str(e)}


def ping() -> Dict[str, Any]:
    return _call('api/ping', {})


def create_member(agent_member_id: str, nickname: str = '') -> Dict[str, Any]:
    """Register / get-or-create a Lucko member. Safe to call repeatedly."""
    return _call('api/member/create', {
        'agent_member_id': str(agent_member_id),
        'nickname': nickname or str(agent_member_id),
    })


def get_member_balance(agent_member_id: str) -> Optional[float]:
    """Return the Lucko-side credit balance, or None on error."""
    res = _call('api/member/balance', {'agent_member_id': str(agent_member_id)})
    if res.get('code') == 0:
        data = res.get('data') or {}
        try:
            return float(data.get('balance', 0))
        except (TypeError, ValueError):
            return None
    return None


def transfer_in(agent_member_id: str, amount: float, order_id: str) -> Dict[str, Any]:
    """Load credits from agent wallet → member wallet (before play)."""
    return _call('api/wallet/transfer-in', {
        'agent_member_id': str(agent_member_id),
        'amount': f"{amount:.2f}",
        'order_id': str(order_id),
    })


def transfer_out(agent_member_id: str, amount: float, order_id: str) -> Dict[str, Any]:
    """Withdraw credits from member wallet → agent wallet (after play)."""
    return _call('api/wallet/transfer-out', {
        'agent_member_id': str(agent_member_id),
        'amount': f"{amount:.2f}",
        'order_id': str(order_id),
    })


def transfer_out_all(agent_member_id: str, order_id: str) -> Dict[str, Any]:
    """Sweep entire member balance back to agent wallet."""
    return _call('api/wallet/transfer-out-all', {
        'agent_member_id': str(agent_member_id),
        'order_id': str(order_id),
    })


def get_game_list(game_type: str = '') -> Dict[str, Any]:
    """Fetch available games. game_type: 'slot'|'live'|'table'|'' (all)."""
    params = {}
    if game_type:
        params['game_type'] = game_type
    return _call('api/game/list', params)


def get_game_url(game_id: str, agent_member_id: str,
                 return_url: str = '', lang: str = 'en') -> Dict[str, Any]:
    """Get a playable launch URL for this member + game."""
    params = {
        'game_id': str(game_id),
        'agent_member_id': str(agent_member_id),
        'lang': lang,
    }
    if return_url:
        params['return_url'] = return_url
    return _call('api/game/launch', params)


def get_transfer_status(order_id: str) -> Dict[str, Any]:
    return _call('api/wallet/transfer-status', {'order_id': str(order_id)})
