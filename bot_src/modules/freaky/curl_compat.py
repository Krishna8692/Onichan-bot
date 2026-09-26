"""
curl_compat.py — HTTP client with Chrome TLS fingerprinting and aiohttp fallback.

Provides ChromeSession (curl_cffi-based, with aiohttp fallback) and
CurlSession (pure aiohttp with browser-like headers and SSL settings).
"""
import logging
import asyncio
import aiohttp
import ssl
import random
from typing import Optional, Dict, Any
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

# TLS cipher suites to mimic modern Chrome
CHROME_CIPHERS = [
    "TLS_AES_128_GCM_SHA256",
    "TLS_AES_256_GCM_SHA384",
    "TLS_CHACHA20_POLY1305_SHA256",
    "ECDHE-ECDSA-AES128-GCM-SHA256",
    "ECDHE-RSA-AES128-GCM-SHA256",
    "ECDHE-ECDSA-AES256-GCM-SHA384",
    "ECDHE-RSA-AES256-GCM-SHA384",
]


class _CurlResponse:
    """Wraps a curl_cffi response to emulate an aiohttp response."""

    def __init__(self, resp):
        self._r = resp

    @property
    def status(self):
        return self._r.status_code

    @property
    def status_code(self):
        return self._r.status_code

    @property
    def url(self):
        return str(self._r.url)

    @property
    def headers(self):
        return self._r.headers

    def json(self, content_type=None):
        try:
            return self._r.json()
        except Exception:
            return {}

    def text(self):
        return self._r.text if hasattr(self._r, 'text') else str(self._r.content)

    def read(self):
        return self._r.content


class _CurlRequest:
    """Async context manager for a single curl_cffi request."""

    def __init__(self, coro):
        self._coro = coro
        self._resp = None

    async def __aenter__(self):
        resp = await self._coro
        self._resp = _CurlResponse(resp)
        return self._resp

    async def __aexit__(self, *args):
        pass


def _extract_timeout(kwargs, default=12):
    """Extract timeout from kwargs; handle aiohttp.ClientTimeout or int/float."""
    t = kwargs.pop("timeout", default)
    if hasattr(t, "total"):
        return t.total or default
    return t or default


def _clean_kwargs(kwargs):
    """Remove aiohttp-specific kwargs that curl_cffi doesn't recognize."""
    kwargs.pop("connector", None)
    return kwargs


class ChromeSession:
    """
    Drop-in replacement for aiohttp.ClientSession using curl_cffi AsyncSession
    with Chrome TLS impersonation and automatic aiohttp fallback safeguard.
    """

    def __init__(self, impersonate="chrome131", timeout=12, proxies=None, **kwargs):
        self.impersonate = impersonate
        self._default_timeout = timeout
        self.proxies = proxies
        self._session = None
        self._use_aiohttp = False
        self._aiohttp_session = None

    async def __aenter__(self):
        try:
            from curl_cffi.requests import AsyncSession
            session_kwargs = {
                "impersonate": self.impersonate,
                "timeout": self._default_timeout,
            }
            if self.proxies:
                session_kwargs["proxies"] = self.proxies
            self._session = AsyncSession(**session_kwargs)
            await self._session.__aenter__()
        except Exception as e:
            import aiohttp
            logger.warning(f"curl_cffi AsyncSession failed ({e}), falling back to aiohttp ClientSession")
            self._session = None
            self._use_aiohttp = True
            aio_kwargs = {"timeout": aiohttp.ClientTimeout(total=self._default_timeout)}
            if self.proxies and isinstance(self.proxies, dict):
                p_url = self.proxies.get("https") or self.proxies.get("http")
                if p_url:
                    aio_kwargs["proxy"] = p_url
            self._aiohttp_session = aiohttp.ClientSession(**aio_kwargs)
            await self._aiohttp_session.__aenter__()
            return self._aiohttp_session
        return self

    async def __aexit__(self, *args):
        if self._use_aiohttp and self._aiohttp_session:
            await self._aiohttp_session.__aexit__(*args)
        elif self._session is not None:
            try:
                await self._session.__aexit__(*args)
            except Exception:
                pass

    def get(self, url, **kwargs):
        if self._use_aiohttp:
            return self._aiohttp_session.get(url, **kwargs)
        timeout = _extract_timeout(kwargs, self._default_timeout)
        _clean_kwargs(kwargs)
        if self.proxies and "proxies" not in kwargs:
            kwargs["proxies"] = self.proxies
        return _CurlRequest(self._session.get(url, timeout=timeout, **kwargs))

    def post(self, url, **kwargs):
        if self._use_aiohttp:
            return self._aiohttp_session.post(url, **kwargs)
        timeout = _extract_timeout(kwargs, self._default_timeout)
        _clean_kwargs(kwargs)
        if self.proxies and "proxies" not in kwargs:
            kwargs["proxies"] = self.proxies
        return _CurlRequest(self._session.post(url, timeout=timeout, **kwargs))

