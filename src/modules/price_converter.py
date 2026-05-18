"""
Price converter + live chart generator for /conv command.

Resolves a free-form symbol (crypto ticker like BTC/TON or stock ticker like AAPL)
to a price source, fetches current price + 7-day history, and renders a chart PNG.

Sources:
- Crypto: CoinGecko public API (no key needed)
- Stock:  Yahoo Finance via yfinance
"""

import asyncio
import io
import time
import logging
from typing import Optional, Dict, Any, Tuple, List

import aiohttp

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import FuncFormatter

log = logging.getLogger("price_converter")

# ----- caches -----
_COIN_LIST_CACHE: Dict[str, Any] = {"ts": 0.0, "data": None}
_COIN_LIST_TTL = 6 * 3600  # 6 hours

_PRICE_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_PRICE_TTL = 60  # 60 seconds

_CHART_CACHE: Dict[str, Tuple[float, bytes]] = {}
_CHART_TTL = 60

_FX_CACHE: Dict[str, Tuple[float, float]] = {}
_FX_TTL = 600  # 10 minutes

CG_BASE = "https://api.coingecko.com/api/v3"

# Common-symbol → coingecko-id overrides for the obvious cases where the
# CoinGecko `symbol` field collides (many obscure tokens reuse popular tickers).
COIN_ALIASES = {
    "btc": "bitcoin",
    "eth": "ethereum",
    "ton": "the-open-network",
    "sol": "solana",
    "usdt": "tether",
    "usdc": "usd-coin",
    "bnb": "binancecoin",
    "xrp": "ripple",
    "ada": "cardano",
    "doge": "dogecoin",
    "shib": "shiba-inu",
    "trx": "tron",
    "dot": "polkadot",
    "matic": "matic-network",
    "ltc": "litecoin",
    "link": "chainlink",
    "avax": "avalanche-2",
    "atom": "cosmos",
    "near": "near",
    "ftm": "fantom",
    "uni": "uniswap",
    "bch": "bitcoin-cash",
    "etc": "ethereum-classic",
    "xmr": "monero",
    "algo": "algorand",
    "xlm": "stellar",
    "icp": "internet-computer",
    "fil": "filecoin",
    "vet": "vechain",
    "pepe": "pepe",
    "wbtc": "wrapped-bitcoin",
    "op": "optimism",
    "arb": "arbitrum",
    "apt": "aptos",
    "sui": "sui",
    "inj": "injective-protocol",
    "tia": "celestia",
    "sei": "sei-network",
    "wld": "worldcoin-wld",
    "render": "render-token",
    "rndr": "render-token",
    "ondo": "ondo-finance",
    "jup": "jupiter-exchange-solana",
    "pyth": "pyth-network",
    "wif": "dogwifcoin",
    "bonk": "bonk",
    "floki": "floki",
}

FIAT_SYMBOLS = {
    "usd": "$", "eur": "€", "gbp": "£", "jpy": "¥", "cny": "¥",
    "inr": "₹", "krw": "₩", "rub": "₽", "brl": "R$", "cad": "C$",
    "aud": "A$", "chf": "₣", "try": "₺", "mxn": "$", "sgd": "S$",
    "hkd": "HK$", "nzd": "NZ$", "zar": "R", "sek": "kr", "nok": "kr",
    "uah": "₴", "pln": "zł", "thb": "฿", "idr": "Rp", "myr": "RM",
    "php": "₱", "ngn": "₦", "aed": "AED", "sar": "SAR",
}

VS_CURRENCIES = set(FIAT_SYMBOLS.keys()) | {"btc", "eth"}


def fiat_symbol(code: str) -> str:
    return FIAT_SYMBOLS.get(code.lower(), code.upper() + " ")


def _fmt_price(value: float, currency: str) -> str:
    """Format a price with sensible precision."""
    sym = fiat_symbol(currency)
    abs_v = abs(value)
    if abs_v >= 1000:
        return f"{sym}{value:,.2f}"
    if abs_v >= 1:
        return f"{sym}{value:,.4f}".rstrip("0").rstrip(".") or f"{sym}0"
    if abs_v >= 0.0001:
        return f"{sym}{value:.6f}".rstrip("0").rstrip(".")
    return f"{sym}{value:.10f}".rstrip("0").rstrip(".")


# ---------------------------------------------------------------------------
# CoinGecko helpers
# ---------------------------------------------------------------------------

