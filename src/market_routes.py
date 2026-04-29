"""
Market Routes — Flask routes for the peer-to-peer marketplace.
Registered via register_market_routes(app, ...) called from keep_alive.py.
"""
from __future__ import annotations
import os
import html as _html
from flask import request, jsonify, session, redirect, render_template_string
from functools import wraps

def _he(s) -> str:
    """HTML-escape a value for safe insertion into HTML. Call on every user-supplied field."""
    return _html.escape(str(s) if s is not None else "")

def _safe_int(val, default: int = 0) -> int:
    """Convert val to int, returning default on any error (prevents 500 on malformed input)."""
    try:
        return int(val)
    except (TypeError, ValueError):
        return default

def _safe_float(val, default: float = 0.0) -> float:
    """Convert val to float, returning default on any error."""
    try:
        return float(val)
    except (TypeError, ValueError):
        return default

# ─── registration helper ──────────────────────────────────────────────────────
def register_market_routes(app, user_required, admin_required, get_user_sidebar, USER_CSS, ADMIN_CSS):
    from modules import marketplace as mkt
    from modules.credits import get_balance
    mkt.init_marketplace_tables()
    mkt.start_background_thread()

    # ── helpers ──────────────────────────────────────────────────────────────
    def _uid():
        return session.get("user_id")

    def _uname():
        return session.get("username") or session.get("first_name") or f"user{_uid()}"

    def _stars(rating):
        r = round(rating)
        return "⭐" * r + "☆" * (5 - r)

    def _fmt_dt(dt):
        if not dt:
            return "—"
        try:
            return dt.strftime("%b %d, %Y")
        except Exception:
            return str(dt)

    # ── shared CSS ────────────────────────────────────────────────────────────
    MARKET_CSS = """
<style>
.mkt-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:16px;margin-top:16px}
.mkt-card{background:rgba(255,255,255,.06);border:1px solid rgba(255,105,180,.18);border-radius:14px;
  padding:16px;transition:transform .2s,border-color .2s;position:relative;overflow:hidden}
.mkt-card:hover{transform:translateY(-3px);border-color:rgba(255,105,180,.45)}
.mkt-card .badge{display:inline-block;font-size:.7rem;padding:2px 8px;border-radius:20px;font-weight:700;margin-bottom:8px}
.badge-fixed{background:#1e3a5f;color:#7ec8e3}
.badge-auction{background:#3a1e5f;color:#c87ef8}
.badge-cat{background:rgba(255,255,255,.1);color:#ddd}
.mkt-card h3{font-size:.95rem;font-weight:700;margin:4px 0 6px;color:#fff;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.mkt-card .price{font-size:1.1rem;font-weight:800;color:#ff69b4;margin:4px 0}
.mkt-card .meta{font-size:.75rem;color:#aaa;margin-top:6px}
.mkt-card .timeleft{font-size:.75rem;color:#ffd700;font-weight:700}
.mkt-card .bid-count{font-size:.75rem;color:#b0c4de;margin-top:2px}
.mkt-btn{display:inline-block;padding:8px 18px;border-radius:8px;font-weight:700;
  font-size:.85rem;cursor:pointer;border:none;transition:opacity .2s}
.mkt-btn-primary{background:linear-gradient(135deg,#e94560,#9b2e9b);color:#fff}
.mkt-btn-outline{background:transparent;border:1px solid rgba(255,105,180,.5);color:#ff99cc}
.mkt-btn:hover{opacity:.85}
.mkt-btn:disabled{opacity:.4;cursor:not-allowed}
.mkt-filters{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:16px}
.mkt-filters select,.mkt-filters input{background:rgba(255,255,255,.07);border:1px solid rgba(255,105,180,.2);
  color:#fff;border-radius:8px;padding:6px 12px;font-size:.85rem}
.mkt-filters select option{background:#1e0f2d}
.mkt-tag-row{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:14px}
.mkt-tag{padding:5px 14px;border-radius:20px;font-size:.8rem;font-weight:700;cursor:pointer;
  border:1px solid rgba(255,105,180,.3);background:transparent;color:#ccc;transition:all .2s}
.mkt-tag.active{background:rgba(255,105,180,.25);border-color:#ff69b4;color:#fff}
.mkt-hero{text-align:center;padding:20px 0 10px}
.mkt-hero h1{font-size:1.6rem;font-weight:800;
  background:linear-gradient(135deg,#ff69b4,#da70d6);-webkit-background-clip:text;
  -webkit-text-fill-color:transparent;margin-bottom:6px}
.mkt-hero p{font-size:.85rem;color:#bbb}
.mkt-stat-row{display:flex;flex-wrap:wrap;gap:10px;margin:12px 0}
.mkt-stat{flex:1;min-width:90px;background:rgba(255,255,255,.06);border-radius:10px;
  padding:10px 14px;text-align:center;border:1px solid rgba(255,105,180,.15)}
.mkt-stat .sv{font-size:1.3rem;font-weight:800;color:#ff69b4}
.mkt-stat .sk{font-size:.7rem;color:#aaa;margin-top:2px}
.detail-box{background:rgba(255,255,255,.05);border-radius:12px;padding:18px;
  border:1px solid rgba(255,105,180,.15);margin-bottom:14px}
.detail-box h2{font-size:1rem;font-weight:700;color:#ff99cc;margin-bottom:10px}
.mkt-table{width:100%;border-collapse:collapse;font-size:.83rem}
.mkt-table th{color:#ff99cc;font-weight:700;padding:8px 10px;border-bottom:1px solid rgba(255,105,180,.2);text-align:left}
.mkt-table td{padding:8px 10px;border-bottom:1px solid rgba(255,255,255,.05);color:#ddd;vertical-align:middle}
.mkt-form label{display:block;font-size:.82rem;color:#ccc;margin-bottom:4px;margin-top:12px}
.mkt-form input,.mkt-form select,.mkt-form textarea{
  width:100%;background:rgba(255,255,255,.07);border:1px solid rgba(255,105,180,.25);
  color:#fff;border-radius:8px;padding:8px 12px;font-size:.9rem;font-family:inherit}
.mkt-form textarea{min-height:90px;resize:vertical}
.mkt-result{padding:10px 14px;border-radius:8px;margin-top:10px;font-size:.85rem;display:none}
.mkt-result.ok{background:rgba(74,222,128,.15);border:1px solid rgba(74,222,128,.3);color:#4ade80}
.mkt-result.err{background:rgba(239,68,68,.15);border:1px solid rgba(239,68,68,.3);color:#f87171}
.stars{color:#ffd700;font-size:.9rem}
.seller-chip{display:inline-flex;align-items:center;gap:6px;background:rgba(255,255,255,.07);
  border-radius:20px;padding:4px 10px;font-size:.78rem;color:#ccc}
.bid-row{display:flex;justify-content:space-between;align-items:center;padding:6px 0;
  border-bottom:1px solid rgba(255,255,255,.06);font-size:.83rem}
.reveal-box{background:rgba(74,222,128,.08);border:1px solid rgba(74,222,128,.25);
  border-radius:10px;padding:14px;margin-top:10px}
.reveal-box pre{white-space:pre-wrap;word-break:break-all;font-size:.83rem;color:#b0ffb0;max-height:400px;overflow:auto}
</style>
"""

    # ── browse page ───────────────────────────────────────────────────────────
    @app.route("/user/market")
    @user_required
    def market_browse():
        uid = _uid()
        cat      = request.args.get("cat", "")
        ltype    = request.args.get("type", "")
        sort     = request.args.get("sort", "newest")
        q        = request.args.get("q", "").strip()
        min_price = request.args.get("min_price", "")
        max_price = request.args.get("max_price", "")
        min_rating = request.args.get("min_rating", "")
        page     = max(1, _safe_int(request.args.get("page", 1), 1))

        try:
            min_p = float(min_price) if min_price else None
            max_p = float(max_price) if max_price else None
            min_r = float(min_rating) if min_rating else None
        except ValueError:
            min_p = max_p = min_r = None

        data = mkt.list_listings(
            category=cat or None, listing_type=ltype or None,
            search=q or None, sort=sort, page=page, per_page=16,
            min_price=min_p, max_price=max_p, min_rating=min_r,
        )
        items = data["items"]
        total = data["total"]
        pages = max(1, (total + 15) // 16)

        def card_html(item):
            is_auc = item["listing_type"] == "auction"
            tl = mkt.time_left_str(item.get("auction_end_at")) if is_auc else ""
            bid_val = item.get("current_bid") or item.get("starting_bid") or item.get("price") or 0
            price_val = item.get("price") or 0
            display_price = int(bid_val) if is_auc else int(price_val)
            price_label = "Current Bid" if is_auc else "Price"
            tl_html = f'<div class="timeleft">{_he(tl)}</div>' if tl else ""
            bid_cnt_n = item["bid_count"]
            bid_cnt = (f'<div class="bid-count">{bid_cnt_n} bid{"s" if bid_cnt_n!=1 else ""}</div>'
                       if is_auc else "")
            badge_cls = "badge-auction" if is_auc else "badge-fixed"
            badge_lbl = "Auction" if is_auc else "Fixed"
            item_cat = _he(item["category"])
            item_title = _he(item["title"])
            item_seller = _he(item["seller_name"])
            return (
                f'<a href="/user/market/listing/{item["id"]}" style="text-decoration:none">'
                f'<div class="mkt-card">'
                f'<span class="badge {badge_cls}">{badge_lbl}</span> '
                f'<span class="badge badge-cat">{item_cat}</span>'
                f'<h3>{item_title}</h3>'
                f'<div class="price">{display_price:,} credits</div>'
                f'<div class="meta" style="font-size:.75rem;color:#bbb">{price_label}</div>'
                f'{tl_html}{bid_cnt}'
                f'<div class="meta">{item_seller} &nbsp;&#183;&nbsp; {item["views"]} views</div>'
                f'</div></a>'
            )

        cards_html = "".join(card_html(i) for i in items)
        if not items:
            cards_html = '<div style="text-align:center;color:#aaa;padding:40px">No listings found. <a href="/user/market/sell" style="color:#ff69b4">Be the first to sell!</a></div>'

        # Escape ALL query params that appear in HTML attributes or JS strings
        _q_he = _he(q)
        _cat_he = _he(cat)
        _ltype_he = _he(ltype)
        _sort_he = _he(sort)
        _min_price_he = _he(min_price)
        _max_price_he = _he(max_price)
        _min_rating_he = _he(min_rating)

        def pag_btn(p, label):
            active = "mkt-btn-primary" if p == page else "mkt-btn-outline"
            href = (f"?cat={_cat_he}&type={_ltype_he}&sort={_sort_he}"
                    f"&q={_q_he}&min_price={_min_price_he}"
                    f"&max_price={_max_price_he}&min_rating={_min_rating_he}&page={p}")
            return f'<a href="{href}" class="mkt-btn {active}" style="padding:5px 12px">{label}</a>'

        pag_html = ""
        if pages > 1:
            pag_btns = "".join(pag_btn(p, p) for p in range(max(1,page-2), min(pages+1, page+3)))
            prev_btn = pag_btn(page-1, "Prev") if page > 1 else ""
            next_btn = pag_btn(page+1, "Next") if page < pages else ""
            pag_html = f'<div style="display:flex;gap:6px;justify-content:center;margin-top:20px;flex-wrap:wrap">{prev_btn}{pag_btns}{next_btn}</div>'

        cat_tags = (f'<button class="mkt-tag {"active" if not cat else ""}" '
                    f'onclick="location.href=\'?type={_ltype_he}&sort={_sort_he}&q={_q_he}\'">All</button>')
        for c in mkt.CATEGORIES:
            c_he = _he(c)
            cat_tags += (f'<button class="mkt-tag {"active" if c==cat else ""}" '
                         f'onclick="location.href=\'?cat={c_he}&type={_ltype_he}&sort={_sort_he}&q={_q_he}\'">{c_he}</button>')

        sidebar = get_user_sidebar("market", "Marketplace")
        balance = get_balance(uid)
        _sel = lambda v, cur: "selected" if v == cur else ""
        return render_template_string(f"""<!DOCTYPE html><html><head>
<title>Marketplace — Onichan</title>{USER_CSS}{MARKET_CSS}</head>
<body><div class="sparkles"></div>{sidebar}
<div class="main-content">
<div class="mkt-hero">
  <h1>Marketplace</h1>
  <p>Buy &amp; sell digital products &mdash; cards, accounts, combos and more</p>
  <div style="margin-top:10px;display:flex;gap:8px;justify-content:center;flex-wrap:wrap">
    <span style="background:rgba(255,105,180,.1);border:1px solid rgba(255,105,180,.3);border-radius:20px;padding:4px 12px;font-size:.8rem">Balance: <b>{balance:,} credits</b></span>
    <a href="/user/market/sell" class="mkt-btn mkt-btn-primary">+ List a Product</a>
    <a href="/user/market/myshop" class="mkt-btn mkt-btn-outline">My Shop</a>
    <a href="/user/market/myorders" class="mkt-btn mkt-btn-outline">My Orders</a>
  </div>
</div>

<div class="mkt-tag-row">{cat_tags}</div>

<form method="GET" action="/user/market" class="mkt-filters">
  <input name="q" placeholder="Search listings..." value="{_q_he}" style="flex:1;min-width:160px">
  <select name="type">
    <option value="" {_sel("", ltype)}>All Types</option>
    <option value="fixed" {_sel("fixed", ltype)}>Fixed Price</option>
    <option value="auction" {_sel("auction", ltype)}>Auction</option>
  </select>
  <input name="min_price" type="number" min="0" placeholder="Min price" value="{_min_price_he}" style="width:90px">
  <input name="max_price" type="number" min="0" placeholder="Max price" value="{_max_price_he}" style="width:90px">
  <select name="min_rating">
    <option value="" {_sel("", min_rating)}>Any Rating</option>
    <option value="4" {_sel("4", min_rating)}>4+ stars</option>
    <option value="3" {_sel("3", min_rating)}>3+ stars</option>
  </select>
  <select name="sort">
    <option value="newest" {_sel("newest", sort)}>Newest</option>
    <option value="price_asc" {_sel("price_asc", sort)}>Price ↑</option>
    <option value="price_desc" {_sel("price_desc", sort)}>Price ↓</option>
    <option value="popular" {_sel("popular", sort)}>Popular</option>
  </select>
  <input type="hidden" name="cat" value="{_he(cat)}">
  <button type="submit" class="mkt-btn mkt-btn-primary">Search</button>
</form>

<div style="font-size:.8rem;color:#aaa;margin-bottom:8px">{total:,} listing{"s" if total!=1 else ""} found</div>
<div class="mkt-grid">{cards_html}</div>
{pag_html}
</div></body></html>""")

    # ── listing detail ────────────────────────────────────────────────────────
    @app.route("/user/market/listing/<int:listing_id>")
    @user_required
    def market_listing(listing_id):
        uid = _uid()
        listing = mkt.get_listing(listing_id, increment_view=True)
        if not listing:
            return redirect("/user/market")

        is_auc = listing["listing_type"] == "auction"
        is_mine = listing["seller_id"] == uid
        is_active = listing["status"] == "active"
        rating, review_count = mkt.get_seller_rating(listing["seller_id"])
        reviews = mkt.get_seller_reviews(listing["seller_id"], limit=5)
        bids = mkt.get_listing_bids(listing_id, limit=10) if is_auc else []
        balance = get_balance(uid)

        # check if user already purchased this listing
        def _check_purchase(conn):
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT download_token FROM market_purchases
                    WHERE listing_id=%s AND buyer_id=%s AND status IN ('pending','confirmed')
                    LIMIT 1
                """, (listing_id, uid))
                row = cur.fetchone()
                return row[0] if row else None
        from modules.database import _execute_with_retry as _db
        existing_token = _db(_check_purchase)

        bid_val = float(listing.get("current_bid") or listing.get("starting_bid") or 0)
        price_val = float(listing.get("price") or 0)
        tl = mkt.time_left_str(listing.get("auction_end_at")) if is_auc else ""
        stars_html = _stars(rating) if rating else "No ratings yet"

        rev_html = ""
        for rv in reviews:
            rv_comment = _he(rv['comment']) if rv['comment'] else '<em>No comment</em>'
            rev_html += (
                f'<div style="padding:8px 0;border-bottom:1px solid rgba(255,255,255,.06)">'
                f'<span class="stars">{_stars(rv["rating"])}</span>'
                f'<span style="color:#aaa;font-size:.78rem;margin-left:8px">{_fmt_dt(rv["created_at"])}</span>'
                f'<div style="font-size:.83rem;color:#ddd;margin-top:3px">{rv_comment}</div>'
                f'</div>'
            )

        bid_rows = ""
        for b in bids:
            bid_rows += (
                f'<div class="bid-row">'
                f'<span style="color:#fff">{int(b["amount"]):,} credits</span>'
                f'<span style="color:#aaa;font-size:.75rem">{_he(b["bidder_name"])} &middot; {_fmt_dt(b["created_at"])}</span>'
                f'</div>'
            )

        # Action section
        if not is_active:
            status_label = {"sold":"Sold","cancelled":"Cancelled","ended":"Ended"}.get(listing["status"],"Inactive")
            action_html = f'<div style="text-align:center;padding:20px;color:#aaa">{status_label} &mdash; This listing is no longer active.</div>'
        elif is_mine:
            action_html = '<div style="color:#aaa;font-size:.85rem;padding:10px">This is your listing.</div>'
        elif existing_token:
            _tok_safe = _he(existing_token)
            action_html = (
                f'<div class="reveal-box" id="reveal-area">'
                f'<div style="font-weight:700;color:#4ade80;margin-bottom:8px">You own this product</div>'
                f'<button class="mkt-btn mkt-btn-primary" onclick="revealProduct(\'{_tok_safe}\')">Reveal Product</button>'
                f'<div id="reveal-content" style="margin-top:10px"></div>'
                f'</div>'
            )
        elif is_auc:
            min_bid = int(bid_val) + 1
            _tl_safe = _he(tl)
            action_html = (
                f'<div class="detail-box mkt-form">'
                f'<h2>Place a Bid</h2>'
                f'<div style="font-size:.85rem;color:#ccc;margin-bottom:10px">'
                f'Current highest: <b style="color:#ff69b4">{int(bid_val):,} credits</b>'
                f' &nbsp;&middot;&nbsp; Time: <b style="color:#ffd700">{_tl_safe}</b>'
                f'</div>'
                f'<label>Your Bid (min {min_bid:,} credits) &mdash; Balance: {balance:,}</label>'
                f'<div style="display:flex;gap:8px;margin-top:6px">'
                f'<input type="number" id="bid-amount" min="{min_bid}" value="{min_bid}" style="flex:1">'
                f'<button class="mkt-btn mkt-btn-primary" onclick="placeBid({listing_id})">Place Bid</button>'
                f'</div>'
                f'<div class="mkt-result" id="bid-result"></div>'
                f'</div>'
            )
        else:
            price_int = int(price_val)
            action_html = (
                f'<div class="detail-box">'
                f'<h2>Buy Now</h2>'
                f'<div style="font-size:.85rem;color:#ccc;margin-bottom:12px">'
                f'Price: <b style="color:#ff69b4;font-size:1.1rem">{price_int:,} credits</b>'
                f' &nbsp;&middot;&nbsp; Your balance: <b>{balance:,}</b>'
                f'</div>'
                f'<button class="mkt-btn mkt-btn-primary" style="width:100%" onclick="buyNow({listing_id},{price_int})">'
                f'Buy Now &mdash; {price_int:,} credits'
                f'</button>'
                f'<div class="mkt-result" id="buy-result"></div>'
                f'</div>'
            )

        cancel_html = ""
        if is_mine and is_active:
            cancel_html = f"""<div style="margin-top:10px">
<button class="mkt-btn mkt-btn-outline" onclick="cancelListing({listing_id})" style="font-size:.8rem">Cancel Listing</button>
<div class="mkt-result" id="cancel-result"></div></div>"""

        bid_history_html = ""
        if is_auc:
            _bid_body = bid_rows or '<div style="color:#aaa;font-size:.83rem">No bids yet — be the first!</div>'
            bid_history_html = '<div class="detail-box"><h2>Bid History (' + str(listing['bid_count']) + ')</h2>' + _bid_body + '</div>'

        _desc_raw = listing['description']
        _desc = _he(_desc_raw) if _desc_raw else '<em>No description provided.</em>'
        _rev_body = rev_html or '<div style="color:#aaa;font-size:.83rem">No reviews yet.</div>'
        _badge_cls = "badge-auction" if is_auc else "badge-fixed"
        _badge_label = "Auction" if is_auc else "Fixed Price"
        _views_line = str(listing['views']) + " views &middot; Listed " + _fmt_dt(listing['created_at'])
        _title_he = _he(listing['title'])
        _seller_he = _he(listing['seller_name'])
        _cat_he = _he(listing['category'])

        sidebar = get_user_sidebar("market", listing["title"])
        return render_template_string(f"""<!DOCTYPE html><html><head>
<title>{_title_he} &mdash; Marketplace</title>{USER_CSS}{MARKET_CSS}</head>
<body><div class="sparkles"></div>{sidebar}
<div class="main-content">
<div style="margin-bottom:10px"><a href="/user/market" style="color:#ff69b4;font-size:.85rem">&#8592; Back to Marketplace</a></div>

<div class="detail-box">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:8px">
    <div>
      <span class="badge {_badge_cls}" style="margin-right:6px">{_badge_label}</span>
      <span class="badge badge-cat">{_cat_he}</span>
    </div>
    <span style="font-size:.78rem;color:#aaa">{_views_line}</span>
  </div>
  <h2 style="font-size:1.2rem;font-weight:800;margin:10px 0 6px;color:#fff">{_title_he}</h2>
  <div class="seller-chip">&#128100; {_seller_he} &nbsp;<span class="stars" style="font-size:.8rem">{stars_html}</span><span style="color:#aaa">({review_count})</span></div>
  <div style="margin-top:12px;font-size:.88rem;color:#ccc;line-height:1.6">{_desc}</div>
</div>

{action_html}
{cancel_html}
{bid_history_html}

<div class="detail-box">
  <h2>&#11088; Seller Reviews ({review_count})</h2>
  {_rev_body}
</div>
</div>

<script>
function showResult(id, msg, ok) {{
  var el = document.getElementById(id);
  if(!el) return;
  el.style.display = 'block';
  el.textContent = msg;
  el.className = 'mkt-result ' + (ok ? 'ok' : 'err');
}}

function buyNow(id, price) {{
  if(!confirm('Buy this listing for ' + price.toLocaleString() + ' credits?')) return;
  fetch('/user/market/api/buy', {{method:'POST',headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{listing_id:id}})}})
  .then(r=>r.json()).then(d=>{{
    if(d.ok) {{
      showResult('buy-result', '✅ Purchased! Revealing product...', true);
      setTimeout(()=>revealProduct(d.download_token), 800);
    }} else showResult('buy-result', '❌ ' + d.error, false);
  }}).catch(()=>showResult('buy-result', '❌ Request failed', false));
}}

