"""
Lucko.ai Live Casino Routes
/user/casino/live              — player lobby (game grid)
/user/casino/live/play/<inst>  — iframe wrapper with cashout
/api/casino/live/play          — buy-in + get game URL (JSON)
/api/casino/live/cashout       — transfer back to bot wallet (JSON)
/api/casino/live/balance       — Lucko wallet balance (JSON)
/webhook/lucko/notify          — Lucko bet/payout webhook
/admin/casino/live             — admin settings panel
"""
import json
import time
from flask import request, jsonify, session, render_template_string, redirect

import modules.lucko_client as _api
import modules.lucko_wallet as _wallet

# ── Game type meta ─────────────────────────────────────────────────────────────

_TYPE_LABELS = {
    'live':    '🎬 Live',
    'lottery': '🎱 Lottery',
    'crash':   '🚀 Crash',
    'slot':    '🎰 Slot',
    'table':   '🃏 Table',
}


# ── HTML templates ─────────────────────────────────────────────────────────────

_LOBBY_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Live Casino — Onichan</title>
{{ user_css|safe }}
<style>
.lc-wrap{max-width:1200px;margin:0 auto;padding:20px 16px 80px}
.lc-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:24px;gap:12px;flex-wrap:wrap}
.lc-header h1{margin:0;font-size:1.5rem;background:linear-gradient(135deg,#a855f7,#ec4899);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}
.bal-box{background:rgba(168,85,247,.15);border:1px solid rgba(168,85,247,.3);border-radius:12px;padding:10px 20px;display:flex;gap:20px;align-items:center}
.bal-box .lbl{font-size:.68rem;color:#a78bfa;text-transform:uppercase;letter-spacing:.06em}
.bal-box .val{font-size:1.1rem;font-weight:700;color:#e0d7ff}
.notice{background:rgba(239,68,68,.1);border:1px solid rgba(239,68,68,.35);border-radius:10px;padding:14px 18px;color:#fca5a5;margin-bottom:20px;font-size:.875rem}
.notice a{color:#f87171}
.filter-bar{display:flex;gap:8px;margin-bottom:20px;flex-wrap:wrap}
.fbt{background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.13);color:#d1d5db;padding:6px 16px;border-radius:20px;cursor:pointer;font-size:.8rem;transition:.2s}
.fbt:hover,.fbt.active{background:rgba(168,85,247,.35);border-color:#a855f7;color:#e0d7ff}
.game-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:16px}
.lc-card{background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.09);border-radius:14px;overflow:hidden;cursor:pointer;transition:transform .2s,box-shadow .2s}
.lc-card:hover{transform:translateY(-4px);box-shadow:0 8px 28px rgba(168,85,247,.3)}
.lc-thumb{width:100%;aspect-ratio:4/3;background:linear-gradient(135deg,#1e1b4b,#312e81);display:flex;align-items:center;justify-content:center;font-size:2.8rem;position:relative;overflow:hidden}
.lc-thumb img{width:100%;height:100%;object-fit:cover;position:absolute;inset:0}
.type-badge{position:absolute;top:7px;right:7px;background:rgba(0,0,0,.72);color:#a78bfa;font-size:.58rem;padding:3px 7px;border-radius:20px;font-weight:700;letter-spacing:.04em;z-index:1}
.lc-body{padding:10px 12px 12px}
.lc-name{font-size:.8rem;font-weight:600;color:#e0d7ff;margin-bottom:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.lc-sub{font-size:.65rem;color:#6b7280;margin-bottom:8px}
.play-btn{width:100%;background:linear-gradient(135deg,#7c3aed,#a21caf);color:#fff;border:none;padding:7px;border-radius:8px;font-size:.75rem;font-weight:700;cursor:pointer;transition:opacity .2s}
.play-btn:hover{opacity:.82}
.empty{text-align:center;padding:60px 20px;color:#6b7280;grid-column:1/-1}
.empty .ei{font-size:3rem;margin-bottom:10px}
/* Buy-in modal */
.modal-overlay{position:fixed;inset:0;background:rgba(0,0,0,.78);z-index:9000;display:flex;align-items:center;justify-content:center;padding:20px}
.modal-box{background:#1a1a2e;border:1px solid rgba(168,85,247,.4);border-radius:18px;padding:28px;max-width:380px;width:100%}
.modal-box h3{margin:0 0 5px;color:#e0d7ff;font-size:1.05rem}
.modal-sub{color:#9ca3af;font-size:.78rem;margin-bottom:18px}
.mrow{display:flex;align-items:center;gap:10px;margin-bottom:13px}
.mrow label{color:#a78bfa;font-size:.78rem;min-width:80px}
.minp{flex:1;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.18);color:#e0d7ff;padding:9px 12px;border-radius:8px;font-size:.95rem}
.quick{display:flex;gap:6px;margin-bottom:16px;flex-wrap:wrap}
.qb{background:rgba(124,58,237,.22);border:1px solid rgba(124,58,237,.38);color:#c4b5fd;padding:5px 10px;border-radius:6px;cursor:pointer;font-size:.75rem;transition:.2s}
.qb:hover{background:rgba(124,58,237,.45)}
.mact{display:flex;gap:10px}
.btn-confirm{flex:1;background:linear-gradient(135deg,#7c3aed,#a21caf);color:#fff;border:none;padding:11px;border-radius:10px;font-weight:700;cursor:pointer;font-size:.9rem}
.btn-cancel{background:rgba(255,255,255,.08);color:#9ca3af;border:1px solid rgba(255,255,255,.14);padding:11px 18px;border-radius:10px;cursor:pointer;font-size:.9rem}
.spin{display:inline-block;width:16px;height:16px;border:2px solid #fff;border-top-color:transparent;border-radius:50%;animation:sp .7s linear infinite;vertical-align:middle;margin-right:5px}
@keyframes sp{to{transform:rotate(360deg)}}
</style>
</head>
<body>
{{ sidebar|safe }}
<div class="main-content">
<div class="lc-wrap">

  <div class="lc-header">
    <div>
      <a href="/user/casino" style="color:#a78bfa;font-size:.8rem;text-decoration:none">← Casino</a>
      <h1 style="margin-top:5px">🎬 Live & Crash Games</h1>
    </div>
    <div class="bal-box">
      <div><div class="lbl">Balance</div><div class="val" id="balVal">${{ balance }}</div></div>
    </div>
  </div>

  {% if not configured %}
  <div class="notice">⚠️ <strong>API not configured.</strong>
    Set <code>LUCKO_AGENT_ID</code> and <code>LUCKO_SECRET</code> in Replit Secrets.
    <a href="/admin/casino/live">Admin →</a></div>
  {% endif %}

  {% if configured and not enabled %}
  <div class="notice">🔒 Live casino is currently <strong>disabled</strong> by admin.
    <a href="/admin/casino/live">Enable →</a></div>
  {% endif %}

  {% if configured and enabled %}
  <div class="filter-bar">
    <button class="fbt active" onclick="filterGames('')"  id="fbt-all">All ({{ rooms|length }})</button>
    <button class="fbt"        onclick="filterGames('live')"    id="fbt-live">🎬 Live</button>
    <button class="fbt"        onclick="filterGames('crash')"   id="fbt-crash">🚀 Crash</button>
    <button class="fbt"        onclick="filterGames('lottery')" id="fbt-lottery">🎱 Lottery</button>
  </div>
  {% endif %}

  <div class="game-grid" id="grid">
  {% if rooms %}
    {% for r in rooms %}
    <div class="lc-card" data-type="{{ r.game_type }}"
         onclick="openBuyIn('{{ r.inst_id }}','{{ r.name|replace("'","") }}','{{ r.game_type }}')">
      <div class="lc-thumb">
        {% if r.cover %}
        <img src="{{ r.cover }}" alt="{{ r.name }}" loading="lazy" onerror="this.style.display='none'">
        {% endif %}
        <span style="z-index:1;position:relative">🎮</span>
        <div class="type-badge">{{ type_labels.get(r.game_type, r.game_type) }}</div>
      </div>
      <div class="lc-body">
        <div class="lc-name" title="{{ r.name }}">{{ r.name }}</div>
        <div class="lc-sub">{{ r.game_name }} · Lucko.ai</div>
        <button class="play-btn"
          onclick="event.stopPropagation();openBuyIn('{{ r.inst_id }}','{{ r.name|replace("'","") }}','{{ r.game_type }}')">
          ▶ Play Now
        </button>
      </div>
    </div>
    {% endfor %}
  {% else %}
    <div class="empty">
      <div class="ei">{% if configured and enabled %}🔄{% else %}🎬{% endif %}</div>
      <p>{% if configured and enabled %}No games found — <a href="/admin/casino/live" style="color:#a78bfa">refresh game list</a>{% else %}Live games will appear here once configured.{% endif %}</p>
    </div>
  {% endif %}
  </div>

</div><!-- .lc-wrap -->
</div><!-- .main-content -->

<!-- Buy-in modal -->
<div class="modal-overlay" id="modal" style="display:none" onclick="if(event.target===this)closeModal()">
  <div class="modal-box">
    <h3 id="mTitle">🎮 Play</h3>
    <div class="modal-sub">Transfer credits to your game wallet to start playing.</div>
    <div class="mrow">
      <label>Balance</label>
      <span id="mBal" style="color:#4ade80;font-weight:700"></span>
    </div>
    <div class="mrow">
      <label>Buy-in</label>
      <input class="minp" type="number" id="buyinAmt"
        min="{{ min_buyin }}" max="{{ max_buyin }}" step="1" value="{{ default_buyin }}">
    </div>
    <div class="quick">
      <button class="qb" onclick="setAmt({{ default_buyin }})">${{ default_buyin|int }}</button>
      <button class="qb" onclick="setAmt({{ (default_buyin*2)|int }})">${{ (default_buyin*2)|int }}</button>
      <button class="qb" onclick="setAmt({{ (default_buyin*5)|int }})">${{ (default_buyin*5)|int }}</button>
      <button class="qb" onclick="setAmt('all')">All In</button>
    </div>
    <div class="mact">
      <button class="btn-cancel" onclick="closeModal()">Cancel</button>
      <button class="btn-confirm" id="confirmBtn" onclick="confirmPlay()">🎮 Play!</button>
    </div>
  </div>
</div>

<script>
var _inst='', _name='', _type='';
function openBuyIn(inst,name,type){
  _inst=inst; _name=name; _type=type;
  document.getElementById('mTitle').textContent='🎮 '+name;
  document.getElementById('mBal').textContent=document.getElementById('balVal').textContent;
  document.getElementById('modal').style.display='flex';
}
function closeModal(){ document.getElementById('modal').style.display='none'; }
function setAmt(v){
  if(v==='all'){
    var b=parseFloat(document.getElementById('balVal').textContent.replace('$',''))||0;
    document.getElementById('buyinAmt').value=Math.min(b,{{ max_buyin }}).toFixed(2);
  } else {
    document.getElementById('buyinAmt').value=parseFloat(v).toFixed(2);
  }
}
function confirmPlay(){
  var amt=parseFloat(document.getElementById('buyinAmt').value)||0;
  if(amt<=0){alert('Enter a buy-in amount');return;}
  var btn=document.getElementById('confirmBtn');
  btn.disabled=true;
  btn.innerHTML='<span class="spin"></span>Entering…';
  fetch('/api/casino/live/play',{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({inst_id:_inst,game_name:_name,game_type:_type,buyin:amt})
  }).then(r=>r.json()).then(d=>{
    if(d.ok){
      sessionStorage.setItem('lc_game_url',d.game_url);
      sessionStorage.setItem('lc_lucko_bal',d.lucko_balance||'0');
      window.location.href='/user/casino/live/play/'+_inst;
    } else {
      alert('Error: '+(d.error||'Unknown'));
      btn.disabled=false; btn.innerHTML='🎮 Play!';
    }
  }).catch(()=>{alert('Network error');btn.disabled=false;btn.innerHTML='🎮 Play!';});
}
function filterGames(type){
  document.querySelectorAll('.fbt').forEach(b=>b.classList.remove('active'));
  var el=document.getElementById(type?'fbt-'+type:'fbt-all');
  if(el) el.classList.add('active');
  document.querySelectorAll('.lc-card').forEach(c=>{
    c.style.display=(!type||c.dataset.type===type)?'':'none';
  });
}
</script>
</body>
</html>"""


_PLAY_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{{ game_name }} — Onichan Live</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0d0d1a;color:#e0d7ff;font-family:system-ui,sans-serif;height:100vh;display:flex;flex-direction:column;overflow:hidden}
.ctrl{background:rgba(13,13,26,.96);border-bottom:1px solid rgba(168,85,247,.3);padding:9px 14px;display:flex;align-items:center;gap:10px;z-index:100;flex-shrink:0}
.ctrl .gn{font-weight:700;color:#e0d7ff;flex:1;font-size:.88rem;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.bal-chip{background:rgba(74,222,128,.14);border:1px solid rgba(74,222,128,.3);color:#4ade80;padding:4px 12px;border-radius:20px;font-size:.78rem;font-weight:700;white-space:nowrap}
.btn-exit{background:linear-gradient(135deg,#7c3aed,#a21caf);color:#fff;border:none;padding:8px 15px;border-radius:8px;font-size:.78rem;font-weight:700;cursor:pointer;white-space:nowrap}
.btn-exit:hover{opacity:.85}
.game-frame{flex:1;position:relative;overflow:hidden}
.game-frame iframe{width:100%;height:100%;border:none;display:block}
.no-url{display:flex;align-items:center;justify-content:center;flex-direction:column;gap:14px;color:#9ca3af;text-align:center;padding:30px;height:100%}
.no-url .ei{font-size:3rem}
/* Cashout overlay */
.co-overlay{position:fixed;inset:0;background:rgba(0,0,0,.88);z-index:9999;display:none;align-items:center;justify-content:center}
.co-box{background:#1a1a2e;border:1px solid rgba(74,222,128,.4);border-radius:18px;padding:32px;max-width:340px;width:100%;text-align:center}
.co-box h3{color:#4ade80;margin-bottom:8px;font-size:1.25rem}
.co-amt{font-size:2rem;font-weight:800;color:#e0d7ff;margin:12px 0}
.co-meta{color:#9ca3af;font-size:.8rem;margin-bottom:20px}
.btn-done{background:linear-gradient(135deg,#7c3aed,#a21caf);color:#fff;border:none;padding:12px 32px;border-radius:10px;font-weight:700;cursor:pointer;font-size:1rem}
.spin{display:inline-block;width:22px;height:22px;border:2.5px solid #a78bfa;border-top-color:transparent;border-radius:50%;animation:sp .7s linear infinite}
@keyframes sp{to{transform:rotate(360deg)}}
</style>
</head>
<body>
<div class="ctrl">
  <a href="/user/casino/live" style="color:#a78bfa;font-size:1.2rem;text-decoration:none" title="Back to lobby">←</a>
  <div class="gn">{{ game_name }}</div>
  <div class="bal-chip" id="luckoBalChip">
    <span id="luckoBal">{{ "%.2f"|format(lucko_balance) }}</span> credits in game
  </div>
  <button class="btn-exit" id="exitBtn" onclick="doExit()">💸 Cash Out & Exit</button>
</div>

<div class="game-frame">
{% if game_url %}
  <iframe id="gf" src="{{ game_url }}" allow="fullscreen *" allowfullscreen></iframe>
{% else %}
  <div class="no-url">
    <div class="ei">⚠️</div>
    <p>Could not load game.<br><span style="color:#ef4444;font-size:.8rem">{{ error or 'Unknown error' }}</span></p>
    <a href="/user/casino/live" style="color:#a78bfa;margin-top:8px">← Back to lobby</a>
  </div>
{% endif %}
</div>

<!-- Cashout result overlay -->
<div class="co-overlay" id="coOverlay">
  <div class="co-box">
    <h3 id="coTitle">💸 Cashing Out…</h3>
    <div class="co-amt" id="coAmt"><span class="spin"></span></div>
    <div class="co-meta" id="coMeta"></div>
    <button class="btn-done" id="coDone" style="display:none" onclick="window.location='/user/casino/live'">← Back to Lobby</button>
  </div>
</div>

<script>
var _exiting=false;
var _instId='{{ inst_id }}';

function doExit(){
  if(_exiting) return;
  _exiting=true;
  document.getElementById('exitBtn').disabled=true;
  document.getElementById('coOverlay').style.display='flex';
  fetch('/api/casino/live/cashout',{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({inst_id:_instId})
  }).then(r=>r.json()).then(d=>{
    if(d.ok){
      document.getElementById('coTitle').textContent='✅ Cashed Out!';
      document.getElementById('coAmt').textContent='$'+parseFloat(d.credits_back||0).toFixed(2);
      var meta='';
      if(d.commission>0.001) meta='House commission: $'+parseFloat(d.commission).toFixed(2)+' ('+d.commission_pct+'%)';
      document.getElementById('coMeta').textContent=meta;
    } else {
      document.getElementById('coTitle').textContent='⚠️ Cashout Issue';
      document.getElementById('coAmt').textContent='—';
      document.getElementById('coMeta').textContent=d.error||'Please contact support.';
    }
    document.getElementById('coDone').style.display='inline-block';
  }).catch(function(){
    document.getElementById('coTitle').textContent='⚠️ Network Error';
    document.getElementById('coAmt').textContent='—';
    document.getElementById('coMeta').textContent='Please try again.';
    document.getElementById('coDone').style.display='inline-block';
  });
}

// sendBeacon fires the cashout request before the page unloads — guaranteed
// delivery even when the user closes the tab or navigates away.
// The server ignores any client-supplied inst_id, so no payload is needed.
window.addEventListener('pagehide', function(){
  if(!_exiting && {{ 'true' if game_url else 'false' }}){
    navigator.sendBeacon('/api/casino/live/cashout', new Blob(['{}'],{type:'application/json'}));
  }
});
</script>
</body>
</html>"""


_ADMIN_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Lucko.ai — Admin</title>
{{ admin_css|safe }}
<style>
.wrap{max-width:920px;margin:0 auto;padding:20px}
.sec{background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.1);border-radius:12px;padding:20px;margin-bottom:20px}
.sec h3{margin:0 0 16px;color:#e0d7ff;font-size:.95rem;font-weight:700}
.badge{display:inline-flex;align-items:center;gap:6px;padding:4px 12px;border-radius:20px;font-size:.75rem;font-weight:700}
.badge-ok{background:rgba(74,222,128,.2);color:#4ade80;border:1px solid rgba(74,222,128,.3)}
.badge-err{background:rgba(239,68,68,.2);color:#ef4444;border:1px solid rgba(239,68,68,.3)}
.inp{background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.18);color:#e0d7ff;padding:8px 12px;border-radius:8px;font-size:.875rem}
.inp-sm{width:110px}
.frow{display:flex;gap:12px;align-items:center;margin-bottom:12px;flex-wrap:wrap}
.frow label{color:#a78bfa;font-size:.8rem;min-width:160px}
.msg{padding:10px 16px;border-radius:8px;margin-bottom:16px;font-size:.875rem}
.msg-ok{background:rgba(74,222,128,.14);color:#4ade80;border:1px solid rgba(74,222,128,.3)}
.msg-err{background:rgba(239,68,68,.14);color:#f87171;border:1px solid rgba(239,68,68,.3)}
.table-wrap{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:.8rem}
th,td{padding:8px 12px;text-align:left;border-bottom:1px solid rgba(255,255,255,.06)}
th{color:#a78bfa;font-weight:600}
.tag{padding:2px 8px;border-radius:12px;font-size:.7rem;font-weight:700}
.tag-in{background:rgba(74,222,128,.2);color:#4ade80}
.tag-out{background:rgba(239,68,68,.2);color:#ef4444}
.tag-ok{background:rgba(74,222,128,.2);color:#4ade80}
.tag-fail{background:rgba(239,68,68,.2);color:#ef4444}
.tag-pend{background:rgba(251,191,36,.2);color:#fbbf24}
.toggle{position:relative;display:inline-block;width:42px;height:22px}
.toggle input{opacity:0;width:0;height:0}
.sl{position:absolute;inset:0;background:#374151;border-radius:11px;cursor:pointer;transition:.3s}
.toggle input:checked+.sl{background:#7c3aed}
.sl:before{content:"";position:absolute;width:16px;height:16px;left:3px;bottom:3px;background:#fff;border-radius:50%;transition:.3s}
.toggle input:checked+.sl:before{transform:translateX(20px)}
.game-row{display:flex;align-items:center;gap:10px;padding:8px 0;border-bottom:1px solid rgba(255,255,255,.05)}
.game-row .gname{flex:1;color:#d1d5db;font-size:.83rem;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0}
.stat-box{display:flex;gap:24px;flex-wrap:wrap;margin-bottom:16px}
.stat{min-width:120px}
.stat .slbl{font-size:.68rem;color:#a78bfa;text-transform:uppercase;letter-spacing:.05em;margin-bottom:4px}
.stat .sval{font-size:1.4rem;font-weight:800;color:#e0d7ff}
</style>
</head>
<body>
<div class="wrap">
  <div style="display:flex;align-items:center;gap:12px;margin-bottom:20px;flex-wrap:wrap">
    <a href="/admin/casino" style="color:#a78bfa;text-decoration:none">← Casino Admin</a>
    <h2 style="margin:0;color:#e0d7ff;flex:1">🎬 Lucko.ai Live Casino</h2>
    <span class="badge {{ 'badge-ok' if configured else 'badge-err' }}">
      {{ '✅ API Ready' if configured else '❌ Not Configured' }}
    </span>
  </div>

  {% if message %}
  <div class="msg {{ 'msg-ok' if msg_ok else 'msg-err' }}">{{ message }}</div>
  {% endif %}

  <!-- Global settings -->
  <div class="sec">
    <h3>Global Settings</h3>
    <form method="POST">
    <input type="hidden" name="action" value="save_global">
    <div class="frow">
      <label>Live Casino Enabled</label>
      <label class="toggle"><input type="checkbox" name="enabled" {{ 'checked' if lucko_enabled }}>
        <span class="sl"></span></label>
    </div>
    <div class="frow">
      <label>Default Commission %</label>
      <input class="inp inp-sm" type="number" name="default_commission_pct"
        value="{{ commission_pct }}" min="0" max="20" step="0.1">
      <small style="color:#6b7280">Applied on cashout</small>
    </div>
    <div class="frow">
      <label>Default Buy-in ($)</label>
      <input class="inp inp-sm" type="number" name="default_buyin"
        value="{{ default_buyin }}" min="1" step="1">
    </div>
    <div class="frow">
      <label>Min / Max Buy-in ($)</label>
      <input class="inp inp-sm" type="number" name="min_buyin" value="{{ min_buyin }}" min="0.01" step="0.01">
      <span style="color:#6b7280">–</span>
      <input class="inp inp-sm" type="number" name="max_buyin" value="{{ max_buyin }}" min="1" step="1">
    </div>
    <button type="submit" class="btn btn-primary">Save Settings</button>
    </form>
  </div>

  <!-- API Credentials & Status -->
  <div class="sec">
    <h3>API Credentials & Connection</h3>
    <div style="display:grid;grid-template-columns:160px 1fr;gap:8px 16px;font-size:.82rem;margin-bottom:16px;align-items:center">
      <span style="color:#a78bfa">Agent ID</span>
      <code style="color:{% if agent_id_display %}#4ade80{% else %}#ef4444{% endif %}">
        {{ agent_id_display or '❌ NOT SET — add LUCKO_AGENT_ID to Replit Secrets' }}</code>
      <span style="color:#a78bfa">Secret</span>
      <span style="color:{% if secret_set %}#4ade80{% else %}#ef4444{% endif %}">
        {{ '✅ Set (LUCKO_SECRET)' if secret_set else '❌ NOT SET — add LUCKO_SECRET to Replit Secrets' }}</span>
      <span style="color:#a78bfa">API Base URL</span>
      <code style="color:#9ca3af;font-size:.75rem">{{ base_url_display }}</code>
    </div>
    {% if not configured %}
    <div style="background:rgba(239,68,68,.1);border:1px solid rgba(239,68,68,.3);border-radius:8px;padding:12px;font-size:.8rem;color:#fca5a5;margin-bottom:14px">
      <strong>Setup required:</strong> Go to Replit Secrets (🔑 icon in sidebar) and add:<br>
      • <code>LUCKO_AGENT_ID</code> — your Lucko agent ID<br>
      • <code>LUCKO_SECRET</code> — your Lucko signing secret<br>
      • <code>LUCKO_BASE_URL</code> (optional) — defaults to <code>https://api.aigapi.com</code>
    </div>
    {% endif %}
    <div style="display:flex;gap:8px;flex-wrap:wrap">
      <form method="POST"><input type="hidden" name="action" value="ping_api">
        <button type="submit" class="btn btn-purple">🔗 Test Connection</button></form>
      <form method="POST"><input type="hidden" name="action" value="refresh_games">
        <button type="submit" class="btn btn-purple">🔄 Refresh Games ({{ rooms|length }} loaded)</button></form>
    </div>
    {% if ping_result %}
    <div style="margin-top:12px;padding:10px;background:rgba(255,255,255,.04);border-radius:8px;font-size:.78rem;color:#9ca3af;word-break:break-all">
      {{ ping_result }}</div>
    {% endif %}
  </div>

  <!-- Per-game settings -->
  {% if rooms %}
  <div class="sec">
    <h3>Game Room Settings ({{ rooms|length }} rooms)</h3>
    <form method="POST">
    <input type="hidden" name="action" value="save_games">
    <div style="max-height:420px;overflow-y:auto;padding-right:4px">
    {% for r in rooms %}
    <div class="game-row">
      <span class="gname" title="{{ r.name }}">
        {{ r.name }}
        <span style="color:#6b7280;font-size:.68rem">({{ r.game_type }})</span>
      </span>
      <label class="toggle" title="Enable/Disable">
        <input type="checkbox" name="enabled_{{ r.inst_id }}" {{ 'checked' if r.enabled }}>
        <span class="sl"></span></label>
      <input type="number" class="inp" style="width:76px"
        name="comm_{{ r.inst_id }}" value="{{ r.commission_pct }}"
        min="0" max="20" step="0.1" title="Commission %">
      <span style="color:#6b7280;font-size:.7rem">%</span>
    </div>
    {% endfor %}
    </div>
    <button type="submit" class="btn btn-primary" style="margin-top:14px">Save Game Settings</button>
    </form>
  </div>
  {% endif %}

  <!-- Stats + sweep -->
  <div class="sec">
    <h3>Wallet Overview</h3>
    <div class="stat-box">
      <div class="stat">
        <div class="slbl">Members</div>
        <div class="sval">{{ member_count }}</div>
      </div>
      <div class="stat">
        <div class="slbl">Ever Deposited</div>
        <div class="sval">${{ total_in }}</div>
      </div>
      <div class="stat">
        <div class="slbl">Live Exposure</div>
        <div class="sval" style="color:#fbbf24" title="Credits currently inside Lucko wallets (deposited minus withdrawn)">${{ live_exposure }}</div>
      </div>
      <div class="stat">
        <div class="slbl">Commission Earned</div>
        <div class="sval" style="color:#4ade80">${{ total_commission }}</div>
      </div>
      <div class="stat">
        <div class="slbl">Webhook Events</div>
        <div class="sval">{{ wh_count }}</div>
      </div>
    </div>
    <form method="POST" onsubmit="return confirm('Force cashout ALL member wallets now?')">
      <input type="hidden" name="action" value="sweep_all">
      <button type="submit" class="btn btn-red">⚡ Emergency Sweep All Wallets</button>
    </form>
  </div>

  <!-- Transfer log -->
  <div class="sec">
    <h3>Recent Transfers (last 50)</h3>
    {% if transfers %}
    <div class="table-wrap">
    <table>
      <tr><th>Time</th><th>User ID</th><th>Dir</th><th>Credits</th><th>Commission</th><th>Status</th></tr>
      {% for t in transfers %}
      <tr>
        <td style="color:#6b7280">{{ t.created_at.strftime('%m/%d %H:%M') if t.created_at else '—' }}</td>
        <td>{{ t.telegram_id }}</td>
        <td><span class="tag {{ 'tag-in' if t.direction=='in' else 'tag-out' }}">{{ t.direction }}</span></td>
        <td>${{ '%.2f'|format(t.credits_lucko|float) }}</td>
        <td style="color:#fbbf24">${{ '%.2f'|format(t.commission_amount|float) }}</td>
        <td><span class="tag {% if t.status=='completed' %}tag-ok{% elif t.status=='failed' %}tag-fail{% else %}tag-pend{% endif %}">
          {{ t.status }}</span></td>
      </tr>
      {% endfor %}
    </table>
    </div>
    {% else %}
    <p style="color:#6b7280">No transfers yet.</p>
    {% endif %}
  </div>

</div>
</body>
</html>"""


# ── Route registration ─────────────────────────────────────────────────────────

def register_lucko_routes(app, user_required, owner_required,
                          get_user_sidebar, USER_CSS, ADMIN_CSS):

    # ── User: lobby ──────────────────────────────────────────────────────────

    @app.route('/user/casino/live')
    @user_required
    def user_casino_live():
        from modules.cc_shop import get_user_balance
        user_id   = session.get('user_id')
        balance   = get_user_balance(user_id)
        configured = _api.is_configured()
        enabled    = _wallet.is_enabled()

        rooms = []
        if configured and enabled:
            rooms = [r for r in _wallet.get_cached_rooms() if r['enabled']]

        return render_template_string(
            _LOBBY_HTML,
            sidebar      = get_user_sidebar('casino_live', '🎬 Live Casino'),
            user_css     = USER_CSS,
            balance      = f"{balance:.2f}",
            configured   = configured,
            enabled      = enabled,
            rooms        = rooms,
            type_labels  = _TYPE_LABELS,
            min_buyin    = float(_wallet.get_setting('min_buyin',    '1.00')),
            max_buyin    = float(_wallet.get_setting('max_buyin',   '500.00')),
            default_buyin= float(_wallet.get_setting('default_buyin', '10.00')),
        )

    # ── User: play page (iframe wrapper) ─────────────────────────────────────

    @app.route('/user/casino/live/play/<inst_id>')
    @user_required
    def user_lucko_play(inst_id):
        user_id    = session.get('user_id')
        game_name  = session.get(f'lc_name_{inst_id}', inst_id)
        lucko_bal  = session.get(f'lc_bal_{inst_id}',  0.0)

        game_url = ''
        error    = ''
        if _api.is_configured():
            res = _wallet.get_lobby_url(user_id, inst_id)
            if res['ok']:
                game_url = res['url']
            else:
                error = res.get('error', 'Could not load game')
        else:
            error = 'Lucko API not configured'

        return render_template_string(
            _PLAY_HTML,
            inst_id      = inst_id,
            game_name    = game_name,
            game_url     = game_url,
            lucko_balance= lucko_bal,
            error        = error,
        )

    # ── API: buy-in ───────────────────────────────────────────────────────────

    @app.route('/api/casino/live/play', methods=['POST'])
    @user_required
    def api_lucko_play():
        user_id = session.get('user_id')
        data    = request.get_json(silent=True) or {}
        inst_id = str(data.get('inst_id', ''))
        buyin   = float(data.get('buyin') or
                        _wallet.get_setting('default_buyin', '10'))
        game_name = str(data.get('game_name', inst_id))

        if not inst_id:
            return jsonify({'ok': False, 'error': 'Missing inst_id'})
        if not _api.is_configured():
            return jsonify({'ok': False, 'error': 'Lucko API not configured'})
        if not _wallet.is_enabled():
            return jsonify({'ok': False, 'error': 'Live casino is disabled'})

        # Buy in
        res = _wallet.buy_in(user_id, buyin, inst_id)
        if not res['ok']:
            return jsonify(res)

        # Get game URL
        url_res = _wallet.get_lobby_url(user_id, inst_id)
        if not url_res['ok']:
            # Zero-commission rollback — no game session started, no commission owed
            _wallet.rollback_buy_in(user_id)
            return jsonify({'ok': False, 'error': url_res.get('error', 'Could not get game URL')})

        # Store context in session for the play page
        session[f'lc_name_{inst_id}'] = game_name
        session[f'lc_bal_{inst_id}']  = res['lucko_balance']

        return jsonify({
            'ok':           True,
            'game_url':     url_res['url'],
            'lucko_balance': res['lucko_balance'],
        })

    # ── API: cash-out ─────────────────────────────────────────────────────────

    @app.route('/api/casino/live/cashout', methods=['POST'])
    @user_required
    def api_lucko_cashout():
        user_id = session.get('user_id')
        # inst_id from the client is intentionally ignored here.
        # Commission is determined by the server-side active session recorded
        # at buy-in time, so users cannot manipulate the commission rate by
        # submitting a different or blank inst_id.
        result  = _wallet.cash_out(user_id)
        return jsonify(result)

    # ── API: Lucko balance ────────────────────────────────────────────────────

    @app.route('/api/casino/live/balance')
    @user_required
    def api_lucko_balance():
        user_id   = session.get('user_id')
        lucko_uid = _wallet.ensure_member(user_id)
        bal = _api.get_balance(lucko_uid) if lucko_uid else None
        return jsonify({'lucko_balance': bal})

    # ── Webhook ───────────────────────────────────────────────────────────────

    @app.route('/webhook/lucko/notify', methods=['POST'])
    def webhook_lucko():
        """
        Receives bet/payout events from Lucko.ai.
        Payload (JSON): {agent_id, user_id, inst_id, game_id,
                          bet_amount, win_amount, txn_id, sign, timestamp, ...}
        We verify the sign, then persist the event and reconcile any
        large negative-net wallets back to the bot balance.
        """
        import logging
        wlog = logging.getLogger('lucko_webhook')

        data = request.get_json(silent=True) or {}
        received_sign = data.get('sign', '')
        agent_id, secret, _ = _api._cfg()

        # Verify signature
        params_for_sign = {k: v for k, v in data.items()
                          if k != 'sign' and v is not None and str(v) != ''}
        expected = _api._sign(secret, params_for_sign)
        if received_sign != expected:
            wlog.warning(f'[lucko_wh] invalid sign received: {received_sign!r}')
            return jsonify({'code': 400, 'message': 'invalid sign'})

        user_id_raw  = str(data.get('user_id', ''))
        inst_id      = str(data.get('inst_id', ''))
        game_id      = str(data.get('game_id', ''))
        txn_id_wh    = str(data.get('txn_id', ''))
        bet_amount   = float(data.get('bet_amount', 0) or 0)
        win_amount   = float(data.get('win_amount', 0) or 0)
        event_type   = str(data.get('event_type', 'bet'))

        # Persist webhook event
        from modules.database import _execute_with_retry as _q
        _q("""
            CREATE TABLE IF NOT EXISTS lucko_webhook_events (
                id SERIAL PRIMARY KEY,
                lucko_user_id VARCHAR(120),
                inst_id VARCHAR(50),
                game_id VARCHAR(50),
                txn_id VARCHAR(150),
                bet_amount DECIMAL(12,4) DEFAULT 0,
                win_amount DECIMAL(12,4) DEFAULT 0,
                event_type VARCHAR(40),
                raw_payload JSONB,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        try:
            _q("""
                INSERT INTO lucko_webhook_events
                    (lucko_user_id, inst_id, game_id, txn_id,
                     bet_amount, win_amount, event_type, raw_payload)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT DO NOTHING
            """, (user_id_raw, inst_id, game_id, txn_id_wh,
                  bet_amount, win_amount, event_type, json.dumps(data)))
        except Exception as e:
            wlog.warning(f'[lucko_wh] insert failed: {e}')

        # If this is a payout event and win_amount > 0, invalidate token cache
        # so the next balance poll reflects the new amount.
        if win_amount > 0 and user_id_raw:
            with _wallet._token_lock:
                _wallet._token_cache.pop(user_id_raw, None)

        return jsonify({'code': 200, 'message': 'ok'})

    # ── Admin: live casino settings ───────────────────────────────────────────

    @app.route('/admin/casino/live', methods=['GET', 'POST'])
    @admin_required
    def admin_casino_live():
        from modules.database import _execute_with_retry as _q

        message     = ''
        msg_ok      = True
        ping_result = None

        if request.method == 'POST':
            action = request.form.get('action', '')

            if action == 'save_global':
                _wallet.set_setting('enabled',
                    'true' if request.form.get('enabled') else 'false')
                _wallet.set_setting('default_commission_pct',
                    request.form.get('default_commission_pct', '5'))
                _wallet.set_setting('default_buyin',
                    request.form.get('default_buyin', '10'))
                _wallet.set_setting('min_buyin',
                    request.form.get('min_buyin', '1'))
                _wallet.set_setting('max_buyin',
                    request.form.get('max_buyin', '500'))
                message = '✅ Settings saved!'

            elif action == 'ping_api':
                res = _api.ping()
                ok  = res.get('code') in (200, 700102)
                ping_result = (
                    f"code={res.get('code')} — {res.get('message','')}"
                    f"  {'✅ OK' if ok else '❌ FAIL'}"
                )
                msg_ok  = ok
                message = 'API ping complete.'

            elif action == 'refresh_games':
                rooms = _wallet.refresh_game_cache()
                message = f'✅ Refreshed — {len(rooms)} game rooms loaded.'

            elif action == 'save_games':
                all_rooms = _wallet.get_cached_rooms()
                for r in all_rooms:
                    iid = r['inst_id']
                    enabled = bool(request.form.get(f'enabled_{iid}'))
                    try:
                        comm = float(request.form.get(f'comm_{iid}',
                            _wallet.get_setting('default_commission_pct', '5')))
                    except (ValueError, TypeError):
                        comm = 5.0
                    _wallet.set_game_setting(iid, 'enabled', enabled)
                    _wallet.set_game_setting(iid, 'commission_pct', comm)
                message = '✅ Game settings saved!'

            elif action == 'sweep_all':
                result  = _wallet.sweep_all_members()
                message = (f"✅ Swept {result['swept']} wallets, "
                           f"${result['total_back']:.2f} returned. "
                           f"Errors: {result['errors']}")
                msg_ok  = result['errors'] == 0

        # All stats in a single round-trip using conditional aggregation
        try:
            _stats = _q("""
                SELECT
                    (SELECT COUNT(*) FROM lucko_members) AS member_count,
                    COALESCE(SUM(CASE WHEN direction='in'  AND status='completed' THEN credits_lucko    ELSE 0 END), 0) AS total_in,
                    COALESCE(SUM(CASE WHEN direction='out' AND status='completed' THEN credits_lucko    ELSE 0 END), 0) AS total_out,
                    COALESCE(SUM(CASE WHEN direction='out' AND status='completed' THEN commission_amount ELSE 0 END), 0) AS total_comm
                FROM lucko_transfers
            """, fetch_one=True) or {}
        except Exception:
            _stats = {}

        member_count  = int(_stats.get('member_count', 0))
        total_in      = float(_stats.get('total_in',   0))
        total_out     = float(_stats.get('total_out',  0))
        total_comm    = float(_stats.get('total_comm', 0))
        live_exposure = max(0.0, round(total_in - total_out, 2))

        # Webhook event count (separate table — one extra query only)
        try:
            wh_count = (_q(
                "SELECT COUNT(*) as c FROM lucko_webhook_events",
                fetch_one=True) or {}).get('c', 0)
        except Exception:
            wh_count = 0

        # Agent ID display (masked for security)
        import os
        agent_id_display = os.environ.get('LUCKO_AGENT_ID', '')
        secret_set       = bool(os.environ.get('LUCKO_SECRET', ''))
        base_url_display = os.environ.get('LUCKO_BASE_URL', 'https://api.aigapi.com (default)')

        rooms     = _wallet.get_cached_rooms()
        transfers = _wallet.get_recent_transfers(50)

        return render_template_string(
            _ADMIN_HTML,
            admin_css        = ADMIN_CSS,
            message          = message,
            msg_ok           = msg_ok,
            configured       = _api.is_configured(),
            lucko_enabled    = _wallet.is_enabled(),
            commission_pct   = float(_wallet.get_setting('default_commission_pct', '5')),
            default_buyin    = float(_wallet.get_setting('default_buyin', '10')),
            min_buyin        = float(_wallet.get_setting('min_buyin', '1')),
            max_buyin        = float(_wallet.get_setting('max_buyin', '500')),
            rooms            = rooms,
            transfers        = transfers,
            ping_result      = ping_result,
            member_count     = member_count,
            total_in         = f"{total_in:.2f}",
            total_commission = f"{total_comm:.2f}",
            live_exposure    = f"{live_exposure:.2f}",
            wh_count         = wh_count,
            agent_id_display = agent_id_display,
            secret_set       = secret_set,
            base_url_display = base_url_display,
        )