async def _fetch_coin_list(session: aiohttp.ClientSession) -> List[Dict[str, str]]:
    """Cached list of all coins on CoinGecko: [{id, symbol, name}, ...]."""
    now = time.time()
    if _COIN_LIST_CACHE["data"] and (now - _COIN_LIST_CACHE["ts"]) < _COIN_LIST_TTL:
        return _COIN_LIST_CACHE["data"]
    try:
        async with session.get(f"{CG_BASE}/coins/list", timeout=aiohttp.ClientTimeout(total=15)) as r:
            if r.status == 200:
                data = await r.json(content_type=None)
                if isinstance(data, list):
                    _COIN_LIST_CACHE["data"] = data
                    _COIN_LIST_CACHE["ts"] = now
                    return data
    except Exception as e:
        log.warning("coingecko coin list fetch failed: %s", e)
    return _COIN_LIST_CACHE.get("data") or []


async def _resolve_crypto_id(session: aiohttp.ClientSession, query: str) -> Optional[Tuple[str, str, str]]:
    """Resolve a user-typed symbol to (coin_id, symbol, name)."""
    q = query.strip().lower()
    if not q:
        return None
    coins = await _fetch_coin_list(session)
    coins_by_id = {c.get("id", "").lower(): c for c in coins} if coins else {}

    if q in COIN_ALIASES:
        cid = COIN_ALIASES[q]
        c = coins_by_id.get(cid)
        if c:
            return cid, c.get("symbol", q).upper(), c.get("name", cid.title())
        return cid, q.upper(), cid.replace("-", " ").title()

    if not coins:
        return None
    # Exact id match
    if q in coins_by_id:
        c = coins_by_id[q]
        return c["id"], c.get("symbol", q).upper(), c.get("name", q.title())
    # Exact symbol match — prefer shortest name (usually most established)
    sym_matches = [c for c in coins if c.get("symbol", "").lower() == q]
    if sym_matches:
        sym_matches.sort(key=lambda c: len(c.get("name", "")))
        c = sym_matches[0]
        return c["id"], c.get("symbol", q).upper(), c.get("name", c["id"].title())
    # Exact name match
    for c in coins:
        if c.get("name", "").lower() == q:
            return c["id"], c.get("symbol", "").upper(), c.get("name", "")
    return None