function placeBid(id) {{
  var amount = parseInt(document.getElementById('bid-amount').value);
  if(!amount || amount <= 0) return;
  if(!confirm('Place a bid of ' + amount.toLocaleString() + ' credits?')) return;
  fetch('/user/market/api/bid', {{method:'POST',headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{listing_id:id, amount:amount}})}})
  .then(r=>r.json()).then(d=>{{
    if(d.ok) {{ showResult('bid-result','✅ Bid placed! Your credits are held until outbid or auction ends.',true); }}
    else showResult('bid-result','❌ ' + d.error, false);
  }}).catch(()=>showResult('bid-result','❌ Request failed',false));
}}

function revealProduct(token) {{
  fetch('/user/market/api/reveal', {{method:'POST',headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{token:token}})}})
  .then(r=>r.json()).then(d=>{{
    if(d.ok) {{
      var area = document.getElementById('reveal-content') || document.querySelector('.reveal-box');
      if(d.product_type === 'text') {{
        var pre = document.createElement('pre');
        pre.textContent = d.product_content;
        area.innerHTML = '<div class="reveal-box"><div style="font-weight:700;color:#4ade80;margin-bottom:8px">&#128230; Product Content</div></div>';
        area.querySelector('.reveal-box').appendChild(pre);
      }} else {{
        area.innerHTML = '<div class="reveal-box"><div style="font-weight:700;color:#4ade80;margin-bottom:8px">&#128193; File Download</div><a href="/user/market/download/' + token + '" class="mkt-btn mkt-btn-primary" download>&#11015; Download File</a></div>';
      }}
    }} else alert('Error: ' + d.error);
  }});
}}

