"""
indicators.py — Pure-Python technical indicators for the signal bot.

Inputs: list of candle dicts [{ts, open, high, low, close, volume}]
Output: flat dict of indicator values
"""

from typing import List, Dict, Any, Optional
import math


def _closes(candles: List[Dict]) -> List[float]:
    return [c["close"] for c in candles]

def _highs(candles: List[Dict]) -> List[float]:
    return [c["high"] for c in candles]

def _lows(candles: List[Dict]) -> List[float]:
    return [c["low"] for c in candles]


# ── EMA ────────────────────────────────────────────────────────────────────────
def ema(values: List[float], period: int) -> List[float]:
    if len(values) < period:
        return []
    k = 2 / (period + 1)
    result = [sum(values[:period]) / period]
    for v in values[period:]:
        result.append(v * k + result[-1] * (1 - k))
    return result


# ── RSI ────────────────────────────────────────────────────────────────────────
def rsi(values: List[float], period: int = 14) -> Optional[float]:
    if len(values) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(values)):
        d = values[i] - values[i - 1]
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


# ── MACD ───────────────────────────────────────────────────────────────────────
def macd(values: List[float], fast: int = 12, slow: int = 26, signal: int = 9):
    """Returns (macd_line, signal_line, histogram) — each as the latest value."""
    if len(values) < slow + signal:
        return None, None, None
    ema_fast = ema(values, fast)
    ema_slow = ema(values, slow)
    # align: ema_slow is shorter by (slow - fast) elements
    offset = slow - fast
    macd_line = [ema_fast[offset + i] - ema_slow[i] for i in range(len(ema_slow))]
    if len(macd_line) < signal:
        return None, None, None
    sig_line = ema(macd_line, signal)
    if not sig_line:
        return None, None, None
    m = round(macd_line[-1], 6)
    s = round(sig_line[-1], 6)
    h = round(m - s, 6)
    return m, s, h


# ── Bollinger Bands ────────────────────────────────────────────────────────────
def bollinger(values: List[float], period: int = 20, num_std: float = 2.0):
    """Returns (upper, mid, lower, %B) — latest values only."""
    if len(values) < period:
        return None, None, None, None
    window = values[-period:]
    mid = sum(window) / period
    variance = sum((v - mid) ** 2 for v in window) / period
    std = math.sqrt(variance)
    upper = round(mid + num_std * std, 6)
    lower = round(mid - num_std * std, 6)
    mid = round(mid, 6)
    price = values[-1]
    pct_b = round((price - lower) / (upper - lower) * 100, 1) if (upper - lower) > 0 else 50.0
    return upper, mid, lower, pct_b


