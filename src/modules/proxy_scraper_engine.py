import asyncio
import aiohttp
import time
import threading
import traceback
import ipaddress
from urllib.parse import urlparse
from datetime import datetime
from modules.database import _execute_with_retry


_BLOCKED_NETWORKS = [
    ipaddress.ip_network('127.0.0.0/8'),
    ipaddress.ip_network('10.0.0.0/8'),
    ipaddress.ip_network('172.16.0.0/12'),
    ipaddress.ip_network('192.168.0.0/16'),
    ipaddress.ip_network('169.254.0.0/16'),
    ipaddress.ip_network('::1/128'),
    ipaddress.ip_network('fc00::/7'),
    ipaddress.ip_network('fe80::/10'),
]


def _is_safe_url(url):
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ('http', 'https'):
            return False
        hostname = parsed.hostname
        if not hostname:
            return False
        if hostname in ('localhost', 'metadata.google.internal', '169.254.169.254'):
            return False
        try:
            addr = ipaddress.ip_address(hostname)
            for net in _BLOCKED_NETWORKS:
                if addr in net:
                    return False
        except ValueError:
            pass
        return True
    except Exception:
        return False


DEFAULT_SOURCES = {
    'proxyscrape_http': {
        'url': 'https://api.proxyscrape.com/v2/?request=get&protocol=http&timeout=10000&country=all&ssl=all&anonymity=all',
        'type': 'HTTP',
        'enabled': True,
    },
    'proxyscrape_socks5': {
        'url': 'https://api.proxyscrape.com/v2/?request=get&protocol=socks5&timeout=10000&country=all',
        'type': 'SOCKS5',
        'enabled': True,
    },
    'proxyscrape_socks4': {
        'url': 'https://api.proxyscrape.com/v2/?request=get&protocol=socks4&timeout=10000&country=all',
        'type': 'SOCKS4',
        'enabled': True,
    },
    'geonode_http': {
        'url': 'https://proxylist.geonode.com/api/proxy-list?limit=500&page=1&sort_by=lastChecked&sort_type=desc&protocols=http%2Chttps',
        'type': 'HTTP',
        'enabled': True,
        'json_mode': True,
    },
    'geonode_socks': {
        'url': 'https://proxylist.geonode.com/api/proxy-list?limit=500&page=1&sort_by=lastChecked&sort_type=desc&protocols=socks4%2Csocks5',
        'type': 'SOCKS5',
        'enabled': True,
        'json_mode': True,
    },
    'free_proxy_list': {
        'url': 'https://www.proxy-list.download/api/v1/get?type=http&anon=elite',
        'type': 'HTTP',
        'enabled': True,
    },
    'free_proxy_list_https': {
        'url': 'https://www.proxy-list.download/api/v1/get?type=https&anon=elite',
        'type': 'HTTP',
        'enabled': True,
    },
    'free_proxy_list_socks5': {
        'url': 'https://www.proxy-list.download/api/v1/get?type=socks5',
        'type': 'SOCKS5',
        'enabled': True,
    },
    'openproxylist_http': {
        'url': 'https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt',
        'type': 'HTTP',
        'enabled': True,
    },
    'openproxylist_socks5': {
        'url': 'https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt',
        'type': 'SOCKS5',
        'enabled': True,
    },
    'monosans_http': {
        'url': 'https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt',
        'type': 'HTTP',
        'enabled': True,
    },
    'monosans_socks5': {
        'url': 'https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks5.txt',
        'type': 'SOCKS5',
        'enabled': True,
    },
    'clarketm_http': {
        'url': 'https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt',
        'type': 'HTTP',
        'enabled': True,
    },
    'hookzof_socks5': {
        'url': 'https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt',
        'type': 'SOCKS5',
        'enabled': True,
    },
}

_scraper_running = False
_last_scrape_time = None
_scrape_stats = {'total_scraped': 0, 'total_alive': 0, 'last_run': None, 'sources_ok': 0, 'sources_fail': 0}