function cancelListing(id) {{
  if(!confirm('Cancel this listing? Bids will be refunded.')) return;
  fetch('/user/market/api/cancel', {{method:'POST',headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{listing_id:id}})}})
  .then(r=>r.json()).then(d=>{{
    if(d.ok){{showResult('cancel-result','✅ Listing cancelled',true);setTimeout(()=>location.reload(),1200);}}
    else showResult('cancel-result','❌ '+d.error,false);
  }});
}}
</script>
</body></html>""")

    # ── sell / create listing ─────────────────────────────────────────────────
    @app.route("/user/market/sell", methods=["GET", "POST"])
    @user_required
    def market_sell():
        uid = _uid()
        uname = _uname()
        balance = get_balance(uid)
        error = ""

        if request.method == "POST":
            title        = request.form.get("title", "").strip()
            category     = request.form.get("category", "Other")
            description  = request.form.get("description", "").strip()
            listing_type = request.form.get("listing_type", "fixed")
            price_str    = request.form.get("price", "0")
            sbid_str     = request.form.get("starting_bid", "0")
            product_type = request.form.get("product_type", "text")
            content      = request.form.get("product_content", "").strip()
            auction_hrs  = request.form.get("auction_hours", "24")
            file_path    = None

            # file upload
            f = request.files.get("product_file")
            if f and f.filename:
                import os, uuid
                upload_dir = os.path.join(os.path.dirname(__file__), "static", "market_uploads")
                os.makedirs(upload_dir, exist_ok=True)
                ext = os.path.splitext(f.filename)[1][:10]
                fname = f"{uuid.uuid4().hex}{ext}"
                fpath = os.path.join(upload_dir, fname)
                f.save(fpath)
                file_path = f"market_uploads/{fname}"
                product_type = "file"

            if not title:
                error = "Title is required"
            elif not content and not file_path:
                error = "Product content or file is required"
            else:
                try:
                    price = float(price_str) if listing_type == "fixed" else 0
                    sbid  = float(sbid_str)  if listing_type == "auction" else None
                    ahrs  = int(auction_hrs) if listing_type == "auction" else None
                except ValueError:
                    error = "Invalid price value"

            if not error:
                res = mkt.create_listing(
                    seller_id=uid, seller_name=uname, title=title,
                    category=category, description=description,
                    listing_type=listing_type, price=price,
                    product_type=product_type,
                    product_content=content if product_type == "text" else None,
                    file_path=file_path,
                    starting_bid=sbid, auction_hours=ahrs,
                )
                if res["ok"]:
                    return redirect(f"/user/market/listing/{res['listing_id']}")
                error = res.get("error", "Failed to create listing")

        sidebar = get_user_sidebar("market", "Sell a Product")
        cat_opts = "".join(f'<option value="{c}">{c}</option>' for c in mkt.CATEGORIES)
        return render_template_string(f"""<!DOCTYPE html><html><head>
