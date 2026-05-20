"""
signal_feed.py — Candle + price data for Pocket Option asset pairs.

All data from free public APIs — no user keys needed.
- Forex (major + exotic): yfinance FX tickers  e.g. EURUSD=X, USDCOP=X
- Crypto: CoinGecko OHLC or Binance public klines
- Stocks: yfinance equity tickers
"""

import asyncio
import logging
import time
from typing import Optional, List, Dict, Any, Tuple

import aiohttp

log = logging.getLogger("signal_feed")

# ── Cache ──────────────────────────────────────────────────────────────────────
_CANDLE_CACHE: Dict[str, Tuple[float, List[Dict]]] = {}
_PRICE_CACHE:  Dict[str, Tuple[float, Dict]]       = {}
_CANDLE_TTL = 30   # seconds — candles refresh every 30 s
_PRICE_TTL  = 15   # seconds — tick every 15 s

# ── Pocket Option full asset list ─────────────────────────────────────────────
# Each entry: (display_name, category, yf_ticker_or_cg_id, kind)
#   kind: "forex" | "crypto" | "stock"

OTC_CLASSIC = [
    ("AUD/CAD OTC", "AUD/CAD", "AUDCAD=X", "forex"),
    ("AUD/USD OTC", "AUD/USD", "AUDUSD=X", "forex"),
    ("AUD/CHF OTC", "AUD/CHF", "AUDCHF=X", "forex"),
    ("AUD/JPY OTC", "AUD/JPY", "AUDJPY=X", "forex"),
    ("AUD/NZD OTC", "AUD/NZD", "AUDNZD=X", "forex"),
    ("CAD/CHF OTC", "CAD/CHF", "CADCHF=X", "forex"),
    ("CAD/JPY OTC", "CAD/JPY", "CADJPY=X", "forex"),
    ("CHF/JPY OTC", "CHF/JPY", "CHFJPY=X", "forex"),
    ("EUR/AUD OTC", "EUR/AUD", "EURAUD=X", "forex"),
    ("EUR/CAD OTC", "EUR/CAD", "EURCAD=X", "forex"),
    ("EUR/CHF OTC", "EUR/CHF", "EURCHF=X", "forex"),
    ("EUR/GBP OTC", "EUR/GBP", "EURGBP=X", "forex"),
    ("EUR/JPY OTC", "EUR/JPY", "EURJPY=X", "forex"),
    ("EUR/NZD OTC", "EUR/NZD", "EURNZD=X", "forex"),
    ("EUR/USD OTC", "EUR/USD", "EURUSD=X", "forex"),
    ("GBP/AUD OTC", "GBP/AUD", "GBPAUD=X", "forex"),
    ("GBP/CAD OTC", "GBP/CAD", "GBPCAD=X", "forex"),
    ("GBP/CHF OTC", "GBP/CHF", "GBPCHF=X", "forex"),
    ("GBP/JPY OTC", "GBP/JPY", "GBPJPY=X", "forex"),
    ("GBP/NZD OTC", "GBP/NZD", "GBPNZD=X", "forex"),
    ("GBP/USD OTC", "GBP/USD", "GBPUSD=X", "forex"),
    ("MAD/USD OTC", "MAD/USD", "MADUSD=X", "forex"),
    ("NZD/CAD OTC", "NZD/CAD", "NZDCAD=X", "forex"),
    ("NZD/CHF OTC", "NZD/CHF", "NZDCHF=X", "forex"),
    ("NZD/JPY OTC", "NZD/JPY", "NZDJPY=X", "forex"),
    ("NZD/USD OTC", "NZD/USD", "NZDUSD=X", "forex"),
    ("OMR/CNY OTC", "OMR/CNY", "OMRCNY=X", "forex"),
    ("QAR/CNY OTC", "QAR/CNY", "QARCNY=X", "forex"),
    ("USD/ARS OTC", "USD/ARS", "USDARS=X", "forex"),
    ("USD/BDT OTC", "USD/BDT", "USDBDT=X", "forex"),
    ("USD/BRL OTC", "USD/BRL", "USDBRL=X", "forex"),
    ("USD/CAD OTC", "USD/CAD", "USDCAD=X", "forex"),
    ("USD/CHF OTC", "USD/CHF", "USDCHF=X", "forex"),
    ("USD/CLP OTC", "USD/CLP", "USDCLP=X", "forex"),
    ("USD/CNY OTC", "USD/CNY", "USDCNY=X", "forex"),
    ("USD/COP OTC", "USD/COP", "USDCOP=X", "forex"),
    ("USD/INR OTC", "USD/INR", "USDINR=X", "forex"),
    ("USD/JPY OTC", "USD/JPY", "USDJPY=X", "forex"),
    ("USD/MXN OTC", "USD/MXN", "USDMXN=X", "forex"),
    ("USD/MYR OTC", "USD/MYR", "USDMYR=X", "forex"),
    ("USD/PHP OTC", "USD/PHP", "USDPHP=X", "forex"),
    ("USD/RUB OTC", "USD/RUB", "USDRUB=X", "forex"),
    ("USD/SGD OTC", "USD/SGD", "USDSGD=X", "forex"),
    ("USD/TRY OTC", "USD/TRY", "USDTRY=X", "forex"),
    ("USD/ZAR OTC", "USD/ZAR", "USDZAR=X", "forex"),
]

