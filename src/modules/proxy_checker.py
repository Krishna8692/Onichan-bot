import asyncio
import aiohttp
import time
import re
import html as html_mod
from typing import Optional, Dict, List


def parse_proxy(proxy: str) -> Optional[str]:
    proxy = proxy.strip()
    if not proxy:
        return None
    if '://' in proxy:
        return proxy
    parts = proxy.split(':')
    if len(parts) == 4:
        host, port, user, passwd = parts
        return f'http://{user}:{passwd}@{host}:{port}'
    if '@' in proxy:
        auth, hostport = proxy.rsplit("@", 1)
        user, password = auth.split(":", 1)
        host, port = hostport.rsplit(":", 1)
        return f"http://{user}:{password}@{host}:{port}"
    if len(parts) == 2:
        host, port = parts
        return f'http://{host}:{port}'
    return None


def get_flag_emoji(country_code: str) -> str:
    if not country_code or len(country_code) != 2:
        return '🏳️'
    try:
        return ''.join(chr(ord(c) + 127397) for c in country_code.upper())
    except:
        return '🏳️'


async def test_proxy(proxy_str: str, timeout: int = 10) -> Dict:
    result = {
        "proxy": proxy_str, "alive": False, "ms": None, "ip": None,
        "country": None, "country_code": None, "isp": None, "type": None,
        "stripe": False, "stripe_ms": None,
        "fraud_score": None, "is_proxy": None, "is_vpn": None,
        "hosting": False,
        "error": None,
    }
    proxy_url = parse_proxy(proxy_str)
    if not proxy_url:
        result["error"] = "Invalid format"
        return result

    if proxy_url.startswith("socks5"):
        result["type"] = "SOCKS5"
    elif proxy_url.startswith("socks4"):
        result["type"] = "SOCKS4"
    else:
        result["type"] = "HTTP"

    try:
        t0 = time.perf_counter()
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as s:
            async with s.get("http://ip-api.com/json?fields=query,country,countryCode,isp,org,as,hosting", proxy=proxy_url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    result["alive"] = True
                    result["ms"] = round((time.perf_counter() - t0) * 1000)
                    result["ip"] = data.get("query", "?")
                    result["country"] = data.get("country", "?")
                    result["country_code"] = data.get("countryCode", "?")
                    result["isp"] = data.get("isp") or data.get("org") or "?"
                    result["hosting"] = data.get("hosting", False)
                    if data.get("hosting"):
                        result["type"] += " (DC)"
                    else:
                        result["type"] += " (Resi)"
                else:
                    result["error"] = f"HTTP {resp.status}"
                    return result
    except asyncio.TimeoutError:
        result["error"] = "Timeout"
        return result
    except Exception as e:
        result["error"] = str(e)[:40]
        return result

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=6)) as s:
            check_url = f"http://proxycheck.io/v2/{result['ip']}?vpn=1&risk=1&asn=1"
            async with s.get(check_url) as resp:
                if resp.status == 200:
                    fdata = await resp.json()
                    ip_data = fdata.get(result["ip"], {})
                    try:
                        result["fraud_score"] = int(ip_data.get("risk", 0))
                    except (ValueError, TypeError):
                        result["fraud_score"] = None
                    result["is_proxy"] = ip_data.get("proxy", "?")
                    result["is_vpn"] = ip_data.get("vpn", "?")
    except Exception:
        pass

    try:
        t1 = time.perf_counter()
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=8),
            connector=aiohttp.TCPConnector(ssl=False)
        ) as s:
            async with s.post(
                "https://api.stripe.com/v1/tokens",
                proxy=proxy_url,
                headers={"content-type": "application/x-www-form-urlencoded"},
                data="key=pk_test_check"
            ) as resp:
                result["stripe_ms"] = round((time.perf_counter() - t1) * 1000)
                if resp.status in (200, 400, 401, 402, 403, 404):
                    result["stripe"] = True
    except Exception:
        result["stripe"] = False
        result["stripe_ms"] = None

    return result


async def test_proxies_batch(proxies: list, concurrency: int = 10) -> list:
    sem = asyncio.Semaphore(concurrency)
    async def _run(p):
        async with sem:
            return await test_proxy(p)
    return await asyncio.gather(*[_run(p) for p in proxies])