<title>Sell — Onichan Marketplace</title>{USER_CSS}{MARKET_CSS}</head>
<body><div class="sparkles"></div>{sidebar}
<div class="main-content">
<div style="margin-bottom:10px"><a href="/user/market" style="color:#ff69b4;font-size:.85rem">← Back to Marketplace</a></div>
<div class="detail-box mkt-form">
  <h2 style="font-size:1.1rem;font-weight:800;color:#ff99cc;margin-bottom:4px">📦 Create a New Listing</h2>
  <div style="font-size:.8rem;color:#aaa;margin-bottom:14px">Balance: <b>{balance:,} credits</b></div>
  {"<div class='mkt-result err' style='display:block;margin-bottom:10px'>" + error + "</div>" if error else ""}
  <form method="POST" enctype="multipart/form-data">
    <label>Listing Type</label>
    <div style="display:flex;gap:10px;margin-top:6px" id="type-selector">
      <label style="cursor:pointer;display:flex;align-items:center;gap:5px">
        <input type="radio" name="listing_type" value="fixed" id="t-fixed" checked onchange="toggleType()"> 🏷 Fixed Price
      </label>
      <label style="cursor:pointer;display:flex;align-items:center;gap:5px">
        <input type="radio" name="listing_type" value="auction" id="t-auction" onchange="toggleType()"> 🔨 Auction
      </label>
    </div>

    <label>Title *</label>
    <input name="title" maxlength="120" placeholder="e.g. Fresh US Visa Classic Cards x10" required>

    <label>Category</label>
    <select name="category">{cat_opts}</select>

    <label>Description</label>
    <textarea name="description" placeholder="Describe your product (validity, quantity, format, etc.)"></textarea>

    <div id="price-section">
      <label>Price (credits) *</label>
      <input type="number" name="price" id="price-input" min="1" value="100" required>
    </div>
    <div id="auction-section" style="display:none">
      <label>Starting Bid (credits) *</label>
      <input type="number" name="starting_bid" id="sbid-input" min="1" value="50">
      <label>Auction Duration</label>
      <select name="auction_hours">
        <option value="6">6 hours</option>
        <option value="12">12 hours</option>
        <option value="24" selected>24 hours</option>
        <option value="48">48 hours</option>
        <option value="72">72 hours</option>
      </select>
    </div>

    <label>Product Type</label>
    <div style="display:flex;gap:10px;margin-top:6px">
      <label style="cursor:pointer;display:flex;align-items:center;gap:5px">
        <input type="radio" name="product_type" value="text" checked onchange="toggleProductType()"> 📝 Text / Data
      </label>
      <label style="cursor:pointer;display:flex;align-items:center;gap:5px">
        <input type="radio" name="product_type" value="file" onchange="toggleProductType()"> 📁 File Upload
      </label>
    </div>

    <div id="text-section">
      <label>Product Content * (shown to buyer after purchase)</label>
      <textarea name="product_content" id="product-content" placeholder="Paste cards, credentials, combo list etc." style="min-height:140px;font-family:monospace"></textarea>
    </div>
    <div id="file-section" style="display:none">
      <label>Upload File * (.txt, .zip, .csv etc.)</label>
      <input type="file" name="product_file" id="product-file" accept=".txt,.zip,.csv,.json,.xml,.docx,.pdf">
    </div>

    <div style="margin-top:18px">
      <button type="submit" class="mkt-btn mkt-btn-primary" style="width:100%;padding:12px">
        🚀 Publish Listing
      </button>
    </div>
  </form>
