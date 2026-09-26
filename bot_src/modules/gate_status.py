import json
import os
import time
import threading

_lock = threading.Lock()
_cache = {}
_cache_ts = 0
_CACHE_TTL = 5

def _status_file():
    base = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "gate_status.json")

def _load():
    global _cache, _cache_ts
    now = time.time()
    with _lock:
        if now - _cache_ts < _CACHE_TTL:
            return _cache.copy()
        try:
            with open(_status_file(), "r") as f:
                _cache = json.load(f)
        except Exception:
            _cache = {}
        _cache_ts = now
        return _cache.copy()

def _save(data):
    global _cache, _cache_ts
    with _lock:
        with open(_status_file(), "w") as f:
            json.dump(data, f, indent=2)
        _cache = data.copy()
        _cache_ts = time.time()

def is_gate_offline(gate_name: str) -> bool:
    # File stores True = ONLINE, False/missing = OFFLINE
    data = _load()
    return not bool(data.get(gate_name, True))

def set_gate_offline(gate_name: str, offline: bool):
    # Store inverted: True = online, False = offline (matches panel semantics)
    data = _load()
    data[gate_name] = not offline
    _save(data)

def get_all_gate_status() -> dict:
    return _load()

def offline_message(cmd_name: str) -> str:
    return (
        "🚫 <b>CHECKER MODULE OFFLINE</b>\n\n"
        f"┌─ 🧩 Module: \"/{cmd_name}\"\n"
        "├─ 📡 Status: ❌ Disabled\n"
        "├─ 🔧 Operation: Maintenance / Optimization\n"
        "├─ 🕒 ETA: Not specified\n"
        "└─ ⚠️ Access: Restricted temporarily\n\n"
        "╰─➤ Our systems are undergoing upgrades to enhance speed, accuracy & reliability\n\n"
        "⏳ Please retry after some time\n"
        "🔔 Updates will be pushed automatically\n\n"
        "💠 Thank you for your patience"
    )
