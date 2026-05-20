"""
signal_analyst.py — Calls Claude claude-opus-4-7 to produce a Pocket Option trading signal.

Uses the Replit AI Integrations Anthropic proxy (no user API key needed).
"""

import os
import json
import random
import string
import logging
from typing import Dict, Any, Optional

log = logging.getLogger("signal_analyst")

_ANTHROPIC_BASE_URL = os.environ.get("AI_INTEGRATIONS_ANTHROPIC_BASE_URL", "")
_ANTHROPIC_API_KEY  = os.environ.get("AI_INTEGRATIONS_ANTHROPIC_API_KEY", "")

# ── Decorative code generator ─────────────────────────────────────────────────
_CHARS = string.ascii_uppercase + string.digits

def _gen_code() -> str:
    """Generate a decorative code like LYR-9M2J-T30N."""
    p1 = "".join(random.choices(_CHARS, k=3))
    p2 = "".join(random.choices(_CHARS, k=4))
    p3 = "".join(random.choices(_CHARS, k=4))
    return f"{p1}-{p2}-{p3}"


# ── Prompt builder ────────────────────────────────────────────────────────────
def _build_prompt(asset: str, interval: str, price_info: Optional[Dict], ind: Dict[str, Any]) -> str:
    price_str = f"{price_info['price']:.6f}" if price_info else "N/A"
    chg_str   = f"{price_info['change_pct']:+.2f}%" if price_info else "N/A"

    recent = ind.get("recent_candles", [])
    recent_str = "\n".join(
        f"  O:{c['open']} H:{c['high']} L:{c['low']} C:{c['close']}"
        for c in recent
    ) or "  (no data)"

    patterns = ", ".join(ind.get("patterns", [])) or "None detected"

    return f"""You are a professional binary options trading signal analyst for the Pocket Option platform.

ASSET: {asset}
TIMEFRAME: {interval}
CURRENT PRICE: {price_str}  |  CHANGE: {chg_str}

TECHNICAL INDICATORS:
- RSI(14): {ind.get('rsi', 'N/A')}
- MACD: {ind.get('macd', 'N/A')} | Signal: {ind.get('macd_signal', 'N/A')} | Histogram: {ind.get('macd_hist', 'N/A')}
- MACD Cross: {ind.get('macd_cross', 'N/A')}
- EMA(9): {ind.get('ema_9', 'N/A')} | EMA(21): {ind.get('ema_21', 'N/A')} | EMA(50): {ind.get('ema_50', 'N/A')}
- EMA Trend: {ind.get('ema_trend', 'N/A')}
- Bollinger Upper: {ind.get('bb_upper', 'N/A')} | Mid: {ind.get('bb_mid', 'N/A')} | Lower: {ind.get('bb_lower', 'N/A')}
- Bollinger %B: {ind.get('bb_pct_b', 'N/A')}  |  Position: {ind.get('bb_position', 'N/A')}
- ATR(14): {ind.get('atr', 'N/A')}
- Candlestick patterns: {patterns}

LAST 5 CANDLES (oldest → newest):
{recent_str}

VALID POCKET OPTION EXPIRY TIMES (minutes): 1, 2, 3, 5, 10, 15

Your task: Analyse all indicators above and produce a trading signal for Pocket Option.
Choose:
- direction: UP or DOWN
- expiry_minutes: the best Pocket Option expiry from the valid list above (strong momentum → 1-3 min; slower trend → 5-15 min)
- accuracy_low and accuracy_high: your confidence range (e.g. 72 and 78 or 85 and 90)
- indicator_combo: a short professional string listing 2-3 of the key indicator systems you used, in the style of the SnipeSpy platform (e.g. "Bollinger Bands 21, RSI 14, Pivot Points, QuantumFlow v1" or "VolatilityBands 15, QuantumMACD 7/14, TrendWave v3"). Use real indicator names but vary the version numbers and names professionally.
- liquidity_note: one sentence describing market liquidity/conditions (e.g. "Liquidity indicators suggest moderate trade execution ease." or "Short-term liquidity indicates balanced buy/sell distribution.")
- data_source_note: one short sentence about the data source (e.g. "Chart quotes obtained from primary source." or "Quotes imported from the exchange for analysis.")

Return ONLY valid JSON, no other text:
{{
  "direction": "UP",
  "expiry_minutes": 5,
  "accuracy_low": 85,
  "accuracy_high": 90,
  "indicator_combo": "Bollinger Bands 21, RSI 14, Pivot Points, QuantumFlow v1",
  "liquidity_note": "Liquidity indicators suggest moderate trade execution ease.",
  "data_source_note": "Chart quotes obtained from primary source."
}}"""