</div>
</div>
<script>
function toggleType() {{
  var auc = document.getElementById('t-auction').checked;
  document.getElementById('price-section').style.display = auc ? 'none' : 'block';
  document.getElementById('auction-section').style.display = auc ? 'block' : 'none';
  document.getElementById('price-input').required = !auc;
  document.getElementById('sbid-input').required = auc;
}}
function toggleProductType() {{
  var isFile = document.querySelector('[name=product_type]:checked').value === 'file';
  document.getElementById('text-section').style.display = isFile ? 'none' : 'block';
  document.getElementById('file-section').style.display = isFile ? 'block' : 'none';
  document.getElementById('product-content').required = !isFile;
  document.getElementById('product-file').required = isFile;
}}
</script>
</body></html>""")

    # ── my shop (seller dashboard) ────────────────────────────────────────────
    @app.route("/user/market/myshop")
    @user_required
    def market_myshop():
        uid = _uid()
        stats = mkt.get_seller_stats(uid)
        rating, review_count = mkt.get_seller_rating(uid)
        listings = mkt.list_listings(seller_id=uid, status="active", per_page=50)
        all_listings = mkt.list_listings(seller_id=uid, status="sold", per_page=10)

        lc = stats.get("listing_counts", {})
        active_count  = lc.get("active", 0)
        sold_count    = lc.get("sold", 0) + lc.get("ended", 0)

        rows = ""
        for item in listings["items"]:
            is_auc = item["listing_type"] == "auction"
            tl = _he(mkt.time_left_str(item.get("auction_end_at"))) if is_auc else "&mdash;"
            display = int(item.get("current_bid") or item.get("price") or 0)
            badge_cls = "badge-auction" if is_auc else "badge-fixed"
            badge_lbl = "Auction" if is_auc else "Fixed"
            bid_cell = str(item['bid_count']) + " bids" if is_auc else "&mdash;"
            iid = item['id']
            rows += (
                f'<tr>'
                f'<td><a href="/user/market/listing/{iid}" style="color:#ff99cc">{_he(item["title"])}</a></td>'
                f'<td><span class="badge {badge_cls}" style="font-size:.7rem">{badge_lbl}</span></td>'
                f'<td>{_he(item["category"])}</td>'
                f'<td>{display:,} cr</td>'
                f'<td>{bid_cell}</td>'
                f'<td style="color:#ffd700">{tl}</td>'
                f'<td>{item["views"]}</td>'
                f'<td><button class="mkt-btn mkt-btn-outline" style="padding:3px 10px;font-size:.75rem" onclick="cancelListing({iid})">Cancel</button></td>'
                f'</tr>'
            )

        sold_rows = ""
        for item in all_listings["items"]:
            iid = item['id']
            sold_rows += (
                f'<tr>'
                f'<td><a href="/user/market/listing/{iid}" style="color:#aaa">{_he(item["title"])}</a></td>'
                f'<td>{_he(item["category"])}</td>'
                f'<td>{int(item.get("price") or item.get("current_bid") or 0):,} cr</td>'
                f'<td>{item["views"]}</td>'
                f'</tr>'
            )

        sidebar = get_user_sidebar("market", "My Shop")
        balance = get_balance(uid)
        stars_html = _stars(rating) if rating else "—"

        if listings['items']:
            _active_listings_html = ('<div style="overflow-x:auto"><table class="mkt-table">'
                '<thead><tr><th>Title</th><th>Type</th><th>Category</th><th>Price</th>'
                '<th>Bids</th><th>Time Left</th><th>Views</th><th></th></tr></thead>'
                '<tbody>' + rows + '</tbody></table></div>')
        else:
            _active_listings_html = ("<div style='color:#aaa;font-size:.85rem'>No active listings. "
                "<a href='/user/market/sell' style='color:#ff69b4'>Create one!</a></div>")

        if all_listings['items']:
            _sold_section_html = ('<div class="detail-box"><h2 style="margin-bottom:10px">Recently Sold</h2>'
                '<div style="overflow-x:auto"><table class="mkt-table">'
                '<thead><tr><th>Title</th><th>Category</th><th>Amount</th><th>Views</th></tr></thead>'
                '<tbody>' + sold_rows + '</tbody></table></div></div>')
        else:
            _sold_section_html = ""

        _total_earned = int(stats.get('total_earned', 0))
        _pending_payout = int(stats.get('pending_payout', 0))
        _active_total = listings['total']

        # earnings chart (last 6 months)
        monthly = mkt.get_monthly_earnings(uid, months=6)
        _chart_html = ""
        if monthly:
            max_val = max((m["credits"] for m in monthly), default=1) or 1
            bar_w = 100 // len(monthly)
            bars = ""
            labels = ""
            for m in monthly:
                pct = max(4, int(m["credits"] / max_val * 100))
                short_mo = m["month"][5:]  # MM
                bars += (
                    f'<div style="display:flex;flex-direction:column;align-items:center;gap:4px;flex:1;min-width:0">'
                    f'<div style="font-size:.68rem;color:#ff99cc">{m["credits"]:,}</div>'
                    f'<div style="background:linear-gradient(#ff69b4,#c94fb5);border-radius:4px 4px 0 0;'
                    f'width:70%;height:{pct}px;transition:height .3s"></div>'
                    f'<div style="font-size:.68rem;color:#aaa">{short_mo}</div>'
                    f'</div>'
                )
            _chart_html = (
                '<div class="detail-box" style="margin-top:14px">'
                '<h2 style="margin-bottom:12px">Earnings Chart (Last 6 Months)</h2>'
                '<div style="display:flex;align-items:flex-end;gap:4px;height:120px;padding:8px 4px 0">'
                + bars +
                '</div></div>'
            )

        return render_template_string(f"""<!DOCTYPE html><html><head>
<title>My Shop — Marketplace</title>{USER_CSS}{MARKET_CSS}</head>
<body><div class="sparkles"></div>{sidebar}
<div class="main-content">
<div style="margin-bottom:10px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px">
  <a href="/user/market" style="color:#ff69b4;font-size:.85rem">&#8592; Marketplace</a>
  <a href="/user/market/sell" class="mkt-btn mkt-btn-primary" style="font-size:.82rem">+ New Listing</a>
</div>

<div style="font-size:1.1rem;font-weight:800;color:#ff99cc;margin-bottom:12px">My Shop</div>

<div class="mkt-stat-row">
  <div class="mkt-stat"><div class="sv">{active_count}</div><div class="sk">Active Listings</div></div>
  <div class="mkt-stat"><div class="sv">{sold_count}</div><div class="sk">Total Sales</div></div>
  <div class="mkt-stat"><div class="sv">{_total_earned:,}</div><div class="sk">Credits Earned</div></div>
  <div class="mkt-stat"><div class="sv">{_pending_payout:,}</div><div class="sk">Pending Payout</div></div>
  <div class="mkt-stat"><div class="sv">{stars_html}</div><div class="sk">Rating ({review_count})</div></div>
  <div class="mkt-stat"><div class="sv">{balance:,}</div><div class="sk">Wallet</div></div>
</div>

<div class="detail-box" style="margin-top:14px">
  <h2 style="margin-bottom:10px">Active Listings ({_active_total})</h2>
  {_active_listings_html}
</div>

{_chart_html}
{_sold_section_html}
</div>
<script>
function cancelListing(id) {{
  if(!confirm('Cancel this listing? Bids will be refunded.')) return;
  fetch('/user/market/api/cancel',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{listing_id:id}})}})
  .then(r=>r.json()).then(d=>{{if(d.ok)location.reload(); else alert('Error: '+d.error);}});
}}
</script>
</body></html>""")

    # ── my orders (buyer) ─────────────────────────────────────────────────────
    @app.route("/user/market/myorders")
    @user_required
    def market_myorders():
        uid = _uid()
        page = max(1, _safe_int(request.args.get("page", 1), 1))
        data = mkt.get_buyer_orders(uid, page=page)
        items = data["items"]

        rows = ""
        for item in items:
            iid = item["id"]
            ilid = item["listing_id"]
            ititle = _he(item["listing_title"])
            iamount = int(item["amount"])
            iseller = _he(item.get("seller_name") or "")
            idate = _fmt_dt(item["created_at"])
            istatus = item["status"]
            status_badge = {
                "pending":   '<span style="color:#ffd700">Pending</span>',
                "confirmed": '<span style="color:#4ade80">Confirmed</span>',
                "disputed":  '<span style="color:#f87171">Disputed</span>',
                "refunded":  '<span style="color:#7ec8e3">Refunded</span>',
            }.get(istatus, f'<span style="color:#aaa">{_he(istatus)}</span>')
            reviewed = item.get("reviewed")
            review_btn = ""
            if istatus == "confirmed" and not reviewed:
                review_btn = f'<button class="mkt-btn mkt-btn-outline" style="padding:3px 10px;font-size:.73rem" onclick="openReview({iid})">Review</button>'

            dispute_btn = ""
            if istatus == "pending":
                dispute_btn = f'<button class="mkt-btn" style="padding:3px 10px;font-size:.73rem;background:#e94560;color:#fff;border:none;border-radius:6px;cursor:pointer" onclick="openDispute({iid})">Dispute</button>'

            dispute_reason = _he(item.get("dispute_reason") or "")
            dispute_note = f'<div style="color:#f87171;font-size:.75rem;margin-top:4px">Dispute: {dispute_reason}</div>' if istatus == "disputed" and dispute_reason else ""

            token = item.get("download_token") or ""
            if token:
                reveal_btn = f'<button class="mkt-btn mkt-btn-primary" style="padding:3px 10px;font-size:.73rem" onclick="revealInline(\'{token}\',{iid})">Reveal</button>'
            else:
                reveal_btn = "—"
            rows += f"""<tr id="order-{iid}">
<td><a href="/user/market/listing/{ilid}" style="color:#ff99cc">{ititle}</a></td>
<td>{iseller}</td>
<td>{iamount:,} cr</td>
<td>{status_badge}{dispute_note}</td>
<td>{idate}</td>
<td style="white-space:nowrap">{reveal_btn} {review_btn} {dispute_btn}</td>
</tr>
<tr id="reveal-row-{item['id']}" style="display:none">
  <td colspan="6"><div class="reveal-box" id="reveal-box-{item['id']}"></div></td>