# ── ATR ────────────────────────────────────────────────────────────────────────
def atr(candles: List[Dict], period: int = 14) -> Optional[float]:
    if len(candles) < period + 1:
        return None
    trs = []
    for i in range(1, len(candles)):
        h = candles[i]["high"]
        l = candles[i]["low"]
        pc = candles[i - 1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    if len(trs) < period:
        return None
    a = sum(trs[:period]) / period
    for tr in trs[period:]:
        a = (a * (period - 1) + tr) / period
    return round(a, 6)


# ── Candlestick pattern detection ──────────────────────────────────────────────
def detect_patterns(candles: List[Dict]) -> List[str]:
    """Return list of detected pattern names from the last 3 candles."""
    patterns = []
    if len(candles) < 3:
        return patterns
    c0, c1, c2 = candles[-3], candles[-2], candles[-1]

    def body(c):
        return abs(c["close"] - c["open"])

    def upper_wick(c):
        return c["high"] - max(c["open"], c["close"])

    def lower_wick(c):
        return min(c["open"], c["close"]) - c["low"]

    def is_bullish(c):
        return c["close"] > c["open"]

    def is_bearish(c):
        return c["close"] < c["open"]

    b2 = body(c2)
    b1 = body(c1)

    # Doji
    if b2 < (c2["high"] - c2["low"]) * 0.1:
        patterns.append("Doji")

    # Hammer (bullish reversal)
    if (lower_wick(c2) > b2 * 2 and upper_wick(c2) < b2 * 0.5
            and is_bearish(c1)):
        patterns.append("Hammer")

    # Shooting Star (bearish reversal)
    if (upper_wick(c2) > b2 * 2 and lower_wick(c2) < b2 * 0.5
            and is_bullish(c1)):
        patterns.append("Shooting Star")

    # Bullish Engulfing
    if (is_bullish(c2) and is_bearish(c1)
            and c2["open"] < c1["close"] and c2["close"] > c1["open"]):
        patterns.append("Bullish Engulfing")

    # Bearish Engulfing
    if (is_bearish(c2) and is_bullish(c1)
            and c2["open"] > c1["close"] and c2["close"] < c1["open"]):
        patterns.append("Bearish Engulfing")

    # Morning Star (simplified)
    if (is_bearish(c0) and body(c1) < body(c0) * 0.3 and is_bullish(c2)
            and c2["close"] > (c0["open"] + c0["close"]) / 2):
        patterns.append("Morning Star")

    # Evening Star (simplified)
    if (is_bullish(c0) and body(c1) < body(c0) * 0.3 and is_bearish(c2)
            and c2["close"] < (c0["open"] + c0["close"]) / 2):
        patterns.append("Evening Star")

    return patterns


# ── Main compute function ──────────────────────────────────────────────────────
def compute(candles: List[Dict]) -> Dict[str, Any]:
    """Compute all indicators from OHLCV candle list. Returns flat dict."""
    if not candles:
        return {}
    closes = _closes(candles)
    result: Dict[str, Any] = {}

    # Current price
    result["price"] = round(closes[-1], 6)
    result["candle_count"] = len(candles)

    # EMAs
    for p in (9, 21, 50):
        e = ema(closes, p)
        result[f"ema_{p}"] = round(e[-1], 6) if e else None

    # EMA trend
    e9  = result.get("ema_9")
    e21 = result.get("ema_21")
    e50 = result.get("ema_50")
    if e9 and e21 and e50:
        if e9 > e21 > e50:
            result["ema_trend"] = "BULLISH"
        elif e9 < e21 < e50:
            result["ema_trend"] = "BEARISH"
        else:
            result["ema_trend"] = "MIXED"
    else:
        result["ema_trend"] = "UNKNOWN"

    # RSI
    result["rsi"] = rsi(closes)

    # MACD
    m, s, h = macd(closes)
    result["macd"] = m
    result["macd_signal"] = s
    result["macd_hist"] = h
    if m is not None and s is not None:
        result["macd_cross"] = "BULLISH" if m > s else "BEARISH"
    else:
        result["macd_cross"] = "UNKNOWN"

    # Bollinger Bands
    bb_u, bb_m, bb_l, pct_b = bollinger(closes)
    result["bb_upper"] = bb_u
    result["bb_mid"]   = bb_m
    result["bb_lower"] = bb_l
    result["bb_pct_b"] = pct_b

    # ATR (volatility)
    result["atr"] = atr(candles)

    # Price vs BB
    price = closes[-1]
    if bb_u and bb_l:
        if price > bb_u:
            result["bb_position"] = "ABOVE_UPPER"
        elif price < bb_l:
            result["bb_position"] = "BELOW_LOWER"
        elif pct_b and pct_b > 70:
            result["bb_position"] = "NEAR_UPPER"
        elif pct_b and pct_b < 30:
            result["bb_position"] = "NEAR_LOWER"
        else:
            result["bb_position"] = "MIDDLE"
    else:
        result["bb_position"] = "UNKNOWN"

    # Candlestick patterns
    result["patterns"] = detect_patterns(candles)

    # Recent candle summary (last 5 opens/closes for Claude)
    result["recent_candles"] = [
        {"open": round(c["open"], 6), "high": round(c["high"], 6),
         "low": round(c["low"], 6), "close": round(c["close"], 6)}
        for c in candles[-5:]
    ]

    return result