def create_ssl_context() -> ssl.SSLContext:
    """Create an SSL context that mimics Chrome's TLS fingerprint."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    ctx.set_ciphers("DEFAULT")
    return ctx

class CurlSession:
    """
    High-level HTTP session wrapper with curl-like interface.
    Manages cookies, redirects, and browser headers automatically.
    """

    def __init__(self, proxy: Optional[str] = None, timeout: int = 30):
        self.proxy = proxy
        self.timeout = aiohttp.ClientTimeout(total=timeout, connect=15)
        self._session: Optional[aiohttp.ClientSession] = None
        self._connector: Optional[aiohttp.TCPConnector] = None

    async def __aenter__(self):
        self._connector = create_connector()
        self._session = aiohttp.ClientSession(
            connector=self._connector,
            cookie_jar=aiohttp.CookieJar(unsafe=True),
        )
        return self

    async def __aexit__(self, *args):
        if self._session:
            await self._session.close()
        if self._connector:
            await self._connector.close()

    async def get(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict] = None,
        allow_redirects: bool = True,
    ) -> aiohttp.ClientResponse:
        return await self._session.get(
            url,
            headers=headers,
            params=params,
            proxy=self.proxy,
            timeout=self.timeout,
            allow_redirects=allow_redirects,
        )

    async def post(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        data: Optional[Any] = None,
        json: Optional[Any] = None,
        allow_redirects: bool = True,
    ) -> aiohttp.ClientResponse:
        return await self._session.post(
            url,
            headers=headers,
            data=data,
            json=json,
            proxy=self.proxy,
            timeout=self.timeout,
            allow_redirects=allow_redirects,
        )

    async def get_text(self, url: str, headers: Optional[Dict[str, str]] = None) -> str:
        async with await self.get(url, headers=headers) as resp:
            return await resp.text(errors="ignore")

    async def post_json(self, url: str, payload: dict, headers: Optional[Dict[str, str]] = None) -> dict:
        async with await self.post(url, json=payload, headers=headers) as resp:
            try:
                return await resp.json(content_type=None)
            except Exception:
                text = await resp.text(errors="ignore")
                return {"_raw": text, "_status": resp.status}

async def simple_post(
    url: str,
    data: Optional[Any] = None,
    json_data: Optional[Any] = None,
    headers: Optional[Dict] = None,
    proxy: Optional[str] = None,
    timeout: int = 30,
) -> tuple:
    """Simple one-shot POST. Returns (status_code, text)."""
    connector = create_connector()
    async with aiohttp.ClientSession(connector=connector) as session:
        async with session.post(
            url,
            data=data,
            json=json_data,
            headers=headers,
            proxy=proxy,
            timeout=aiohttp.ClientTimeout(total=timeout),
            allow_redirects=True,
        ) as resp:
            text = await resp.text(errors="ignore")
            return resp.status, text

async def simple_get(url: str, proxy: Optional[str] = None, headers: Optional[Dict] = None, timeout: int = 30) -> str:
    """Simple one-shot GET request."""
    connector = create_connector()
    async with aiohttp.ClientSession(connector=connector) as session:
        async with session.get(
            url,
            headers=headers,
            proxy=proxy,
            timeout=aiohttp.ClientTimeout(total=timeout),
            allow_redirects=True,
        ) as resp:
            return await resp.text(errors="ignore")

def create_connector(ssl_ctx: Optional[ssl.SSLContext] = None) -> aiohttp.TCPConnector:
    """Create an aiohttp connector with browser-like settings."""
    if ssl_ctx is None:
        ssl_ctx = create_ssl_context()
    return aiohttp.TCPConnector(
        ssl=ssl_ctx,
        limit=100,
        limit_per_host=10,
        ttl_dns_cache=300,
        force_close=False,
        enable_cleanup_closed=True,
    )