</tr>"""

        sidebar = get_user_sidebar("market", "My Orders")
        total = data["total"]

        if items:
            _orders_html = ('<div style="overflow-x:auto"><table class="mkt-table">'
                '<thead><tr><th>Product</th><th>Seller</th><th>Amount</th>'
                '<th>Status</th><th>Date</th><th>Actions</th></tr></thead>'
                '<tbody>' + rows + '</tbody></table></div>')
        else:
            _orders_html = ("<div style='color:#aaa;padding:30px;text-align:center'>No orders yet. "
                "<a href='/user/market' style='color:#ff69b4'>Browse the marketplace!</a></div>")

        return render_template_string(f"""<!DOCTYPE html><html><head>
<title>My Orders — Marketplace</title>{USER_CSS}{MARKET_CSS}</head>
<body><div class="sparkles"></div>{sidebar}
<div class="main-content">
<div style="margin-bottom:12px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px">
  <a href="/user/market" style="color:#ff69b4;font-size:.85rem">&#8592; Marketplace</a>
</div>
<div style="font-size:1.1rem;font-weight:800;color:#ff99cc;margin-bottom:12px">My Orders ({total})</div>

{_orders_html}

<!-- review modal -->
<div id="review-modal" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.7);z-index:1000;align-items:center;justify-content:center">
  <div style="background:#1e0f2d;border:1px solid rgba(255,105,180,.3);border-radius:14px;padding:20px;width:90%;max-width:400px">
    <h3 style="color:#ff99cc;margin-bottom:12px">⭐ Leave a Review</h3>
    <input type="hidden" id="review-pid">
    <div class="mkt-form">
      <label>Rating</label>
      <select id="review-rating"><option value="5">⭐⭐⭐⭐⭐ 5 - Excellent</option><option value="4">⭐⭐⭐⭐ 4 - Good</option><option value="3">⭐⭐⭐ 3 - Okay</option><option value="2">⭐⭐ 2 - Poor</option><option value="1">⭐ 1 - Bad</option></select>
      <label>Comment (optional)</label>
      <textarea id="review-comment" placeholder="Share your experience..."></textarea>
    </div>
    <div style="display:flex;gap:8px;margin-top:14px">
      <button class="mkt-btn mkt-btn-primary" style="flex:1" onclick="submitReview()">Submit</button>
      <button class="mkt-btn mkt-btn-outline" onclick="document.getElementById('review-modal').style.display='none'">Cancel</button>
    </div>
    <div class="mkt-result" id="review-result"></div>
  </div>
</div>

<!-- dispute modal -->
<div id="dispute-modal" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.7);z-index:1000;align-items:center;justify-content:center">
  <div style="background:#1e0f2d;border:1px solid rgba(248,113,113,.4);border-radius:14px;padding:20px;width:90%;max-width:420px">
    <h3 style="color:#f87171;margin-bottom:8px">&#9888;&#65039; Open a Dispute</h3>
    <p style="color:#ccc;font-size:.85rem;margin-bottom:12px">Funds will be held until an admin reviews and resolves the dispute. Only open a dispute if you have a genuine issue with the purchase.</p>
    <input type="hidden" id="dispute-pid">
    <div class="mkt-form">
      <label>Reason (required)</label>
      <textarea id="dispute-reason" rows="4" placeholder="Describe the issue clearly..." style="min-height:80px"></textarea>
    </div>
    <div style="display:flex;gap:8px;margin-top:14px">
      <button class="mkt-btn" style="flex:1;background:#e94560;color:#fff;border:none;border-radius:8px;padding:8px;cursor:pointer;font-weight:700" onclick="submitDispute()">Submit Dispute</button>
      <button class="mkt-btn mkt-btn-outline" onclick="document.getElementById('dispute-modal').style.display='none'">Cancel</button>
    </div>
    <div class="mkt-result" id="dispute-result"></div>
  </div>