async def check_single_proxy(proxy: str, timeout: int = 10) -> Dict:
    r = await test_proxy(proxy, timeout)
    result = {
        'proxy': proxy,
        'status': 'alive' if r['alive'] else 'dead',
        'ip': r['ip'],
        'external_ip': r['ip'],
        'country': r['country'],
        'country_code': r['country_code'],
        'isp': r['isp'],
        'type': r['type'],
        'response_time': f"{r['ms']}ms" if r['ms'] else None,
        'ms': r['ms'],
        'stripe': r['stripe'],
        'stripe_ms': r['stripe_ms'],
        'fraud_score': r['fraud_score'],
        'is_proxy': r['is_proxy'],
        'is_vpn': r['is_vpn'],
        'hosting': r['hosting'],
        'error': r['error'],
    }
    return result


async def check_proxies(proxies: List[str], timeout: int = 10, max_concurrent: int = 10) -> List[Dict]:
    semaphore = asyncio.Semaphore(max_concurrent)
    async def check_with_semaphore(proxy):
        async with semaphore:
            return await check_single_proxy(proxy, timeout)
    tasks = [check_with_semaphore(proxy) for proxy in proxies]
    return await asyncio.gather(*tasks)


async def check_ip_info(ip_to_check: str = None, proxy_str: str = None) -> Dict:
    result = {
        "ip": None, "country": None, "country_code": None,
        "isp": None, "hosting": False, "ip_type": "Unknown",
        "fraud_score": None, "is_proxy": None, "is_vpn": None,
        "stripe": False, "stripe_ms": None,
        "error": None,
    }
    try:
        proxy_url = parse_proxy(proxy_str) if proxy_str else None
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            if not ip_to_check:
                kwargs = {}
                if proxy_url:
                    kwargs["proxy"] = proxy_url
                async with s.get("https://api.ipify.org", **kwargs) as resp:
                    ip_to_check = (await resp.text()).strip()

            result["ip"] = ip_to_check

            async with s.get(f"http://ip-api.com/json/{ip_to_check}?fields=query,country,countryCode,isp,org,as,hosting") as resp:
                if resp.status == 200:
                    geo = await resp.json()
                    result["country"] = geo.get("country", "?")
                    result["country_code"] = geo.get("countryCode", "?")
                    result["isp"] = geo.get("isp") or geo.get("org") or "?"
                    result["hosting"] = geo.get("hosting", False)
                    result["ip_type"] = "Datacenter" if geo.get("hosting") else "Residential"

            async with s.get(f"http://proxycheck.io/v2/{ip_to_check}?vpn=1&risk=1&asn=1") as resp:
                if resp.status == 200:
                    fj = await resp.json()
                    fd = fj.get(ip_to_check, {})
                    try:
                        result["fraud_score"] = int(fd.get("risk", 0))
                    except (ValueError, TypeError):
                        result["fraud_score"] = None
                    result["is_proxy"] = fd.get("proxy", "?")
                    result["is_vpn"] = fd.get("vpn", "?")

            t0 = time.perf_counter()
            try:
                async with s.post(
                    "https://api.stripe.com/v1/tokens",
                    headers={"content-type": "application/x-www-form-urlencoded"},
                    data="key=pk_test_check"
                ) as resp:
                    result["stripe_ms"] = round((time.perf_counter() - t0) * 1000)
                    if resp.status in (200, 400, 401, 402, 403, 404):
                        result["stripe"] = True
            except Exception:
                pass

    except Exception as e:
        import re as _re
        err = _re.sub(r'https?://[^\s,\'\"]+', '[proxy]', str(e))
        result["error"] = err[:60]

    return result