OTC_CRYPTO = [
    ("BTC/USD OTC", "BTC/USD", "bitcoin",     "crypto"),
    ("ETH/USD OTC", "ETH/USD", "ethereum",    "crypto"),
    ("LTC/USD OTC", "LTC/USD", "litecoin",    "crypto"),
    ("XRP/USD OTC", "XRP/USD", "ripple",      "crypto"),
    ("ADA/USD OTC", "ADA/USD", "cardano",     "crypto"),
    ("SOL/USD OTC", "SOL/USD", "solana",      "crypto"),
    ("DOGE/USD OTC","DOGE/USD","dogecoin",    "crypto"),
    ("BNB/USD OTC", "BNB/USD", "binancecoin", "crypto"),
    ("AVAX/USD OTC","AVAX/USD","avalanche-2", "crypto"),
    ("DOT/USD OTC", "DOT/USD", "polkadot",    "crypto"),
]

FOREX_LIVE = [
    ("EUR/USD", "EUR/USD", "EURUSD=X", "forex"),
    ("GBP/USD", "GBP/USD", "GBPUSD=X", "forex"),
    ("USD/JPY", "USD/JPY", "USDJPY=X", "forex"),
    ("AUD/USD", "AUD/USD", "AUDUSD=X", "forex"),
    ("USD/CAD", "USD/CAD", "USDCAD=X", "forex"),
    ("USD/CHF", "USD/CHF", "USDCHF=X", "forex"),
    ("EUR/GBP", "EUR/GBP", "EURGBP=X", "forex"),
    ("EUR/JPY", "EUR/JPY", "EURJPY=X", "forex"),
    ("GBP/JPY", "GBP/JPY", "GBPJPY=X", "forex"),
    ("NZD/USD", "NZD/USD", "NZDUSD=X", "forex"),
    ("EUR/CHF", "EUR/CHF", "EURCHF=X", "forex"),
    ("AUD/JPY", "AUD/JPY", "AUDJPY=X", "forex"),
    ("CAD/JPY", "CAD/JPY", "CADJPY=X", "forex"),
    ("CHF/JPY", "CHF/JPY", "CHFJPY=X", "forex"),
]

STOCKS_OTC = [
    ("AAPL OTC",  "AAPL",  "AAPL",  "stock"),
    ("TSLA OTC",  "TSLA",  "TSLA",  "stock"),
    ("AMZN OTC",  "AMZN",  "AMZN",  "stock"),
    ("MSFT OTC",  "MSFT",  "MSFT",  "stock"),
    ("GOOGL OTC", "GOOGL", "GOOGL", "stock"),
    ("META OTC",  "META",  "META",  "stock"),
    ("NVDA OTC",  "NVDA",  "NVDA",  "stock"),
    ("NFLX OTC",  "NFLX",  "NFLX",  "stock"),
    ("BABA OTC",  "BABA",  "BABA",  "stock"),
]

# Fast name → entry lookup
_ALL_ASSETS: Dict[str, tuple] = {}
for _lst in (OTC_CLASSIC, OTC_CRYPTO, FOREX_LIVE, STOCKS_OTC):
    for entry in _lst:
        _ALL_ASSETS[entry[0]] = entry  # by display name


# ── CoinGecko candles ──────────────────────────────────────────────────────────
_CG_OHLC_DAYS = {"1m": 1, "2m": 1, "3m": 1, "5m": 1, "10m": 1, "15m": 2, "1h": 7, "4h": 14}

async def _cg_candles(coin_id: str, interval: str) -> List[Dict]:
    days = _CG_OHLC_DAYS.get(interval, 1)
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/ohlc"
    params = {"vs_currency": "usd", "days": str(days)}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status != 200:
                    return []
                raw = await r.json(content_type=None)
        candles = []
        for row in raw:
            ts, o, h, lw, c = row
            candles.append({"ts": ts / 1000, "open": o, "high": h, "low": lw, "close": c, "volume": 0})
        return candles[-50:]
    except Exception as e:
        log.warning("CG candles failed %s: %s", coin_id, e)
        return []