</div>
</div>
<script>
function revealInline(token, pid) {{
  var row = document.getElementById('reveal-row-'+pid);
  var box = document.getElementById('reveal-box-'+pid);
  if(row.style.display !== 'none') {{ row.style.display='none'; return; }}
  fetch('/user/market/api/reveal', {{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{token:token}})}})
  .then(r=>r.json()).then(d=>{{
    if(d.ok) {{
      if(d.product_type==='text') {{
        box.innerHTML='<div style="font-weight:700;color:#4ade80;margin-bottom:8px">&#128230; Product Content</div>';
        var pre=document.createElement('pre'); pre.textContent=d.product_content; box.appendChild(pre);
      }} else {{
        box.innerHTML='<div style="font-weight:700;color:#4ade80;margin-bottom:8px">&#128193; File</div><a href="/user/market/download/'+token+'" class="mkt-btn mkt-btn-primary" download>&#11015; Download</a>';
      }}
      row.style.display='';
    }} else alert('Error: '+d.error);
  }});
}}
function openReview(pid) {{
  document.getElementById('review-pid').value = pid;
  document.getElementById('review-modal').style.display = 'flex';
}}
function submitReview() {{
  var pid = document.getElementById('review-pid').value;
  var rating = document.getElementById('review-rating').value;
  var comment = document.getElementById('review-comment').value;
  fetch('/user/market/api/review', {{method:'POST',headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{purchase_id:parseInt(pid),rating:parseInt(rating),comment:comment}})}})
  .then(r=>r.json()).then(d=>{{
    var el = document.getElementById('review-result');
    el.style.display='block';
    el.textContent = d.ok ? '✅ Review submitted!' : '❌ '+d.error;
    el.className = 'mkt-result '+(d.ok?'ok':'err');
    if(d.ok) setTimeout(()=>location.reload(), 1200);
  }});
}}
function openDispute(pid) {{
  document.getElementById('dispute-pid').value = pid;
  document.getElementById('dispute-reason').value = '';
  document.getElementById('dispute-result').style.display = 'none';
  document.getElementById('dispute-modal').style.display = 'flex';
}}
function submitDispute() {{
  var pid = document.getElementById('dispute-pid').value;
  var reason = document.getElementById('dispute-reason').value.trim();
  if(!reason) {{ alert('Please describe the issue.'); return; }}
  fetch('/user/market/api/dispute', {{method:'POST',headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{purchase_id:parseInt(pid),reason:reason}})}})
  .then(r=>r.json()).then(d=>{{
    var el = document.getElementById('dispute-result');
    el.style.display='block';
    el.textContent = d.ok ? '✅ Dispute submitted. An admin will review it.' : '❌ '+d.error;
    el.className = 'mkt-result '+(d.ok?'ok':'err');
    if(d.ok) setTimeout(()=>location.reload(), 1800);
  }});
}}
</script>
</body></html>""")

    # ── download ──────────────────────────────────────────────────────────────
    @app.route("/user/market/download/<token>")
    @user_required
    def market_download(token):
        uid = _uid()
        result = mkt.reveal_product(token, uid)
        if not result["ok"]:
            return jsonify({"error": result["error"]}), 403
        if result["product_type"] != "file" or not result.get("file_path"):
            return jsonify({"error": "No file for this product"}), 404
        import os
        from flask import send_from_directory
        upload_dir = os.path.join(os.path.dirname(__file__), "static")
        rel = result["file_path"]
        full = os.path.join(upload_dir, rel)
        if not os.path.exists(full):
            return jsonify({"error": "File not found"}), 404
        return send_from_directory(upload_dir, rel, as_attachment=True)

    # ── API: buy ──────────────────────────────────────────────────────────────
    @app.route("/user/market/api/buy", methods=["POST"])
    @user_required
    def market_api_buy():
        uid = _uid()
        data = request.get_json(silent=True) or {}
        lid = _safe_int(data.get("listing_id", 0))
        if not lid:
            return jsonify({"ok": False, "error": "Missing listing_id"})
        res = mkt.purchase_fixed(lid, uid)
        return jsonify(res)

    # ── API: bid ──────────────────────────────────────────────────────────────
    @app.route("/user/market/api/bid", methods=["POST"])
    @user_required
    def market_api_bid():
        uid = _uid()
        uname = _uname()
        data = request.get_json(silent=True) or {}
        lid = _safe_int(data.get("listing_id", 0))
        amount = _safe_float(data.get("amount", 0))
        if not lid or amount <= 0:
            return jsonify({"ok": False, "error": "Invalid parameters"})
        res = mkt.place_bid(lid, uid, uname, amount)
        return jsonify(res)

    # ── API: reveal ───────────────────────────────────────────────────────────
    @app.route("/user/market/api/reveal", methods=["POST"])
    @user_required
    def market_api_reveal():
        uid = _uid()
        data = request.get_json(silent=True) or {}
        token = data.get("token", "").strip()
        if not token:
            return jsonify({"ok": False, "error": "Missing token"})
        res = mkt.reveal_product(token, uid)
        if not res["ok"]:
            return jsonify(res)
        # Only return content for text; file returns file_path info
        out = {"ok": True, "product_type": res["product_type"]}
        if res["product_type"] == "text":
            out["product_content"] = res.get("product_content") or ""
        return jsonify(out)

    # ── API: cancel ───────────────────────────────────────────────────────────
    @app.route("/user/market/api/cancel", methods=["POST"])
    @user_required
    def market_api_cancel():
        uid = _uid()
        data = request.get_json(silent=True) or {}
        lid = _safe_int(data.get("listing_id", 0))
        if not lid:
            return jsonify({"ok": False, "error": "Missing listing_id"})
        res = mkt.cancel_listing(lid, uid)
        return jsonify(res)

    # ── API: review ───────────────────────────────────────────────────────────
    @app.route("/user/market/api/review", methods=["POST"])
    @user_required
    def market_api_review():
        uid = _uid()
        data = request.get_json(silent=True) or {}
        res = mkt.submit_review(
            purchase_id=_safe_int(data.get("purchase_id", 0)),
            reviewer_id=uid,
            rating=_safe_int(data.get("rating", 0)),
            comment=str(data.get("comment", "")).strip()[:400],
        )
        return jsonify(res)

    # ── API: dispute ──────────────────────────────────────────────────────────
    @app.route("/user/market/api/dispute", methods=["POST"])
    @user_required
    def market_api_dispute():
        uid = _uid()
        data = request.get_json(silent=True) or {}
        try:
            pid = int(data.get("purchase_id", 0))
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "Invalid purchase_id"})
        reason = str(data.get("reason", "")).strip()[:1000]
        if not pid:
            return jsonify({"ok": False, "error": "Missing purchase_id"})
        res = mkt.open_dispute(pid, uid, reason)
        return jsonify(res)

    # ── admin market ──────────────────────────────────────────────────────────
    @app.route("/admin/market", methods=["GET", "POST"])
    @admin_required
    def admin_market():
        msg = ""
        if request.method == "POST":
            action = request.form.get("action")
            if action == "set_commission":
                rate = _safe_float(request.form.get("commission_rate", ""), -1.0)
                if rate < 0:
                    msg = "Invalid rate"
                else:
                    rate = max(0.0, min(50.0, rate))
                    mkt.set_commission_rate(rate)
                    msg = "Commission rate updated to " + str(rate) + "%"
            elif action == "remove":
                lid = _safe_int(request.form.get("listing_id", 0))
                if lid:
                    res = mkt.admin_remove_listing(lid)
                    msg = "Listing removed" if res["ok"] else res.get("error", "Error")
            elif action == "reinstate":
                lid = _safe_int(request.form.get("listing_id", 0))
                if lid:
                    res = mkt.admin_reinstate_listing(lid)
                    msg = "Listing reinstated" if res["ok"] else res.get("error", "Error")
            elif action == "dispute_release":
                pid = _safe_int(request.form.get("purchase_id", 0))
                if pid:
                    res = mkt.admin_resolve_dispute_release(pid)
                    msg = "Dispute resolved — funds released to seller." if res["ok"] else res.get("error", "Error")
            elif action == "dispute_refund":
                pid = _safe_int(request.form.get("purchase_id", 0))
                if pid:
                    res = mkt.admin_resolve_dispute_refund(pid)
                    msg = "Dispute resolved — buyer refunded." if res["ok"] else res.get("error", "Error")

        search = request.args.get("q", "")
        sf = request.args.get("status", "")
        page = max(1, _safe_int(request.args.get("page", 1), 1))
        data = mkt.admin_list_listings(search=search or None,
                                        status_filter=sf or None,
                                        page=page, per_page=25)
        active_auctions = mkt.get_active_auctions()
        disputed_purchases = mkt.get_disputed_purchases()
        stats = mkt.get_admin_market_stats()
        commission = mkt.get_commission_rate()

        lc = stats.get("listing_counts", {})
        rows = ""
        for item in data["items"]:
            is_auc = item["listing_type"] == "auction"
            display = int(item.get("current_bid") or item.get("price") or 0)
            sc = {"active":"color:#4ade80","sold":"color:#7ec8e3","cancelled":"color:#f87171","ended":"color:#aaa"}.get(item["status"],"")
            badge_cls = "badge-auction" if is_auc else "badge-fixed"
            badge_lbl = "Auc" if is_auc else "Fix"
            bid_cell = str(item['bid_count']) if is_auc else "&mdash;"
            iid = item["id"]
            rows += (
                f'<tr>'
                f'<td>{iid}</td>'
                f'<td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{_he(item["title"])}</td>'
                f'<td>{_he(item["seller_name"])}</td>'
                f'<td><span class="badge {badge_cls}" style="font-size:.7rem">{badge_lbl}</span> {_he(item["category"])}</td>'
                f'<td>{display:,}</td>'
                f'<td>{bid_cell}</td>'
                f'<td style="{sc}">{_he(item["status"])}</td>'
                f'<td>{item["views"]}</td>'
                f'<td style="white-space:nowrap">'
                f'<form method="POST" style="display:inline" onsubmit="return confirm(\'Remove listing #{iid}?\')">'
                f'<input type="hidden" name="action" value="remove">'
                f'<input type="hidden" name="listing_id" value="{iid}">'
                f'<button type="submit" style="background:#e94560;color:#fff;border:none;border-radius:6px;padding:3px 8px;cursor:pointer;font-size:.73rem">Remove</button>'
                f'</form>'
                + (
                    f' <form method="POST" style="display:inline">'
                    f'<input type="hidden" name="action" value="reinstate">'
                    f'<input type="hidden" name="listing_id" value="{iid}">'
                    f'<button type="submit" style="background:#4ade80;color:#000;border:none;border-radius:6px;padding:3px 8px;cursor:pointer;font-size:.73rem">Reinstate</button>'
                    f'</form>'
                    if item["status"] in ("cancelled", "ended") else ""
                )
                + f'</td></tr>'
            )

        # active auctions sub-panel
        auc_rows = ""
        for a in active_auctions:
            tl = mkt.time_left_str(a.get("auction_end_at"))
            is_expired = a.get("auction_end_at") and mkt._to_utc(a["auction_end_at"]) < mkt._now()
            tl_color = "color:#f87171" if is_expired else "color:#ffd700"
            auc_rows += (
                f'<tr>'
                f'<td>{a["id"]}</td>'
                f'<td><a href="/user/market/listing/{a["id"]}" style="color:#ff99cc" target="_blank">{_he(a["title"])}</a></td>'
                f'<td>{_he(a["seller_name"])}</td>'
                f'<td>{int(a.get("current_bid") or a.get("starting_bid") or 0):,}</td>'
                f'<td>{a["bid_count"]}</td>'
                f'<td style="{tl_color}">{_he(tl)}</td>'
                f'<td style="white-space:nowrap">'
                f'<form method="POST" style="display:inline" onsubmit="return confirm(\'Remove auction {a["id"]}?\')">'
                f'<input type="hidden" name="action" value="remove">'
                f'<input type="hidden" name="listing_id" value="{a["id"]}">'
                f'<button type="submit" style="background:#e94560;color:#fff;border:none;border-radius:6px;padding:3px 8px;cursor:pointer;font-size:.73rem">Remove</button>'
                f'</form>'
                f'</td></tr>'
            )

        _auc_panel = ""
        if active_auctions:
            _auc_panel = (
                '<div style="background:rgba(255,140,0,.08);border:1px solid rgba(255,140,0,.2);border-radius:10px;padding:14px;margin-bottom:18px">'
                '<h2 style="font-size:.95rem;color:#ffd700;margin-bottom:10px">&#128295; Active Auctions (' + str(len(active_auctions)) + ')</h2>'
                '<div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse;font-size:.8rem">'
                '<thead><tr style="color:#ffd700;border-bottom:1px solid rgba(255,215,0,.2)">'
                '<th style="padding:6px;text-align:left">ID</th><th>Title</th><th>Seller</th>'
                '<th>Bid</th><th>Bids</th><th>Time Left</th><th></th></tr></thead>'
                '<tbody>' + auc_rows + '</tbody></table></div></div>'
            )

        # disputed purchases panel
        disp_rows = ""
        for d in disputed_purchases:
            ddt = _fmt_dt(d.get("disputed_at"))
            disp_rows += (
                f'<tr>'
                f'<td style="padding:6px">{d["id"]}</td>'
                f'<td style="max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{_he(d["listing_title"])}</td>'
                f'<td>{d["buyer_id"]}</td>'
                f'<td>{d["seller_id"]}</td>'
                f'<td>{int(d["amount"]):,}</td>'
                f'<td style="max-width:200px;color:#fca5a5;font-size:.76rem;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{_he(d.get("dispute_reason") or "")}</td>'
                f'<td>{ddt}</td>'
                f'<td style="white-space:nowrap">'
                f'<form method="POST" style="display:inline" onsubmit="return confirm(\'Release funds to seller for purchase #{d["id"]}?\')">'
                f'<input type="hidden" name="action" value="dispute_release">'
                f'<input type="hidden" name="purchase_id" value="{d["id"]}">'
                f'<button type="submit" style="background:#4ade80;color:#000;border:none;border-radius:6px;padding:3px 8px;cursor:pointer;font-size:.72rem;margin-right:4px">Release&#x2192;Seller</button>'
                f'</form>'
                f'<form method="POST" style="display:inline" onsubmit="return confirm(\'Refund buyer for purchase #{d["id"]}?\')">'
                f'<input type="hidden" name="action" value="dispute_refund">'
                f'<input type="hidden" name="purchase_id" value="{d["id"]}">'
                f'<button type="submit" style="background:#e94560;color:#fff;border:none;border-radius:6px;padding:3px 8px;cursor:pointer;font-size:.72rem">Refund&#x2192;Buyer</button>'
                f'</form>'
                f'</td></tr>'
            )
        _disp_panel = ""
        if disputed_purchases:
            _disp_panel = (
                '<div style="background:rgba(248,113,113,.08);border:1px solid rgba(248,113,113,.3);border-radius:10px;padding:14px;margin-bottom:18px">'
                '<h2 style="font-size:.95rem;color:#f87171;margin-bottom:10px">&#9878; Open Disputes (' + str(len(disputed_purchases)) + ')</h2>'
                '<div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse;font-size:.8rem">'
                '<thead><tr style="color:#f87171;border-bottom:1px solid rgba(248,113,113,.2)">'
                '<th style="padding:6px;text-align:left">ID</th><th>Product</th><th>Buyer</th>'
                '<th>Seller</th><th>Amount</th><th>Reason</th><th>Filed</th><th>Action</th></tr></thead>'
                '<tbody>' + disp_rows + '</tbody></table></div></div>'
            )

        total = data["total"]
        pages = max(1, (total + 24) // 25)
        pag_html = ""
        _sq = _he(search)
        _ssf = _he(sf)
        if pages > 1:
            pag_html = "<div style='margin-top:12px;display:flex;gap:6px;flex-wrap:wrap'>"
            for p in range(max(1,page-2), min(pages+1,page+3)):
                active_style = "background:#e94560;color:#fff;" if p==page else "background:rgba(255,255,255,.07);color:#ccc;"
                pag_html += f'<a href="?q={_sq}&status={_ssf}&page={p}" style="{active_style}padding:4px 10px;border-radius:6px;text-decoration:none;font-size:.82rem">{p}</a>'
            pag_html += "</div>"

        status_opts = "".join(f'<option value="{s}" {"selected" if s==sf else ""}>{s.title()}</option>' for s in ["","active","sold","cancelled","ended"])

        _msg_html = ""
        if msg:
            _msg_html = '<div style="background:rgba(74,222,128,.15);border:1px solid rgba(74,222,128,.3);border-radius:8px;padding:8px 14px;margin-bottom:14px;color:#4ade80;font-size:.85rem">' + _he(msg) + '</div>'

        return render_template_string(f"""<!DOCTYPE html><html><head>
