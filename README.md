<div align="center">

# 🎀 Onichan Bot

**Multi-tool Telegram bot with OTP interception, card checking, AI tools, and a full web admin panel.**

[![Python](https://img.shields.io/badge/Python-3.11-blue?style=flat-square&logo=python)](https://python.org)
[![Telegram](https://img.shields.io/badge/Telegram-Bot-2CA5E0?style=flat-square&logo=telegram)](https://core.telegram.org/bots)
[![Twilio](https://img.shields.io/badge/Twilio-OTP%20Calls-F22F46?style=flat-square&logo=twilio)](https://twilio.com)
[![Flask](https://img.shields.io/badge/Flask-Web%20Panel-000000?style=flat-square&logo=flask)](https://flask.palletsprojects.com)

</div>

---

## ✨ Features

### 📞 OTP Call Interception
- Place live OTP calls to targets via Twilio with caller ID spoofing
- Custom voice scripts delivered via text-to-speech
- Real-time OTP capture with Accept / Decline buttons in Telegram
- Call recording and AMD (answering machine detection)
- Cloudflare tunnel for public webhook exposure

### 💳 Card Checking (20+ Gates)
| Gate | Command | Level |
|------|---------|-------|
| Stripe Auth | `/sor` `/st5` `/st12` `/str` | Premium |
| Braintree | `/bu` `/b3` `/b3n` `/bt1` `/bt3d` | Premium |
| Square | `/sq` | Free |
| PayPal | `/pp` `/ppv` | Premium |
| Authorize.net | `/auz` `/asd` `/atf` `/anh` | Premium |
| Shopify | `/sh6` `/sh8` `/sh10` `/sh13` | Premium |
| Razorpay | `/rz` `/rzp` | Premium |
| PayU | `/payu` | Premium |
| Auto Stripe Auth | `/ast` | Premium |

Mass checking supported for all gates via `/m<gate>` commands or `.txt` file upload.

### 🤖 AI Tools
- `/ask` — ChatGPT integration
- `/worm` — WormGPT (unfiltered AI)
- `/img` — AI image generation
- `/music` — AI music generation (Suno)

### 💰 Credits & Economy
- Credit balance system with transaction history (`/balance`)
- Voucher codes for distributing credits (`/voucher create`)
- Credit gifting between users (`/gift`)
- Daily claim reward (`/claim`) — free credits every 24 hours
- All gates consume credits per check

### 👑 Premium System
- Subscription tiers with expiry
- Key-based redemption (`/redeem <key>`)
- Crypto payment integration (OxaPay, TON, Coinbase)
- Escrow service for peer-to-peer deals (`/escrow`)
- Reseller infrastructure built in

### 🎰 Casino
- Blackjack, Roulette, Slots, and more
- In-bot balance for casino play

### 🌐 Proxy Management
- System proxy pool (scraped and verified automatically)
- Per-user custom proxy (`/proxy add ip:port:user:pass`)
- Proxy mode toggle: own vs system (`/proxy mode own|system`)
- Built-in proxy shop for users to purchase access

### 🛠 Utility Tools
- `/bin` — BIN lookup (bank, brand, country, card type)
- `/gen` — Card number generator from BIN
- `/fake` — Fake identity / address generator
- `/ip` — IP info and fraud score
- `/tmail` — Temporary email
- `/tpno` — Temporary phone number
- `/download` — Media downloader
- `/web` — Website analyzer
- HIBP breach watcher (background monitoring)

### 🖥 Web Admin Panel (`/admin`)
- **Dashboard** — live stats: users, premium, revenue, checks
- **Users** — list, ban/unban, view proxy mode per user
- **Premium** — grant/revoke subscriptions, generate keys
- **Payments** — transaction log and crypto payment history
- **Approved Cards** — log of all captured approved cards
- **Settings** — access control toggle, maintenance mode, global gate proxy, gate enable/disable switches, error log viewer
- **CC Shop** — upload and sell cards with custom pricing rules
- **Proxy Shop** — manage proxy plans, nodes, and scraping sources
- **Tools** — web-based checker, card generator, and cleaner
- **Auto Hitter** — mass checkout interface

---

## 🚀 Setup

### Requirements
- Python 3.11+
- PostgreSQL database
- Telegram Bot Token (from [@BotFather](https://t.me/BotFather))
- Twilio account (for OTP calls)

### Environment Variables

| Variable | Description |
|----------|-------------|
| `BOT_TOKEN` | Telegram bot token |
| `OWNER_ID` | Your Telegram user ID |
| `ADMIN_PASSWORD` | Admin panel password |
| `SESSION_SECRET` | Flask session secret |
| `TWILIO_ACCOUNT_SID` | Twilio account SID |
| `TWILIO_AUTH_TOKEN` | Twilio auth token |
| `TWILIO_PHONE_NUMBER` | Twilio caller number |
| `DATABASE_URL` | PostgreSQL connection string |
| `TON_WALLET` | TON wallet address for payments |

### Running Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Start the bot
cd src
PORT=5000 python bot.py
```

### Deploying on Replit

The project is configured for Replit VM deployment. The `artifacts/onichan-bot` artifact handles the production run via `scripts/start-bot.sh`. Health checks use the `/ping` endpoint.

---

## 📁 Project Structure

```
src/
├── bot.py              # Main bot — all command handlers (16k+ lines)
├── keep_alive.py       # Flask web server + admin panel
├── config.py           # Environment config
└── modules/
    ├── database.py     # PostgreSQL + fallback storage
    ├── credits.py      # Credit economy system
    ├── premium_plans.py
    ├── premium_keys.py
    ├── gate_checker.py
    ├── auto_hitter.py
    ├── twilio_call.py  # OTP call logic
    ├── bin_lookup.py
    ├── chatgpt.py
    ├── wormgpt.py
    ├── casino.py
    ├── escrow.py
    ├── reseller.py
    ├── proxy_checker.py
    ├── user_config.py
    ├── gate_monitor.py
    ├── hibp_watcher.py
    └── ...

scripts/
├── start-bot.sh        # Production startup script
└── start-all.sh        # Dev startup (bot + API server)

artifacts/
├── onichan-bot/        # Telegram bot artifact (port 5000)
└── api-server/         # API server artifact (port 8080)
```

---

## 🔑 Key Commands

| Command | Description | Access |
|---------|-------------|--------|
| `/start` | Start the bot | All |
| `/help` | Full command list | All |
| `/balance` | View credit balance | Approved |
| `/claim` | Daily free credits | Approved |
| `/buy` | Purchase credits/premium | All |
| `/redeem <key>` | Redeem a premium key | All |
| `/proxy add <proxy>` | Add personal proxy | Approved |
| `/broadcast <msg>` | Message all users | Owner |
| `/ban <id>` | Ban a user | Owner |
| `/genkey <days>` | Generate premium key | Owner |
| `/stats` | Bot statistics | Owner |
| `/geterror` | View recent errors | Owner |
| `/restart` | Restart bot | Owner |

---

## ⚠️ Disclaimer

This project is provided for educational and research purposes only. The authors take no responsibility for misuse. Always comply with applicable laws and terms of service.

---

<div align="center">
Made with ❤️ — Onichan Bot
</div>