def format_proxy_result(result: Dict) -> str:
    proxy = result['proxy']
    if result['status'] in ('live', 'alive'):
        country_flag = get_flag_emoji(result.get('country_code', ''))
        stripe_s = "✅ YES" if result.get('stripe') else "❌ NO"
        stripe_lat = f" ({result['stripe_ms']}ms)" if result.get('stripe_ms') else ""
        fs = result.get('fraud_score')
        if fs is not None:
            if fs <= 20:
                fraud_line = f"✅ {fs}/100 (Clean)"
            elif fs <= 50:
                fraud_line = f"⚠️ {fs}/100 (Medium)"
            elif fs <= 75:
                fraud_line = f"🟡 {fs}/100 (Risky)"
            else:
                fraud_line = f"🔴 {fs}/100 (High Risk)"
        else:
            fraud_line = "─"
        flags = []
        if result.get('is_proxy') == "yes":
            flags.append("Proxy")
        if result.get('is_vpn') == "yes":
            flags.append("VPN")
        flag_str = f" [{', '.join(flags)}]" if flags else ""

        msg = (
            f"<b>✅ LIVE PROXY</b>\n\n"
            f"<b>📡 Proxy:</b> <code>{proxy}</code>\n"
            f"<b>🌐 IP:</b> <code>{result.get('ip', 'N/A')}</code>\n"
            f"<b>🌍 Country:</b> {result.get('country', 'N/A')} {country_flag}\n"
            f"<b>🏢 ISP:</b> {result.get('isp', 'N/A')}\n"
            f"<b>🔧 Type:</b> {result.get('type', 'N/A')}{flag_str}\n"
            f"<b>⚡ Latency:</b> {result.get('ms', 'N/A')}ms\n"
            f"<b>🎯 Fraud:</b> {fraud_line}\n"
            f"<b>💳 Stripe:</b> {stripe_s}{stripe_lat}"
        )
    else:
        msg = (
            f"<b>❌ DEAD PROXY</b>\n\n"
            f"<b>📡 Proxy:</b> <code>{proxy}</code>\n"
            f"<b>❗ Error:</b> {result.get('error', 'Unknown error')}"
        )
    return msg


def format_mass_results(results: List[Dict]) -> str:
    live = [r for r in results if r.get('status') in ('live', 'alive')]
    dead = [r for r in results if r.get('status') not in ('live', 'alive')]
    stripe_ok = [r for r in live if r.get('stripe')]

    msg = (
        f"<b>📊 PROXY CHECK RESULTS</b>\n\n"
        f"<b>Total:</b> {len(results)}\n"
        f"<b>✅ Alive:</b> {len(live)}\n"
        f"<b>❌ Dead:</b> {len(dead)}\n"
        f"<b>💳 Stripe OK:</b> {len(stripe_ok)}/{len(live)}\n\n"
    )

    for r in live[:10]:
        country_flag = get_flag_emoji(r.get('country_code', ''))
        stripe_s = "✅" if r.get('stripe') else "❌"
        stripe_lat = f" ({r['stripe_ms']}ms)" if r.get('stripe_ms') else ""
        fs = r.get('fraud_score')
        if fs is not None:
            if fs <= 20:
                fraud_line = f"✅ {fs}/100"
            elif fs <= 50:
                fraud_line = f"⚠️ {fs}/100"
            else:
                fraud_line = f"🔴 {fs}/100"
        else:
            fraud_line = "─"
        proxy_flags = ""
        if r.get('is_proxy') == "yes":
            proxy_flags += " [Proxy]"
        if r.get('is_vpn') == "yes":
            proxy_flags += " [VPN]"
        msg += (
            f"✅ <code>{r['proxy']}</code>\n"
            f"   IP: <code>{r.get('ip', '?')}</code>\n"
            f"   {r.get('country', '?')} {country_flag} | <code>{r.get('type', '?')}</code>{proxy_flags}\n"
            f"   ISP: <code>{r.get('isp', '?')}</code>\n"
            f"   Latency: <code>{r.get('ms', '?')}ms</code> | Fraud: {fraud_line}\n"
            f"   Stripe: {stripe_s}{stripe_lat}\n\n"
        )

    if len(live) > 10:
        msg += f"<i>... and {len(live)-10} more alive</i>\n\n"

    for r in dead[:3]:
        msg += f"❌ <code>{r['proxy']}</code> — {r.get('error', 'Unknown')}\n"
    if len(dead) > 3:
        msg += f"<i>... and {len(dead)-3} more dead</i>\n"

    msg += "\n<i>Fraud data by proxycheck.io</i>"
    return msg