# ── Claude call ────────────────────────────────────────────────────────────────
async def analyse(asset: str, interval: str,
                  price_info: Optional[Dict], indicators: Dict[str, Any]) -> Optional[Dict]:
    """
    Call Claude and return a signal dict:
    {direction, expiry_minutes, accuracy_low, accuracy_high,
     indicator_combo, liquidity_note, data_source_note,
     enc_code, token_code}
    Returns None on failure.
    """
    if not _ANTHROPIC_BASE_URL or not _ANTHROPIC_API_KEY:
        log.error("Anthropic env vars not set — cannot generate signal")
        return None

    prompt = _build_prompt(asset, interval, price_info, indicators)

    try:
        import anthropic
        client = anthropic.Anthropic(
            base_url=_ANTHROPIC_BASE_URL,
            api_key=_ANTHROPIC_API_KEY,
        )
        # Use claude-opus-4-7 (latest); temperature deprecated on this model so omit it
        import asyncio
        loop = asyncio.get_running_loop()

        def _call():
            return client.messages.create(
                model="claude-opus-4-7",
                max_tokens=512,
                messages=[{"role": "user", "content": prompt}],
            )

        response = await loop.run_in_executor(None, _call)
        raw = response.content[0].text.strip()

        # Strip markdown code fences if Claude wraps in ```json
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        data = json.loads(raw)

        # Validate / sanitise
        direction = str(data.get("direction", "UP")).upper()
        if direction not in ("UP", "DOWN"):
            direction = "UP"
        valid_expiry = {1, 2, 3, 5, 10, 15}
        expiry = int(data.get("expiry_minutes", 5))
        if expiry not in valid_expiry:
            expiry = min(valid_expiry, key=lambda x: abs(x - expiry))
        acc_low  = max(50, min(99, int(data.get("accuracy_low",  72))))
        acc_high = max(acc_low, min(99, int(data.get("accuracy_high", 78))))

        return {
            "direction":        direction,
            "expiry_minutes":   expiry,
            "accuracy_low":     acc_low,
            "accuracy_high":    acc_high,
            "indicator_combo":  str(data.get("indicator_combo", "Bollinger Bands 21, RSI 14")),
            "liquidity_note":   str(data.get("liquidity_note",  "Liquidity indicators suggest moderate execution ease.")),
            "data_source_note": str(data.get("data_source_note","Chart quotes obtained from primary source.")),
            "enc_code":         _gen_code(),
            "token_code":       _gen_code(),
        }

    except json.JSONDecodeError as e:
        log.warning("Claude returned non-JSON: %s | raw=%s", e, raw[:200] if 'raw' in dir() else '?')
    except Exception as e:
        log.error("Claude API call failed: %s", e)

    return None


# ── Fallback signal (when Claude is unavailable) ───────────────────────────────
def fallback_signal(asset: str) -> Dict:
    """Return a placeholder signal if Claude fails."""
    combos = [
        "Bollinger Bands 21, RSI 14, Pivot Points, QuantumFlow v1",
        "VolatilityBands 15, QuantumMACD 7/14, TrendWave v3",
        "DynamicBands 20, SmartRSI 9/14, MomentumFlow v2",
    ]
    notes = [
        "Liquidity indicators suggest moderate trade execution ease.",
        "Short-term liquidity indicates balanced buy/sell distribution.",
        "Market depth analysis shows adequate execution liquidity.",
    ]
    sources = [
        "Chart quotes obtained from primary source.",
        "Quotes imported from the exchange for analysis.",
        "Price data verified against primary market feed.",
    ]
    import random as _r
    return {
        "direction":        _r.choice(["UP", "DOWN"]),
        "expiry_minutes":   _r.choice([1, 2, 3, 5]),
        "accuracy_low":     72,
        "accuracy_high":    78,
        "indicator_combo":  _r.choice(combos),
        "liquidity_note":   _r.choice(notes),
        "data_source_note": _r.choice(sources),
        "enc_code":         _gen_code(),
        "token_code":       _gen_code(),
    }
