import json
import os
import time
import threading

_lock = threading.Lock()
_cache = {}
_cache_ts = 0
_CACHE_TTL = 5


def _config_file():
    base = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "gate_api_config.json")


def _load():
    global _cache, _cache_ts
    now = time.time()
    with _lock:
        if now - _cache_ts < _CACHE_TTL:
            return _cache.copy()
        try:
            with open(_config_file(), "r") as f:
                _cache = json.load(f)
        except Exception:
            _cache = {}
        _cache_ts = now
        return _cache.copy()


def _save(data):
    global _cache, _cache_ts
    with _lock:
        with open(_config_file(), "w") as f:
            json.dump(data, f, indent=2)
        _cache = data.copy()
        _cache_ts = time.time()


def get_gate_cfg(key: str, default: str = "") -> str:
    """Return stored value for key, falling back to default if missing or empty."""
    data = _load()
    val = data.get(key, "")
    return val if val else default


def set_gate_cfg(key: str, value: str):
    """Persist a config value."""
    data = _load()
    data[key] = value
    _save(data)


def get_all_gate_cfg() -> dict:
    """Return full config dict for the admin UI."""
    return _load()


GATE_API_DEFAULTS = {
    "netherex_stripe_url":   "https://checker.netherex.xyz/strauth.php",
    "netherex_stripe_key":   "netherex_auth_shorien_wpxp60bhe",
    "netherex_shopify_url":  "https://checker.netherex.xyz/autosh.php",
    "netherex_shopify_key":  "netherex_auth_autosh",
    "netherex_paypal_url":   "https://checker.netherex.xyz/paypalcheck.php",
    "razorpay_api_url":      "https://api.barryxapi.xyz/razorpay",
    "razorpay_api_key":      "BRY-KESNP-TUPWH-JFOT9",
    "cybor_stv1_url":        "http://206.206.78.217:1011/",
    "cybor_stv2_url":        "http://206.206.78.217:1012/",
    "cybor_stv3_url":        "http://206.206.78.217:1013/",
    "cybor_shopii_url":      "https://cyborxchecker.com/api/autog.php",
    "approvedchkr_url":      "https://approvedchkr.store/api/v1/check.php",
    "stripe_charge_url":     "http://15.204.130.9:6969/check",
    "stripe_charge_url2":    "http://194.150.166.130:5000/",
    "freechk_stripe_url":    "https://freechk.cards/free/stripe.php",
    "freechk_braintree_url": "https://freechk.cards/free/braintree.php",
    "freechk_square_url":    "https://freechk.cards/free/square.php",
    "freechk_paypal_url":    "https://freechk.cards/free/paypal.php",
    "nyvexis_stripe_url":    "https://api.nyvexis.com/stripeauth/",
    "nyvexis_braintree_url": "https://api.nyvexis.com/braintree/",
    "nyvexis_paypal_url":    "https://api.nyvexis.com/paypal/",
    "square_api_url":        "http://138.128.240.15:8006/square",
    "braintree_api_url":     "https://api.barryxapi.xyz/braintree_auth",
    "braintree_api_key":     "BRY-KESNP-TUPWH-JFOT9",
    "rzpauto_url":           "https://rzpauto-production.up.railway.app/rzp",
}