# ── yfinance candles (forex + stocks) ─────────────────────────────────────────
_YF_PERIOD_MAP = {"1m": ("1d", "1m"), "2m": ("1d", "2m"), "3m": ("1d", "1m"),
                  "5m": ("5d", "5m"), "10m": ("5d", "5m"), "15m": ("5d", "15m"),
                  "1h": ("7d", "1h"), "4h": ("14d", "1h")}

def _yf_candles_sync(ticker: str, interval: str) -> List[Dict]:
    try:
        import yfinance as yf
    except Exception:
        return []
    period, yf_interval = _YF_PERIOD_MAP.get(interval, ("5d", "5m"))
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period=period, interval=yf_interval, auto_adjust=False)
        if hist is None or hist.empty:
            return []
        candles = []
        for idx, row in hist.iterrows():
            candles.append({
                "ts":     idx.timestamp(),
                "open":   float(row["Open"]),
                "high":   float(row["High"]),
                "low":    float(row["Low"]),
                "close":  float(row["Close"]),
                "volume": float(row.get("Volume", 0) or 0),
            })
        return candles[-50:]
    except Exception as e:
        log.warning("yfinance candles failed %s: %s", ticker, e)
        return []


async def _yf_candles(ticker: str, interval: str) -> List[Dict]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _yf_candles_sync, ticker, interval)


def _yf_price_sync(ticker: str) -> Optional[Dict]:
    try:
        import yfinance as yf
    except Exception:
        return None
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="2d", interval="5m", auto_adjust=False)
        if hist is None or hist.empty:
            return None
        closes = hist["Close"].dropna()
        if len(closes) < 2:
            return None
        price = float(closes.iloc[-1])
        prev  = float(closes.iloc[-2])
        change_pct = ((price - prev) / prev) * 100 if prev else 0
        return {"price": price, "change_pct": change_pct}
    except Exception as e:
        log.warning("yfinance price failed %s: %s", ticker, e)
        return None


async def _yf_price(ticker: str) -> Optional[Dict]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _yf_price_sync, ticker)


async def _cg_price(coin_id: str) -> Optional[Dict]:
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {"ids": coin_id, "vs_currencies": "usd", "include_24hr_change": "true"}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status != 200:
                    return None
                d = await r.json(content_type=None)
        bucket = d.get(coin_id, {})
        price = bucket.get("usd")
        change = bucket.get("usd_24h_change")
        if price is None:
            return None
        return {"price": float(price), "change_pct": float(change) if change else 0}
    except Exception as e:
        log.warning("CG price failed %s: %s", coin_id, e)
        return None


# ── Public API ─────────────────────────────────────────────────────────────────

async def get_candles(display_name: str, interval: str = "5m") -> List[Dict]:
    """Return up to 50 OHLCV candles for the given Pocket Option display name."""
    cache_key = f"{display_name}:{interval}"
    now = time.time()
    hit = _CANDLE_CACHE.get(cache_key)
    if hit and (now - hit[0]) < _CANDLE_TTL:
        return hit[1]

    entry = _ALL_ASSETS.get(display_name)
    if not entry:
        return []
    _, _, ticker, kind = entry

    if kind == "crypto":
        candles = await _cg_candles(ticker, interval)
        if not candles:
            # Fallback: use yfinance with Binance-style ticker
            yf_ticker = ticker.upper().replace("bitcoin", "BTC").replace("ethereum", "ETH") + "-USD"
            try:
                coin_map = {"bitcoin": "BTC-USD", "ethereum": "ETH-USD", "litecoin": "LTC-USD",
                            "ripple": "XRP-USD", "cardano": "ADA-USD", "solana": "SOL-USD",
                            "dogecoin": "DOGE-USD", "binancecoin": "BNB-USD",
                            "avalanche-2": "AVAX-USD", "polkadot": "DOT-USD"}
                yf_ticker = coin_map.get(ticker, ticker.upper() + "-USD")
            except Exception:
                pass
            candles = await _yf_candles(yf_ticker, interval)
    else:
        candles = await _yf_candles(ticker, interval)

    _CANDLE_CACHE[cache_key] = (now, candles)
    return candles


async def get_price(display_name: str) -> Optional[Dict]:
    """Return {price, change_pct} for the given asset. Cached 15 s."""
    now = time.time()
    hit = _PRICE_CACHE.get(display_name)
    if hit and (now - hit[0]) < _PRICE_TTL:
        return hit[1]

    entry = _ALL_ASSETS.get(display_name)
    if not entry:
        return None
    _, _, ticker, kind = entry

    if kind == "crypto":
        data = await _cg_price(ticker)
    else:
        data = await _yf_price(ticker)

    if data:
        _PRICE_CACHE[display_name] = (now, data)
    return data