def _ensure_default_sources():
    existing = _execute_with_retry("SELECT name FROM scrape_sources", fetch=True) or []
    existing_names = {r['name'] for r in existing}
    for name, src in DEFAULT_SOURCES.items():
        if name not in existing_names:
            _execute_with_retry("""
                INSERT INTO scrape_sources (name, url, proxy_type, enabled, json_mode)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (name) DO NOTHING
            """, (name, src['url'], src['type'], src.get('enabled', True), src.get('json_mode', False)))


def get_scrape_sources(enabled_only=False):
    try:
        conds = []
        if enabled_only:
            conds.append("enabled = TRUE")
        where = "WHERE " + " AND ".join(conds) if conds else ""
        return _execute_with_retry(
            f"SELECT * FROM scrape_sources {where} ORDER BY name", fetch=True
        ) or []
    except Exception:
        return []


def add_scrape_source(name, url, proxy_type='HTTP', enabled=True, json_mode=False, interval_minutes=20):
    if not _is_safe_url(url):
        return None
    return _execute_with_retry("""
        INSERT INTO scrape_sources (name, url, proxy_type, enabled, json_mode, interval_minutes)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (name) DO UPDATE SET url = EXCLUDED.url, proxy_type = EXCLUDED.proxy_type,
            enabled = EXCLUDED.enabled, json_mode = EXCLUDED.json_mode, interval_minutes = EXCLUDED.interval_minutes
        RETURNING id
    """, (name, url, proxy_type.upper(), enabled, json_mode, interval_minutes), fetch_one=True)


def toggle_scrape_source(source_id, enabled):
    return _execute_with_retry(
        "UPDATE scrape_sources SET enabled = %s WHERE id = %s",
        (enabled, source_id), return_rowcount=True
    )


def delete_scrape_source(source_id):
    return _execute_with_retry(
        "DELETE FROM scrape_sources WHERE id = %s", (source_id,), return_rowcount=True
    )


