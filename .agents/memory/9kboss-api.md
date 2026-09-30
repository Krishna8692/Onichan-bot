---
name: 9kboss API
description: Non-obvious constraints discovered while accessing the 9kboss.com API.
---

# 9kboss API constraints

Signed API requests are required; the login flow also requires a CAPTCHA. A previously observed CDN block on the homepage does not imply direct API endpoints are blocked: direct requests to the CAPTCHA endpoint and a dummy login request without a CAPTCHA reached the application. A successful authenticated login over direct access has not been verified.

**Why:** CDN behavior differs by path and may change. Changing only the HTTP library or a proxy will not fix an unsigned request, and a successful HTTP status alone does not prove login succeeded.

**How to apply:** Test the exact endpoint and preserve the same session/route from CAPTCHA to login. Reuse the current signature helper and verify the account-detail response before reporting any balance. If the site changes, inspect its current browser bundle rather than guessing fields or endpoints.

Withdrawal history was not verified through a real authenticated session. Never report an empty history just because an unconfirmed endpoint failed.

**Why:** Failed requests to guessed endpoints were previously interpreted as "no withdrawals."

**How to apply:** Treat withdrawal history as unavailable until a real authenticated request confirms its endpoint and response format.
