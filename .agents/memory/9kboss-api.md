---
name: 9kboss API
description: Non-obvious constraints discovered while accessing the 9kboss.com API.
---

# 9kboss API constraints

Signed requests and an Indian proxy are both necessary. Direct requests fail at the CDN; unsigned requests that reach the application return an application-level forbidden response. The login flow also requires a CAPTCHA.

**Why:** These are independent barriers; changing only the HTTP library or adding a proxy will not fix an unsigned request. A successful HTTP status alone does not prove login succeeded.

**How to apply:** Reuse the project's current API helper and verify the account-detail response before reporting any balance. If the site changes, inspect its current browser bundle rather than guessing fields or endpoints.

Withdrawal history was not verified through a real authenticated session. Never report an empty history just because an unconfirmed endpoint failed.

**Why:** Failed requests to guessed endpoints were previously interpreted as "no withdrawals."

**How to apply:** Treat withdrawal history as unavailable until a real authenticated request confirms its endpoint and response format.