<title>Market Admin &mdash; Onichan</title>{ADMIN_CSS}</head>
<body>
<div style="max-width:1100px;margin:30px auto;padding:20px">
<h1 style="font-size:1.3rem;font-weight:800;color:#e94560;margin-bottom:18px">&#128717; Marketplace Admin</h1>
{_msg_html}

<div style="display:flex;flex-wrap:wrap;gap:10px;margin-bottom:18px">
  <div style="background:rgba(255,255,255,.06);border-radius:10px;padding:12px 18px;min-width:110px;text-align:center">
    <div style="font-size:1.3rem;font-weight:800;color:#e94560">{stats.get('total_sales',0):,}</div>
    <div style="font-size:.72rem;color:#aaa">Total Sales</div>
  </div>
  <div style="background:rgba(255,255,255,.06);border-radius:10px;padding:12px 18px;min-width:110px;text-align:center">
    <div style="font-size:1.3rem;font-weight:800;color:#e94560">{int(stats.get('total_volume',0)):,}</div>
    <div style="font-size:.72rem;color:#aaa">Volume (credits)</div>
  </div>
  <div style="background:rgba(255,255,255,.06);border-radius:10px;padding:12px 18px;min-width:110px;text-align:center">
    <div style="font-size:1.3rem;font-weight:800;color:#e94560">{int(stats.get('total_commission',0)):,}</div>
    <div style="font-size:.72rem;color:#aaa">Commission Earned</div>
  </div>
  <div style="background:rgba(255,255,255,.06);border-radius:10px;padding:12px 18px;min-width:110px;text-align:center">
    <div style="font-size:1.3rem;font-weight:800;color:#e94560">{lc.get('active',0)}</div>
    <div style="font-size:.72rem;color:#aaa">Active Listings</div>
  </div>
  <div style="background:rgba(255,255,255,.06);border-radius:10px;padding:12px 18px;min-width:110px;text-align:center">
    <div style="font-size:1.3rem;font-weight:800;color:#e94560">{commission}%</div>
    <div style="font-size:.72rem;color:#aaa">Commission Rate</div>
  </div>
</div>

{_auc_panel}
{_disp_panel}

<div style="display:flex;gap:14px;flex-wrap:wrap;margin-bottom:18px">
  <form method="POST" style="display:flex;align-items:center;gap:8px;background:rgba(255,255,255,.05);padding:10px 14px;border-radius:10px">
    <input type="hidden" name="action" value="set_commission">
    <label style="font-size:.83rem;color:#ccc">Commission Rate %</label>
    <input type="number" name="commission_rate" value="{commission}" min="0" max="50" step="0.5"
      style="width:80px;background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.2);color:#fff;border-radius:6px;padding:5px 8px">
    <button type="submit" style="background:#e94560;color:#fff;border:none;border-radius:6px;padding:5px 12px;cursor:pointer;font-size:.82rem">Save</button>
  </form>
</div>

<form method="GET" style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px">
  <input name="q" value="{_sq}" placeholder="Search title / seller..." style="flex:1;min-width:160px;background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.15);color:#fff;border-radius:8px;padding:6px 12px;font-size:.85rem">
  <select name="status" style="background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.15);color:#fff;border-radius:8px;padding:6px 10px;font-size:.85rem">
    {status_opts}
  </select>
  <button type="submit" style="background:#e94560;color:#fff;border:none;border-radius:8px;padding:6px 14px;cursor:pointer;font-size:.85rem">Filter</button>
</form>

<div style="font-size:.8rem;color:#aaa;margin-bottom:8px">{total} listing(s)</div>
<div style="overflow-x:auto">
<table style="width:100%;border-collapse:collapse;font-size:.82rem">
  <thead><tr style="color:#e94560;border-bottom:1px solid rgba(233,69,96,.3)">
    <th style="padding:8px;text-align:left">ID</th><th>Title</th><th>Seller</th>
    <th>Type / Cat</th><th>Price</th><th>Bids</th><th>Status</th><th>Views</th><th></th>
  </tr></thead>
  <tbody>{rows or '<tr><td colspan="9" style="text-align:center;color:#aaa;padding:20px">No listings</td></tr>'}</tbody>
</table></div>
{pag_html}
</div></body></html>""")

    print("[Marketplace] Routes registered ✓")
