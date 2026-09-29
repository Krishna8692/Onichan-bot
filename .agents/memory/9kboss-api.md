---
name: 9kboss API
description: How to authenticate and call the 9kboss.com API from the bot, including request signing, CAPTCHA flow, and chunk discovery approach.
---

# 9kboss API

## Request signing (required for all /api/* calls)
Every request needs `ST` (timezone offset string) and `STT` (an MD5 hash derived from a fixed secret, the URL path, and ST). Without correct signing, the API returns `{"message":"forbidden 106","status":9999}`. With correct signing from an unrecognized IP, it returns "CAPTCHA Code is required".

The signing logic and secret are embedded in the RPX JS bundle (chunk 6639). See `bot_src/modules/ninek_checker.py` for the implementation — do not replicate it elsewhere.

**Why:** Any future 9kboss API call (new endpoints, new commands) must reuse the `_build_headers()` / `_post_headers()` helpers in ninek_checker.py, or it will be rejected by the API.

**How to apply:** Import from `modules.ninek_checker`; never construct raw headers for 9kboss requests outside that module.

## CAPTCHA flow
1. GET `/api/auth/image_code?t=<unix_ms>` — no signing required, returns PNG image
2. POST `/api/auth/login` with `{username: email, password: password, imageCode: code}` + signed headers
3. On success (`status: 0`): auth token is in `response.headers['Auth']`
4. Token goes in `Auth: <token>` header for all subsequent authenticated requests
5. Tokens are cached in `_TOKEN_CACHE` keyed by `(user_id, email)` — never shared across Telegram users

## JS chunk discovery
- Runtime chunk map: `https://cdn.9kboss.com/static/js/runtime.83dc2897.js`
- Common/vendor chunks: at `/static/js/<id>.<hash>.js`
- RPX app-specific chunks: at `/static/rpx-32bf502dac24ce03e0fabc38a946f7c7/js/<id>.<hash>.chunk.js` (the `.chunk.js` suffix is required; `.js` returns 404)
- Key chunks found: 8157 (login UI), 6639 (request interceptor/signing), 2360/6793 (user_detail_info)

## Proxy requirement
- 9kboss.com is behind Cloudflare WAF; direct requests return 403 Forbidden
- Requires an Indian IP; `_get_proxy()` in ninek_checker.py queries the `proxy_pool` table first, then falls back to hardcoded GCP India addresses

## Known API endpoints
- Login: `POST /api/auth/login` — `{username, password, imageCode}`
- User info: `GET /api/user/user_detail_info`
- Withdrawal history: exact endpoint not yet confirmed; `_fetch_last_withdraw()` tries 7 common patterns

## Token ownership
Tokens are scoped to `(telegram_user_id, email)`. `check_with_token(user_id, email)` refuses to return a cached token to a different `user_id`. `complete_login` validates the password matches the one used in `start_captcha_flow` before reusing the session.