def _log_scrape_history(source_name, total_scraped, total_alive, total_stored, duration_s, error=''):
    try:
        _execute_with_retry("""
            INSERT INTO scrape_history (source_name, total_scraped, total_alive, total_stored, duration_seconds, error)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (source_name, total_scraped, total_alive, total_stored, round(duration_s, 2), error[:500] if error else ''))
        _execute_with_retry("""
            UPDATE scrape_sources SET last_run = NOW(), last_count = %s, last_alive = %s
            WHERE name = %s
        """, (total_scraped, total_alive, source_name))
    except Exception:
        pass


def get_scrape_history(limit=50):
    return _execute_with_retry("""
        SELECT * FROM scrape_history ORDER BY created_at DESC LIMIT %s
    """, (limit,), fetch=True) or []


async def _fetch_from_source(session, name, source):
    proxies = []
    try:
        url = source.get('url', '')
        if not _is_safe_url(url):
            print(f"[ProxyScraper] Blocked unsafe URL for {name}: {url}")
            return proxies
        json_mode = source.get('json_mode', False)
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                return proxies

            if json_mode:
                data = await resp.json()
                json_path = source.get('json_path', '') or ''
                items = data
                if json_path:
                    for key in json_path.split('.'):
                        if isinstance(items, dict):
                            items = items.get(key, [])
                        else:
                            break
                elif isinstance(data, dict) and 'data' in data:
                    items = data['data']
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, dict):
                            ip = item.get('ip', '')
                            port = item.get('port', '')
                            if ip and port:
                                proxies.append(f"{ip}:{port}")
                        elif isinstance(item, str) and ':' in item:
                            proxies.append(item.strip())
            else:
                text = await resp.text()
                for line in text.strip().split('\n'):
                    line = line.strip()
                    if line and ':' in line:
                        proxies.append(line)
    except Exception as e:
        print(f"[ProxyScraper] Error fetching {name}: {e}")
    return proxies


async def _validate_with_checker(host, port, proxy_type):
    from modules.proxy_checker import test_proxy
    if proxy_type in ('SOCKS5', 'SOCKS4'):
        proxy_str = f"{proxy_type.lower()}://{host}:{port}"
    else:
        proxy_str = f"{host}:{port}"

    try:
        result = await test_proxy(proxy_str, timeout=10)
        if not result.get('alive'):
            return None

        classification = 'datacenter' if result.get('hosting') else 'residential'

        is_proxy = result.get('is_proxy', False)
        is_vpn = result.get('is_vpn', False)
        if is_proxy and not is_vpn:
            anonymity = 'elite'
        elif is_vpn:
            anonymity = 'anonymous'
        else:
            anonymity = 'transparent'

        return {
            'host': host, 'port': port, 'proxy_type': proxy_type,
            'alive': True,
            'speed_ms': result.get('ms', 0) or 0,
            'country': result.get('country', '') or '',
            'country_code': result.get('country_code', '') or '',
            'isp': result.get('isp', '') or '',
            'hosting': result.get('hosting', False),
            'classification': classification,
            'fraud_score': result.get('fraud_score', 0) or 0,
            'anonymity': anonymity,
        }
    except Exception:
        return None


async def _validate_batch(proxies_raw, proxy_type, concurrency=30):
    sem = asyncio.Semaphore(concurrency)
    results = []

    async def _check(host, port):
        async with sem:
            return await _validate_with_checker(host, port, proxy_type)

    tasks = []
    for raw in proxies_raw[:500]:
        parts = raw.strip().split(':')
        if len(parts) >= 2:
            host = parts[0].strip()
            try:
                port = int(parts[1].strip())
            except ValueError:
                continue
            tasks.append(_check(host, port))

    if tasks:
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)
        results = [r for r in raw_results if isinstance(r, dict)]
    return results


def _store_proxies(valid_proxies, source_name):
    stored = 0
    for p in valid_proxies:
        try:
            _execute_with_retry("""
                INSERT INTO proxy_pool (host, port, proxy_type, country, country_code, isp, speed_ms,
                    hosting, alive, last_checked, source, classification, fraud_score, anonymity)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, TRUE, NOW(), %s, %s, %s, %s)
                ON CONFLICT (host, port) DO UPDATE SET
                    alive = TRUE,
                    speed_ms = EXCLUDED.speed_ms,
                    country = EXCLUDED.country,
                    country_code = EXCLUDED.country_code,
                    isp = EXCLUDED.isp,
                    hosting = EXCLUDED.hosting,
                    last_checked = NOW(),
                    source = EXCLUDED.source,
                    classification = EXCLUDED.classification,
                    fraud_score = EXCLUDED.fraud_score,
                    anonymity = EXCLUDED.anonymity
            """, (
                p['host'], p['port'], p['proxy_type'],
                p.get('country', ''), p.get('country_code', ''),
                p.get('isp', ''), p.get('speed_ms', 0),
                p.get('hosting', False), source_name,
                p.get('classification', 'unknown'), p.get('fraud_score', 0),
                p.get('anonymity', 'unknown')
            ))
            stored += 1
        except Exception as e:
            print(f"[ProxyScraper] Store error: {e}")
    return stored


async def run_scrape_cycle():
    global _last_scrape_time, _scrape_stats
    print("[ProxyScraper] Starting scrape cycle...")

    try:
        _ensure_default_sources()
    except Exception as e:
        print(f"[ProxyScraper] Source init skipped (tables may not exist yet): {e}")

    total_scraped = 0
    total_alive = 0
    sources_ok = 0
    sources_fail = 0

    _execute_with_retry("""
        UPDATE proxy_pool SET alive = FALSE
        WHERE last_checked < NOW() - INTERVAL '2 hours'
    """)

    _execute_with_retry("""
        UPDATE proxy_pool SET classification = 'datacenter'
        WHERE classification IS NULL OR classification = '' OR classification = 'unknown'
    """)

    sources = get_scrape_sources(enabled_only=True)
    if not sources:
        sources = [
            {'name': k, 'url': v['url'], 'proxy_type': v['type'],
             'json_mode': v.get('json_mode', False), 'json_path': ''}
            for k, v in DEFAULT_SOURCES.items() if v.get('enabled', True)
        ]

    async with aiohttp.ClientSession() as session:
        for source in sources:
            if source.get('name', '').startswith('webshare') and source.get('url', '').startswith('cap:'):
                continue
            name = source.get('name', 'unknown')
            src_interval = source.get('interval_minutes', 20) or 20
            last_run = source.get('last_run')
            if last_run:
                try:
                    if isinstance(last_run, str):
                        last_run = datetime.strptime(last_run[:19], '%Y-%m-%d %H:%M:%S')
                    elapsed = (datetime.utcnow() - last_run).total_seconds() / 60
                    if elapsed < src_interval:
                        continue
                except Exception:
                    pass

            src_start = time.time()
            try:
                raw = await _fetch_from_source(session, name, source)
                scraped_count = len(raw)
                total_scraped += scraped_count
                alive_count = 0
                stored_count = 0
                if raw:
                    valid = await _validate_batch(raw, source.get('proxy_type', 'HTTP'), concurrency=20)
                    alive_count = len(valid)
                    total_alive += alive_count
                    stored_count = _store_proxies(valid, name)
                    sources_ok += 1
                    print(f"[ProxyScraper] {name}: {scraped_count} scraped, {alive_count} alive, {stored_count} stored")
                else:
                    sources_fail += 1

                dur = time.time() - src_start
                _log_scrape_history(name, scraped_count, alive_count, stored_count, dur)
            except Exception as e:
                sources_fail += 1
                dur = time.time() - src_start
                _log_scrape_history(name, 0, 0, 0, dur, str(e))
                print(f"[ProxyScraper] {name} failed: {e}")

    webshare_sources = [s for s in sources if s.get('name', '').startswith('webshare') and s.get('url', '').startswith('cap:')]
    for ws in webshare_sources:
        ws_start = time.time()
        try:
            cap_parts = ws['url'].replace('cap:', '').split(':', 1)
            cap_service = cap_parts[0] if cap_parts else 'capsolver'
            cap_key = cap_parts[1] if len(cap_parts) > 1 else cap_parts[0]
            result = run_webshare_source(cap_key=cap_key, cap_service=cap_service, count=1)
            added = result.get('added', 0)
            total_alive += added
            sources_ok += 1
            _log_scrape_history(ws['name'], added, added, added, time.time() - ws_start)
            print(f"[ProxyScraper] webshare: {added} proxies added")
        except Exception as e:
            sources_fail += 1
            _log_scrape_history(ws['name'], 0, 0, 0, time.time() - ws_start, str(e))
            print(f"[ProxyScraper] webshare failed: {e}")

    _last_scrape_time = datetime.utcnow()
    _scrape_stats = {
        'total_scraped': total_scraped,
        'total_alive': total_alive,
        'last_run': _last_scrape_time.strftime('%Y-%m-%d %H:%M UTC'),
        'sources_ok': sources_ok,
        'sources_fail': sources_fail,
    }
    print(f"[ProxyScraper] Cycle done: {total_scraped} scraped, {total_alive} alive, {sources_ok} sources OK")
    return _scrape_stats


def _scraper_loop(interval_minutes=20):
    global _scraper_running
    _scraper_running = True
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    while _scraper_running:
        try:
            loop.run_until_complete(run_scrape_cycle())
        except Exception as e:
            print(f"[ProxyScraper] Loop error: {e}")
            traceback.print_exc()

        try:
            sources = get_scrape_sources(enabled_only=True)
            intervals = [s.get('interval_minutes', 20) or 20 for s in sources]
            wait_minutes = min(intervals) if intervals else interval_minutes
        except Exception:
            wait_minutes = interval_minutes

        for _ in range(wait_minutes * 60):
            if not _scraper_running:
                break
            time.sleep(1)
    loop.close()


def start_scraper_thread(interval_minutes=20):
    global _scraper_running
    if _scraper_running:
        return False
    t = threading.Thread(target=_scraper_loop, args=(interval_minutes,), daemon=True)
    t.start()
    print(f"[ProxyScraper] Background thread started (interval: {interval_minutes}min)")
    return True


def stop_scraper():
    global _scraper_running
    _scraper_running = False


def get_scraper_stats():
    return dict(_scrape_stats)


def get_pool_stats():
    total = _execute_with_retry(
        "SELECT COUNT(*) as cnt FROM proxy_pool", fetch_one=True
    )
    alive = _execute_with_retry(
        "SELECT COUNT(*) as cnt FROM proxy_pool WHERE alive = TRUE", fetch_one=True
    )
    by_type = _execute_with_retry("""
        SELECT proxy_type, COUNT(*) as cnt FROM proxy_pool WHERE alive = TRUE GROUP BY proxy_type
    """, fetch=True) or []
    by_country = _execute_with_retry("""
        SELECT country, COUNT(*) as cnt FROM proxy_pool WHERE alive = TRUE AND country != '' GROUP BY country ORDER BY cnt DESC LIMIT 20
    """, fetch=True) or []
    by_class = _execute_with_retry("""
        SELECT classification, COUNT(*) as cnt FROM proxy_pool WHERE alive = TRUE GROUP BY classification
    """, fetch=True) or []

    return {
        'total': (total or {}).get('cnt', 0),
        'alive': (alive or {}).get('cnt', 0),
        'by_type': {r['proxy_type']: r['cnt'] for r in by_type},
        'by_country': {r['country']: r['cnt'] for r in by_country},
        'by_classification': {r['classification']: r['cnt'] for r in by_class},
        'scraper': get_scraper_stats(),
    }


def get_pool_proxies(proxy_type=None, country=None, alive_only=True, classification=None, limit=50):
    conditions = []
    params = []
    if alive_only:
        conditions.append("alive = TRUE")
    if proxy_type:
        conditions.append("proxy_type = %s")
        params.append(proxy_type.upper())
    if country:
        conditions.append("LOWER(country) LIKE %s")
        params.append(f"%{country.lower()}%")
    if classification:
        conditions.append("classification = %s")
        params.append(classification)
    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    params.append(limit)
    return _execute_with_retry(
        f"SELECT * FROM proxy_pool {where} ORDER BY speed_ms ASC, last_checked DESC LIMIT %s",
        params, fetch=True
    ) or []


def get_pool_proxy(proxy_id):
    return _execute_with_retry(
        "SELECT * FROM proxy_pool WHERE id = %s", (proxy_id,), fetch_one=True
    )


def run_webshare_source(cap_key, cap_service='capsolver', count=1):
    try:
        from modules.webshare_gen import WebshareGenerator
        gen = WebshareGenerator(cap_key=cap_key, cap_service=cap_service)
        results = gen.generate(count=count)
        proxies_added = 0
        for acct in results:
            proxy_list = acct.get('proxies', [])
            for proxy_str in proxy_list:
                parts = proxy_str.split(':')
                if len(parts) >= 2:
                    host = parts[0].strip()
                    try:
                        port = int(parts[1].strip())
                    except ValueError:
                        continue
                    username = parts[2] if len(parts) > 2 else ''
                    password = parts[3] if len(parts) > 3 else ''
                    _execute_with_retry("""
                        INSERT INTO proxy_pool (host, port, proxy_type, alive, last_checked, source,
                            classification, username, password, anonymity)
                        VALUES (%s, %s, 'HTTP', TRUE, NOW(), 'webshare', 'residential', %s, %s, 'elite')
                        ON CONFLICT (host, port) DO UPDATE SET
                            alive = TRUE, last_checked = NOW(), username = EXCLUDED.username,
                            password = EXCLUDED.password
                    """, (host, port, username, password))
                    proxies_added += 1
            _log_scrape_history('webshare', len(proxy_list), proxies_added, proxies_added, 0)
        return {'success': True, 'added': proxies_added}
    except ImportError:
        return {'error': 'webshare_gen module not available'}
    except Exception as e:
        return {'error': str(e)}