async def _fetch_crypto_price(
    session: aiohttp.ClientSession, coin_id: str, vs: str,
    symbol: Optional[str] = None, name: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Current price + 24h change + 7d history for a CoinGecko coin."""
    vs = vs.lower()
    if vs not in VS_CURRENCIES:
        vs = "usd"
    # current price + 24h change
    try:
        url = f"{CG_BASE}/simple/price"
        params = {"ids": coin_id, "vs_currencies": vs, "include_24hr_change": "true", "include_market_cap": "true", "include_24hr_vol": "true"}
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as r:
            if r.status != 200:
                return None
            data = await r.json(content_type=None)
        bucket = data.get(coin_id)
        if not bucket:
            return None
        price = bucket.get(vs)
        change = bucket.get(f"{vs}_24h_change")
        market_cap = bucket.get(f"{vs}_market_cap")
        volume = bucket.get(f"{vs}_24h_vol")
        if price is None:
            return None
    except Exception as e:
        log.warning("coingecko price fetch failed: %s", e)
        return None
    # 7-day history
    history: List[Tuple[float, float]] = []
    try:
        url2 = f"{CG_BASE}/coins/{coin_id}/market_chart"
        params2 = {"vs_currency": vs, "days": "7"}
        async with session.get(url2, params=params2, timeout=aiohttp.ClientTimeout(total=20)) as r:
            if r.status == 200:
                hd = await r.json(content_type=None)
                for ts_ms, p in hd.get("prices", []):
                    history.append((ts_ms / 1000.0, float(p)))
    except Exception as e:
        log.warning("coingecko history fetch failed: %s", e)
    return {
        "kind": "crypto",
        "id": coin_id,
        "symbol": (symbol or coin_id).upper(),
        "name": name or coin_id.replace("-", " ").title(),
        "price": float(price),
        "change_24h_pct": float(change) if change is not None else None,
        "market_cap": market_cap,
        "volume_24h": volume,
        "vs": vs,
        "history": history,
    }


# ---------------------------------------------------------------------------
# Yahoo Finance (stock) helper — runs in executor since yfinance is sync
# ---------------------------------------------------------------------------

def _yf_lookup_sync(ticker: str) -> Optional[Dict[str, Any]]:
    try:
        import yfinance as yf  # type: ignore
    except Exception as e:
        log.warning("yfinance unavailable: %s", e)
        return None
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="7d", interval="1h", auto_adjust=False)
        if hist is None or hist.empty:
            hist = t.history(period="1mo", interval="1d", auto_adjust=False)
        if hist is None or hist.empty:
            return None
        closes = hist["Close"].dropna()
        if closes.empty:
            return None
        price = float(closes.iloc[-1])
        first_24h = closes.iloc[-min(24, len(closes))] if len(closes) >= 2 else closes.iloc[0]
        change_pct = ((price - float(first_24h)) / float(first_24h)) * 100.0 if first_24h else None
        history = [(ts.timestamp(), float(v)) for ts, v in closes.items()]
        currency = "USD"
        name = ticker.upper()
        try:
            info = t.fast_info  # type: ignore[attr-defined]
            cur = None
            # fast_info may behave as attribute object OR dict-like
            try:
                cur = info["currency"]  # dict-like
            except Exception:
                cur = getattr(info, "currency", None)
            if cur:
                currency = str(cur).upper()
        except Exception:
            pass
        if not currency or currency == "USD":
            try:
                meta = t.info  # type: ignore[attr-defined]
                if isinstance(meta, dict):
                    cur2 = meta.get("currency") or meta.get("financialCurrency")
                    if cur2:
                        currency = str(cur2).upper()
                    name = meta.get("shortName") or meta.get("longName") or name
            except Exception:
                pass
        return {
            "kind": "stock",
            "id": ticker.upper(),
            "symbol": ticker.upper(),
            "name": name,
            "price": price,
            "change_24h_pct": change_pct,
            "market_cap": None,
            "volume_24h": None,
            "vs": currency.lower(),
            "history": history,
        }
    except Exception as e:
        log.warning("yfinance lookup failed for %s: %s", ticker, e)
        return None


async def _fetch_stock_price(ticker: str) -> Optional[Dict[str, Any]]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _yf_lookup_sync, ticker)


async def _fetch_fx_rate(session: aiohttp.ClientSession, base: str, target: str) -> Optional[float]:
    """Get FX rate: 1 unit of `base` = X units of `target`. Cached 10 min."""
    base = base.lower()
    target = target.lower()
    if base == target:
        return 1.0
    key = f"{base}:{target}"
    now = time.time()
    hit = _FX_CACHE.get(key)
    if hit and (now - hit[0]) < _FX_TTL:
        return hit[1]
    # Primary: open.er-api.com (free, no key)
    try:
        url = f"https://open.er-api.com/v6/latest/{base.upper()}"
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
            if r.status == 200:
                d = await r.json(content_type=None)
                rate = (d.get("rates") or {}).get(target.upper())
                if rate:
                    _FX_CACHE[key] = (now, float(rate))
                    return float(rate)
    except Exception as e:
        log.warning("open.er-api FX fetch failed: %s", e)
    # Fallback: exchangerate.host
    try:
        url = "https://api.exchangerate.host/latest"
        async with session.get(url, params={"base": base.upper(), "symbols": target.upper()},
                               timeout=aiohttp.ClientTimeout(total=10)) as r:
            if r.status == 200:
                d = await r.json(content_type=None)
                rate = (d.get("rates") or {}).get(target.upper())
                if rate:
                    _FX_CACHE[key] = (now, float(rate))
                    return float(rate)
    except Exception as e:
        log.warning("exchangerate.host FX fetch failed: %s", e)
    return None


def _convert_quote_currency(data: Dict[str, Any], target: str, rate: float) -> Dict[str, Any]:
    """Return a new quote dict with price/history/market stats scaled by `rate`."""
    converted = dict(data)
    converted["price"] = float(data["price"]) * rate
    converted["history"] = [(ts, float(p) * rate) for ts, p in (data.get("history") or [])]
    for fld in ("market_cap", "volume_24h"):
        v = data.get(fld)
        if v is not None:
            try:
                converted[fld] = float(v) * rate
            except Exception:
                pass
    converted["vs"] = target.lower()
    return converted


# ---------------------------------------------------------------------------
# Chart renderer
# ---------------------------------------------------------------------------

def _render_chart_sync(data: Dict[str, Any]) -> Optional[bytes]:
    history = data.get("history") or []
    if len(history) < 2:
        return None
    import datetime as _dt
    xs = [_dt.datetime.fromtimestamp(ts) for ts, _ in history]
    ys = [v for _, v in history]
    up = (data.get("change_24h_pct") or 0) >= 0
    line_color = "#22c55e" if up else "#ef4444"
    fill_color = "#22c55e22" if up else "#ef444422"

    fig, ax = plt.subplots(figsize=(8, 4), dpi=140)
    fig.patch.set_facecolor("#0b0b13")
    ax.set_facecolor("#0b0b13")

    ax.plot(xs, ys, color=line_color, linewidth=2.2)
    ax.fill_between(xs, ys, min(ys), color=fill_color)

    # Current price marker
    ax.scatter([xs[-1]], [ys[-1]], color=line_color, s=40, zorder=5,
               edgecolor="#ffffff", linewidth=1.0)

    # Styling
    ax.tick_params(colors="#9ca3af", labelsize=9)
    for spine in ax.spines.values():
        spine.set_color("#1f2937")
    ax.grid(True, color="#1f2937", linestyle="--", linewidth=0.5, alpha=0.7)

    cur = (data.get("vs") or "usd").lower()
    sym = fiat_symbol(cur)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _p: f"{sym}{v:,.4f}".rstrip("0").rstrip(".") if v < 1 else f"{sym}{v:,.2f}"))
    span_days = (xs[-1] - xs[0]).days
    if span_days <= 2:
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    else:
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))

    title = f"{data.get('symbol','').upper()}  •  {_fmt_price(data['price'], cur)}"
    chg = data.get("change_24h_pct")
    if chg is not None:
        arrow = "▲" if chg >= 0 else "▼"
        title += f"   {arrow} {chg:+.2f}%  (24h)"
    ax.set_title(title, color="#f9fafb", fontsize=13, pad=12, loc="left", fontweight="bold")

    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()


async def render_chart(data: Dict[str, Any]) -> Optional[bytes]:
    cache_key = f"{data.get('kind')}:{data.get('id')}:{data.get('vs')}"
    now = time.time()
    hit = _CHART_CACHE.get(cache_key)
    if hit and (now - hit[0]) < _CHART_TTL:
        return hit[1]
    loop = asyncio.get_running_loop()
    img = await loop.run_in_executor(None, _render_chart_sync, data)
    if img:
        _CHART_CACHE[cache_key] = (now, img)
    return img


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def fetch_quote(symbol: str, vs: str = "usd") -> Optional[Dict[str, Any]]:
    """Resolve `symbol` (crypto first, then stock), return price + history dict.

    `vs` may be any 3-letter fiat code. Crypto path uses CoinGecko's known
    allowlist (`VS_CURRENCIES`); for unsupported targets we fetch in USD and
    convert via FX. Stock path always fetches in the ticker's native currency
    and converts when requested target differs.
    """
    vs = (vs or "usd").lower()
    cache_key = f"{symbol.lower()}:{vs}"
    now = time.time()
    hit = _PRICE_CACHE.get(cache_key)
    if hit and (now - hit[0]) < _PRICE_TTL:
        return hit[1]

    async with aiohttp.ClientSession() as session:
        resolved = await _resolve_crypto_id(session, symbol)
        if resolved:
            coin_id, sym, name = resolved
            # CoinGecko only knows a fixed vs_currencies set — for anything
            # outside it, fetch in USD and FX-convert afterwards.
            fetch_vs = vs if vs in VS_CURRENCIES else "usd"
            data = await _fetch_crypto_price(session, coin_id, fetch_vs, symbol=sym, name=name)
            if data:
                native = (data.get("vs") or "usd").lower()
                if vs != native:
                    rate = await _fetch_fx_rate(session, native, vs)
                    if rate:
                        data = _convert_quote_currency(data, vs, rate)
                _PRICE_CACHE[cache_key] = (now, data)
                return data

        # Stock fallback (yfinance) — fetch in native currency, then FX-convert.
        data = await _fetch_stock_price(symbol)
        if data:
            native = (data.get("vs") or "usd").lower()
            if vs != native:
                rate = await _fetch_fx_rate(session, native, vs)
                if rate:
                    data = _convert_quote_currency(data, vs, rate)
                # If FX failed, fall through with native currency (caption will note it).
            _PRICE_CACHE[cache_key] = (now, data)
            return data
    return None


def format_caption(amount: float, target_vs: str, data: Dict[str, Any]) -> str:
    """Build the HTML caption sent with the chart."""
    import html as _html
    vs = (data.get("vs") or "usd").lower()
    price = data["price"]
    converted = price * amount
    sym = (data.get("symbol") or "").upper()
    name = _html.escape(data.get("name") or sym)
    kind_emoji = "🪙" if data.get("kind") == "crypto" else "📈"
    chg = data.get("change_24h_pct")
    chg_str = ""
    if chg is not None:
        arrow = "🟢 ▲" if chg >= 0 else "🔴 ▼"
        chg_str = f"\n📊 <b>24h:</b> {arrow} {chg:+.2f}%"

    extra = ""
    mc = data.get("market_cap")
    if mc:
        extra += f"\n💎 <b>Market Cap:</b> {_fmt_price(float(mc), vs)}"
    vol = data.get("volume_24h")
    if vol:
        extra += f"\n💧 <b>Volume (24h):</b> {_fmt_price(float(vol), vs)}"

    # If we couldn't honour the user's requested target (FX rate fetch
    # failed) we fall back to native currency and tell them.
    if target_vs and target_vs.lower() != vs:
        note = f"\n<i>Note: FX unavailable — showing in {vs.upper()}.</i>"
    else:
        note = ""

    return (
        f"{kind_emoji} <b>{name}</b> ({sym})\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 <b>{amount:g} {sym}</b> = <b>{_fmt_price(converted, vs)}</b>\n"
        f"📍 <b>1 {sym}</b> = {_fmt_price(price, vs)}{chg_str}"
        f"{extra}{note}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>Live • powered by CoinGecko / Yahoo Finance</i>"
    )
