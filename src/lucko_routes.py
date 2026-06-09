"""
Lucko.ai Live Casino Routes
/user/casino/live  — player-facing lobby + iframe wrapper
/admin/casino/live — admin settings panel
/api/casino/live/* — JSON API endpoints
/webhook/lucko/*   — Lucko notification webhooks
"""
import json
import time
from flask import request, jsonify, session, render_template_string, redirect

import modules.lucko_client as _api
import modules.lucko_wallet as _wallet


# ── Helpers ───────────────────────────────────────────────────────────────────

_GAME_TYPE_LABELS = {
    'live': 'Live Dealer',
    'slot': 'Slot',
    'table': 'Table',
    'fishing': 'Fishing',
    'lottery': 'Lottery',
    'arcade': 'Arcade',
}
_GAME_TYPE_ICONS = {
    'live': '🎬',
    'slot': '🎰',
    'table': '🃏',
    'fishing': '🎣',
    'lottery': '🎱',
    'arcade': '👾',
}

_LOBBY_HTML = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Live Casino — Onichan</title>
{{ user_css|safe }}
<style>
.lc-wrap{max-width:1200px;margin:0 auto;padding:20px 16px 80px}
.lc-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:24px;gap:12px;flex-wrap:wrap}
.lc-header h1{margin:0;font-size:1.5rem;background:linear-gradient(135deg,#a855f7,#ec4899);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.lc-bal-box{background:rgba(168,85,247,.15);border:1px solid rgba(168,85,247,.3);border-radius:12px;padding:10px 18px;display:flex;gap:20px;align-items:center;flex-wrap:wrap}
.lc-bal-box .lbl{font-size:.7rem;color:#a78bfa;text-transform:uppercase;letter-spacing:.05em}
.lc-bal-box .val{font-size:1.1rem;font-weight:700;color:#e0d7ff}
.notice-box{background:rgba(239,68,68,.1);border:1px solid rgba(239,68,68,.4);border-radius:10px;padding:14px 18px;color:#fca5a5;margin-bottom:20px;font-size:.875rem}
.notice-box a{color:#f87171;text-decoration:underline}
.filter-bar{display:flex;gap:8px;margin-bottom:20px;flex-wrap:wrap}
.fbt{background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.15);color:#d1d5db;padding:6px 14px;border-radius:20px;cursor:pointer;font-size:.8rem;transition:all .2s}
.fbt:hover,.fbt.active{background:rgba(168,85,247,.35);border-color:#a855f7;color:#e0d7ff}
.game-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:16px}
.lc-card{background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.1);border-radius:14px;overflow:hidden;cursor:pointer;transition:transform .2s,box-shadow .2s;position:relative}
.lc-card:hover{transform:translateY(-4px);box-shadow:0 8px 24px rgba(168,85,247,.3)}
.lc-thumb{width:100%;aspect-ratio:4/3;background:linear-gradient(135deg,#1e1b4b,#312e81);display:flex;align-items:center;justify-content:center;font-size:2.5rem;position:relative;overflow:hidden}
.lc-thumb img{width:100%;height:100%;object-fit:cover}
.lc-type-badge{position:absolute;top:8px;right:8px;background:rgba(0,0,0,.7);color:#a78bfa;font-size:.6rem;padding:3px 7px;border-radius:20px;font-weight:600;text-transform:uppercase}
.lc-card-body{padding:10px 12px 12px}
.lc-game-name{font-size:.8rem;font-weight:600;color:#e0d7ff;margin-bottom:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.lc-provider{font-size:.65rem;color:#9ca3af;margin-bottom:8px}
.lc-play-btn{width:100%;background:linear-gradient(135deg,#7c3aed,#a21caf);color:#fff;border:none;padding:7px;border-radius:8px;font-size:.75rem;font-weight:600;cursor:pointer;transition:opacity .2s}
.lc-play-btn:hover{opacity:.85}
.empty-state{text-align:center;padding:60px 20px;color:#6b7280}
.empty-state .ei{font-size:3rem;margin-bottom:12px}

/* Buy-in modal */
.modal-overlay{position:fixed;inset:0;background:rgba(0,0,0,.75);z-index:9000;display:flex;align-items:center;justify-content:center;padding:20px}
.modal-box{background:#1a1a2e;border:1px solid rgba(168,85,247,.4);border-radius:18px;padding:28px;max-width:380px;width:100%}
.modal-box h3{margin:0 0 6px;color:#e0d7ff;font-size:1.1rem}
.modal-box .sub{color:#9ca3af;font-size:.8rem;margin-bottom:20px}
.modal-row{display:flex;align-items:center;gap:10px;margin-bottom:14px}
.modal-row label{color:#a78bfa;font-size:.8rem;min-width:80px}
.modal-inp{flex:1;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.2);color:#e0d7ff;padding:8px 12px;border-radius:8px;font-size:.95rem}
.quick-btns{display:flex;gap:6px;margin-bottom:18px;flex-wrap:wrap}
.qb{background:rgba(124,58,237,.25);border:1px solid rgba(124,58,237,.4);color:#c4b5fd;padding:5px 10px;border-radius:6px;cursor:pointer;font-size:.75rem;transition:all .2s}
.qb:hover{background:rgba(124,58,237,.45)}
.modal-actions{display:flex;gap:10px}
.btn-confirm{flex:1;background:linear-gradient(135deg,#7c3aed,#a21caf);color:#fff;border:none;padding:11px;border-radius:10px;font-weight:700;cursor:pointer;font-size:.9rem}
.btn-cancel{background:rgba(255,255,255,.08);color:#9ca3af;border:1px solid rgba(255,255,255,.15);padding:11px 18px;border-radius:10px;cursor:pointer;font-size:.9rem}
.loading-spin{display:inline-block;width:18px;height:18px;border:2px solid #fff;border-top-color:transparent;border-radius:50%;animation:spin .7s linear infinite;vertical-align:middle;margin-right:6px}
@keyframes spin{to{transform:rotate(360deg)}}
</style>
</head>
<body>
{{ sidebar|safe }}
<div class="main-content">
<div class="lc-wrap">
    <div class="lc-header">
        <div>
            <a href="/user/casino" style="color:#a78bfa;font-size:.8rem;text-decoration:none">← Back to Casino</a>
            <h1 style="margin-top:6px">🎬 Live & Slot Games</h1>
        </div>
        <div class="lc-bal-box">
            <div><div class="lbl">Balance</div><div class="val" id="balVal">${{ balance }}</div></div>
        </div>
    </div>

    {% if not configured %}
    <div class="notice-box">
        ⚠️ <strong>Lucko.ai API not configured.</strong>
        Set <code>LUCKO_AGENT_ID</code> and <code>LUCKO_SECRET</code> to enable live games.
        <br><small>Admin: <a href="/admin/casino/live">Configure now →</a></small>
    </div>
    {% endif %}

    {% if not enabled %}
    <div class="notice-box">
        🔒 Live casino is currently <strong>disabled</strong> by the admin.
    </div>
    {% endif %}

    {% if configured and enabled %}
    <div class="filter-bar">
        <button class="fbt active" onclick="filterGames('')" id="fbt-all">All</button>
        <button class="fbt" onclick="filterGames('live')" id="fbt-live">🎬 Live</button>
        <button class="fbt" onclick="filterGames('slot')" id="fbt-slot">🎰 Slots</button>
        <button class="fbt" onclick="filterGames('table')" id="fbt-table">🃏 Table</button>
    </div>
    {% endif %}

    <div class="game-grid" id="gameGrid">
    {% if games %}
        {% for g in games %}
        <div class="lc-card" data-type="{{ g.game_type }}" onclick="openBuyIn('{{ g.game_id }}','{{ g.name|replace("'","") }}','{{ g.game_type }}')">
            <div class="lc-thumb">
                {% if g.thumbnail %}
                <img src="{{ g.thumbnail }}" alt="{{ g.name }}" loading="lazy" onerror="this.style.display='none'">
                {% else %}
                {{ g.icon }}
                {% endif %}
                <div class="lc-type-badge">{{ g.type_label }}</div>
            </div>
            <div class="lc-card-body">
                <div class="lc-game-name" title="{{ g.name }}">{{ g.name }}</div>
                <div class="lc-provider">{{ g.provider or 'Lucko.ai' }}</div>
                <button class="lc-play-btn" onclick="event.stopPropagation();openBuyIn('{{ g.game_id }}','{{ g.name|replace("'","") }}','{{ g.game_type }}')">Play Now</button>
            </div>
        </div>
        {% endfor %}
    {% elif configured and enabled %}
        <div class="empty-state" style="grid-column:1/-1">
            <div class="ei">🎰</div>
            <p>No games available right now.<br>
            <small><a href="/admin/casino/live" style="color:#a78bfa">Refresh game list →</a></small></p>
        </div>
    {% else %}
        <div class="empty-state" style="grid-column:1/-1">
            <div class="ei">🎬</div>
            <p style="color:#6b7280">Live games will appear here once the API is configured.</p>
        </div>
    {% endif %}
    </div>
</div>
</div>

<!-- Buy-in modal -->
<div class="modal-overlay" id="buyinModal" style="display:none" onclick="if(event.target===this)closeBuyIn()">
    <div class="modal-box">
        <h3 id="modalGameName">🎰 Game</h3>
        <div class="sub">Transfer credits to your Lucko wallet to play.</div>
        <div class="modal-row">
            <label>Balance</label>
            <span id="modalBal" style="color:#4ade80;font-weight:600"></span>
        </div>
        <div class="modal-row">
            <label>Buy-in</label>
            <input class="modal-inp" type="number" id="buyinAmt" min="{{ min_buyin }}" max="{{ max_buyin }}" step="1" value="{{ default_buyin }}">
        </div>
        <div class="quick-btns">
            <button class="qb" onclick="setAmt({{ default_buyin }})">${{ default_buyin }}</button>
            <button class="qb" onclick="setAmt({{ default_buyin * 2 }})">${{ (default_buyin * 2)|int }}</button>
            <button class="qb" onclick="setAmt({{ default_buyin * 5 }})">${{ (default_buyin * 5)|int }}</button>
            <button class="qb" onclick="setAmt(parseFloat(document.getElementById('balVal').textContent.replace('$','')))">All In</button>
        </div>
        <div class="modal-actions">
            <button class="btn-cancel" onclick="closeBuyIn()">Cancel</button>
            <button class="btn-confirm" id="confirmBtn" onclick="confirmBuyIn()">🎮 Play!</button>
        </div>
    </div>
</div>

<script>
var _gameId='', _gameName='', _gameType='';
function openBuyIn(id, name, type){
    _gameId=id; _gameName=name; _gameType=type;
    document.getElementById('modalGameName').textContent='🎮 '+name;
    document.getElementById('modalBal').textContent=document.getElementById('balVal').textContent;
    document.getElementById('buyinModal').style.display='flex';
}
function closeBuyIn(){ document.getElementById('buyinModal').style.display='none'; }
function setAmt(v){ document.getElementById('buyinAmt').value=parseFloat(v).toFixed(2); }
function confirmBuyIn(){
    var amt=parseFloat(document.getElementById('buyinAmt').value)||0;
    if(amt<=0){alert('Enter a buy-in amount');return;}
    var btn=document.getElementById('confirmBtn');
    btn.disabled=true;
    btn.innerHTML='<span class="loading-spin"></span>Loading…';
    fetch('/api/casino/live/play',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({game_id:_gameId,game_name:_gameName,game_type:_gameType,buyin:amt})
    }).then(r=>r.json()).then(d=>{
        if(d.ok){
            window.location.href='/user/casino/live/play/'+_gameId+'?order='+d.order_id;
        } else {
            alert('Error: '+(d.error||'Unknown error'));
            btn.disabled=false; btn.innerHTML='🎮 Play!';
        }
    }).catch(()=>{alert('Network error');btn.disabled=false;btn.innerHTML='🎮 Play!';});
}
function filterGames(type){
    document.querySelectorAll('.fbt').forEach(b=>b.classList.remove('active'));
    var id=type?'fbt-'+type:'fbt-all';
    var el=document.getElementById(id);
    if(el) el.classList.add('active');
    document.querySelectorAll('.lc-card').forEach(c=>{
        c.style.display=(!type||c.dataset.type===type)?'':'none';
    });
}
</script>
</body>
</html>'''


_PLAY_HTML = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{{ game_name }} — Onichan Live</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0d0d1a;color:#e0d7ff;font-family:system-ui,sans-serif;height:100vh;display:flex;flex-direction:column}
.ctrl-bar{background:rgba(13,13,26,.95);border-bottom:1px solid rgba(168,85,247,.3);padding:10px 16px;display:flex;align-items:center;gap:12px;z-index:100;flex-shrink:0}
.ctrl-bar .gname{font-weight:700;color:#e0d7ff;flex:1;font-size:.9rem;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ctrl-bar .bal-chip{background:rgba(74,222,128,.15);border:1px solid rgba(74,222,128,.3);color:#4ade80;padding:4px 12px;border-radius:20px;font-size:.8rem;font-weight:600;white-space:nowrap}
.btn-exit{background:linear-gradient(135deg,#7c3aed,#a21caf);color:#fff;border:none;padding:8px 16px;border-radius:8px;font-size:.8rem;font-weight:700;cursor:pointer;white-space:nowrap}
.btn-exit:hover{opacity:.85}
.game-frame{flex:1;position:relative}
.game-frame iframe{width:100%;height:100%;border:none;display:block}
.no-url{display:flex;align-items:center;justify-content:center;flex:1;flex-direction:column;gap:12px;color:#9ca3af;text-align:center;padding:20px}
.no-url .ei{font-size:3rem}
.cashout-overlay{position:fixed;inset:0;background:rgba(0,0,0,.85);z-index:9999;display:none;align-items:center;justify-content:center}
.cashout-box{background:#1a1a2e;border:1px solid rgba(74,222,128,.4);border-radius:18px;padding:32px;max-width:340px;width:100%;text-align:center}
.cashout-box h3{color:#4ade80;margin-bottom:8px;font-size:1.3rem}
.cashout-box .amt{font-size:2rem;font-weight:800;color:#e0d7ff;margin:12px 0}
.cashout-box .meta{color:#9ca3af;font-size:.8rem;margin-bottom:20px}
.cashout-box .btn-done{background:linear-gradient(135deg,#7c3aed,#a21caf);color:#fff;border:none;padding:12px 32px;border-radius:10px;font-weight:700;cursor:pointer;font-size:1rem}
.loading-spin{display:inline-block;width:20px;height:20px;border:2px solid #a78bfa;border-top-color:transparent;border-radius:50%;animation:spin .7s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
</style>
</head>
<body>
<div class="ctrl-bar">
    <a href="/user/casino/live" style="color:#a78bfa;font-size:1.2rem;text-decoration:none" title="Back">←</a>
    <div class="gname">{{ game_name }}</div>
    <div class="bal-chip" id="luckoBalChip">
        <span id="luckoBal">{{ lucko_balance|round(2) }}</span> credits
    </div>
    <button class="btn-exit" id="exitBtn" onclick="doExit()">💸 Cash Out & Exit</button>
</div>

<div class="game-frame">
{% if game_url %}
    <iframe id="gameIframe" src="{{ game_url }}" allow="fullscreen" allowfullscreen></iframe>
{% else %}
    <div class="no-url">
        <div class="ei">⚠️</div>
        <p>Could not load game.<br><small style="color:#ef4444">{{ error }}</small></p>
        <a href="/user/casino/live" style="color:#a78bfa;margin-top:12px">← Back to lobby</a>
    </div>
{% endif %}
</div>

<!-- Cashout result overlay -->
<div class="cashout-overlay" id="cashoutOverlay">
    <div class="cashout-box">
        <h3 id="coTitle">💸 Cashing Out…</h3>
        <div class="amt" id="coAmt"><span class="loading-spin"></span></div>
        <div class="meta" id="coMeta"></div>
        <button class="btn-done" id="coDone" style="display:none" onclick="window.location='/user/casino/live'">← Back to Lobby</button>
    </div>
</div>

<script>
var _exiting=false;
var _gameId='{{ game_id }}';

function doExit(){
    if(_exiting) return;
    _exiting=true;
    document.getElementById('exitBtn').disabled=true;
    document.getElementById('cashoutOverlay').style.display='flex';
    fetch('/api/casino/live/cashout',{method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({game_id:_gameId})
    }).then(r=>r.json()).then(d=>{
        if(d.ok){
            document.getElementById('coTitle').textContent='✅ Cashed Out!';
            document.getElementById('coAmt').textContent='$'+d.credits_back.toFixed(2);
            var meta='';
            if(d.commission>0) meta='Commission: $'+d.commission.toFixed(2)+' ('+d.commission_pct+'%)';
            document.getElementById('coMeta').textContent=meta;
        } else {
            document.getElementById('coTitle').textContent='⚠️ Cashout Issue';
            document.getElementById('coAmt').textContent='—';
            document.getElementById('coMeta').textContent=d.error||'Please contact support.';
        }
        document.getElementById('coDone').style.display='';
    }).catch(()=>{
        document.getElementById('coTitle').textContent='⚠️ Network Error';
        document.getElementById('coAmt').textContent='—';
        document.getElementById('coMeta').textContent='Please try again or contact support.';
        document.getElementById('coDone').style.display='';
    });
}

// Warn on accidental close without cashing out
window.addEventListener('beforeunload', function(e){
    if(!_exiting){
        e.preventDefault();
        e.returnValue='Cash out before leaving to collect your winnings!';
    }
});
</script>
</body>
</html>'''


_ADMIN_HTML = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Lucko.ai Settings — Admin</title>
{{ admin_css|safe }}
<style>
.section{background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.1);border-radius:12px;padding:20px;margin-bottom:20px}
.section h3{margin:0 0 16px;color:#e0d7ff;font-size:1rem}
.status-badge{display:inline-flex;align-items:center;gap:6px;padding:4px 12px;border-radius:20px;font-size:.78rem;font-weight:600}
.badge-ok{background:rgba(74,222,128,.2);color:#4ade80;border:1px solid rgba(74,222,128,.3)}
.badge-warn{background:rgba(251,191,36,.2);color:#fbbf24;border:1px solid rgba(251,191,36,.3)}
.badge-err{background:rgba(239,68,68,.2);color:#ef4444;border:1px solid rgba(239,68,68,.3)}
.inp{background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.2);color:#e0d7ff;padding:8px 12px;border-radius:8px;width:100%;font-size:.875rem}
.inp-sm{width:120px}
.form-row{display:flex;gap:12px;align-items:center;margin-bottom:12px;flex-wrap:wrap}
.form-row label{color:#a78bfa;font-size:.8rem;min-width:160px}
.msg{padding:10px 16px;border-radius:8px;margin-bottom:16px;font-size:.875rem}
.msg-ok{background:rgba(74,222,128,.15);color:#4ade80;border:1px solid rgba(74,222,128,.3)}
.msg-err{background:rgba(239,68,68,.15);color:#f87171;border:1px solid rgba(239,68,68,.3)}
.table-wrap{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:.8rem}
th,td{padding:8px 12px;text-align:left;border-bottom:1px solid rgba(255,255,255,.06)}
th{color:#a78bfa;font-weight:600}
.tag{padding:2px 8px;border-radius:12px;font-size:.7rem;font-weight:600}
.tag-in{background:rgba(74,222,128,.2);color:#4ade80}
.tag-out{background:rgba(239,68,68,.2);color:#ef4444}
.tag-ok{background:rgba(74,222,128,.2);color:#4ade80}
.tag-fail{background:rgba(239,68,68,.2);color:#ef4444}
.tag-pend{background:rgba(251,191,36,.2);color:#fbbf24}
.game-row{display:flex;align-items:center;gap:10px;padding:8px 0;border-bottom:1px solid rgba(255,255,255,.05)}
.game-row label{flex:1;color:#d1d5db;font-size:.85rem}
.toggle{position:relative;display:inline-block;width:42px;height:22px}
.toggle input{opacity:0;width:0;height:0}
.toggle .slider{position:absolute;inset:0;background:#374151;border-radius:11px;cursor:pointer;transition:.3s}
.toggle input:checked+.slider{background:#7c3aed}
.toggle .slider:before{content:"";position:absolute;width:16px;height:16px;left:3px;bottom:3px;background:#fff;border-radius:50%;transition:.3s}
.toggle input:checked+.slider:before{transform:translateX(20px)}
</style>
</head>
<body>
<div style="max-width:900px;margin:0 auto;padding:20px">
    <div style="display:flex;align-items:center;gap:12px;margin-bottom:20px;flex-wrap:wrap">
        <a href="/admin/casino" style="color:#a78bfa;text-decoration:none">← Casino Admin</a>
        <h2 style="margin:0;color:#e0d7ff;flex:1">🎬 Lucko.ai Live Casino</h2>
        <span class="status-badge {{ status_class }}">{{ status_text }}</span>
    </div>

    {% if message %}
    <div class="msg {% if msg_ok %}msg-ok{% else %}msg-err{% endif %}">{{ message }}</div>
    {% endif %}

    <!-- Enable/disable + global commission -->
    <div class="section">
        <h3>Global Settings</h3>
        <form method="POST">
        <input type="hidden" name="action" value="save_global">
        <div class="form-row">
            <label>Live Casino Enabled</label>
            <label class="toggle">
                <input type="checkbox" name="enabled" {% if lucko_enabled %}checked{% endif %}>
                <span class="slider"></span>
            </label>
        </div>
        <div class="form-row">
            <label>Default Commission %</label>
            <input class="inp inp-sm" type="number" name="default_commission_pct" value="{{ commission_pct }}" min="0" max="20" step="0.1">
            <small style="color:#6b7280">Applied on cashout (0 = no commission)</small>
        </div>
        <div class="form-row">
            <label>Default Buy-in ($)</label>
            <input class="inp inp-sm" type="number" name="default_buyin" value="{{ default_buyin }}" min="1" step="1">
        </div>
        <div class="form-row">
            <label>Min Buy-in ($)</label>
            <input class="inp inp-sm" type="number" name="min_buyin" value="{{ min_buyin }}" min="0.01" step="0.01">
        </div>
        <div class="form-row">
            <label>Max Buy-in ($)</label>
            <input class="inp inp-sm" type="number" name="max_buyin" value="{{ max_buyin }}" min="1" step="1">
        </div>
        <button type="submit" class="btn btn-primary">Save Settings</button>
        </form>
    </div>

    <!-- API credentials status -->
    <div class="section">
        <h3>API Configuration</h3>
        {% if configured %}
        <div style="color:#4ade80;margin-bottom:12px">✅ LUCKO_AGENT_ID and LUCKO_SECRET are set.</div>
        {% else %}
        <div style="color:#f87171;margin-bottom:12px">
            ❌ API credentials not set. Set <code>LUCKO_AGENT_ID</code> and <code>LUCKO_SECRET</code>
            as Replit Secrets to activate live games.
        </div>
        {% endif %}
        <div style="display:flex;gap:10px;flex-wrap:wrap">
            <form method="POST">
                <input type="hidden" name="action" value="ping_api">
                <button type="submit" class="btn btn-purple">🔗 Test API Connection</button>
            </form>
            <form method="POST">
                <input type="hidden" name="action" value="refresh_games">
                <button type="submit" class="btn btn-purple">🔄 Refresh Game List</button>
            </form>
        </div>
        {% if ping_result %}
        <div style="margin-top:12px;padding:10px;background:rgba(255,255,255,.04);border-radius:8px;font-size:.8rem;color:#9ca3af">
            API response: {{ ping_result }}
        </div>
        {% endif %}
    </div>

    <!-- Game list + per-game settings -->
    {% if games %}
    <div class="section">
        <h3>Game Settings ({{ games|length }} games)</h3>
        <form method="POST">
        <input type="hidden" name="action" value="save_games">
        <div style="max-height:400px;overflow-y:auto">
        {% for g in games %}
        <div class="game-row">
            <label>{{ g.icon }} {{ g.name }} <span style="color:#6b7280;font-size:.7rem">({{ g.game_type }})</span></label>
            <label class="toggle" title="Enable/disable this game">
                <input type="checkbox" name="game_enabled_{{ g.game_id }}" {% if g.enabled %}checked{% endif %}>
                <span class="slider"></span>
            </label>
            <input type="number" class="inp" style="width:80px" name="game_commission_{{ g.game_id }}"
                value="{{ g.commission_pct }}" min="0" max="20" step="0.1" title="Commission %"
                placeholder="Commission%">
            <span style="color:#6b7280;font-size:.7rem">%</span>
        </div>
        {% endfor %}
        </div>
        <button type="submit" class="btn btn-primary" style="margin-top:16px">Save Game Settings</button>
        </form>
    </div>
    {% endif %}

    <!-- Credits & sweep -->
    <div class="section">
        <h3>Wallet Overview</h3>
        <div style="display:flex;gap:20px;flex-wrap:wrap;margin-bottom:16px">
            <div>
                <div style="color:#a78bfa;font-size:.7rem;text-transform:uppercase">Members Registered</div>
                <div style="font-size:1.5rem;font-weight:700;color:#e0d7ff">{{ member_count }}</div>
            </div>
            <div>
                <div style="color:#a78bfa;font-size:.7rem;text-transform:uppercase">Total Transfers In</div>
                <div style="font-size:1.5rem;font-weight:700;color:#e0d7ff">${{ total_in }}</div>
            </div>
            <div>
                <div style="color:#a78bfa;font-size:.7rem;text-transform:uppercase">Total Commission Earned</div>
                <div style="font-size:1.5rem;font-weight:700;color:#4ade80">${{ total_commission }}</div>
            </div>
        </div>
        <form method="POST" onsubmit="return confirm('Force-cashout ALL members now? This cannot be undone.')">
            <input type="hidden" name="action" value="sweep_all">
            <button type="submit" class="btn btn-red">⚡ Emergency Sweep All Wallets</button>
        </form>
    </div>

    <!-- Recent transfer log -->
    <div class="section">
        <h3>Recent Transfers (last 50)</h3>
        {% if transfers %}
        <div class="table-wrap">
        <table>
            <tr><th>Time</th><th>User</th><th>Direction</th><th>Credits</th><th>Commission</th><th>Status</th></tr>
            {% for t in transfers %}
            <tr>
                <td style="color:#6b7280">{{ t.created_at.strftime('%m/%d %H:%M') if t.created_at else '' }}</td>
                <td>{{ t.telegram_id }}</td>
                <td><span class="tag {% if t.direction=='in' %}tag-in{% else %}tag-out{% endif %}">{{ t.direction }}</span></td>
                <td>${{ '%.2f'|format(t.credits_lucko|float) }}</td>
                <td style="color:#fbbf24">${{ '%.2f'|format(t.commission_amount|float) }}</td>
                <td><span class="tag {% if t.status=='completed' %}tag-ok{% elif t.status=='failed' %}tag-fail{% else %}tag-pend{% endif %}">{{ t.status }}</span></td>
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
</html>'''


def register_lucko_routes(app, user_required, owner_required, get_user_sidebar, USER_CSS, ADMIN_CSS):
    """Register all Lucko.ai routes on the Flask app."""

    # ── Cached game list ──────────────────────────────────────────────────────
    _game_cache = {'games': [], 'fetched_at': 0}
    _CACHE_TTL = 3600

    def _get_cached_games():
        now = time.time()
        if _game_cache['games'] and (now - _game_cache['fetched_at']) < _CACHE_TTL:
            return _game_cache['games']
        return _refresh_games()

    def _refresh_games():
        res = _api.get_game_list()
        if res.get('code') == 0:
            raw = res.get('data') or []
            if isinstance(raw, dict):
                raw = raw.get('list') or raw.get('games') or []
            games = []
            for g in raw:
                gid = g.get('game_id') or g.get('id') or ''
                if not gid:
                    continue
                gtype = (g.get('game_type') or g.get('type') or 'slot').lower()
                games.append({
                    'game_id': str(gid),
                    'name': g.get('name') or g.get('game_name') or str(gid),
                    'game_type': gtype,
                    'type_label': _GAME_TYPE_LABELS.get(gtype, gtype.title()),
                    'icon': _GAME_TYPE_ICONS.get(gtype, '🎮'),
                    'thumbnail': g.get('thumbnail') or g.get('img') or g.get('image') or '',
                    'provider': g.get('provider') or g.get('platform') or '',
                    'enabled': _wallet.is_game_enabled(str(gid)),
                    'commission_pct': _wallet.get_commission_pct(str(gid)),
                })
            _game_cache['games'] = games
            _game_cache['fetched_at'] = time.time()
            return games
        return _game_cache['games']

    # ── User lobby ────────────────────────────────────────────────────────────

    @app.route('/user/casino/live')
    @user_required
    def user_casino_live():
        from modules.cc_shop import get_user_balance
        user_id = session.get('user_id')
        balance = get_user_balance(user_id)
        configured = _api.is_configured()
        enabled = _wallet.is_enabled()

        games = []
        if configured and enabled:
            all_games = _get_cached_games()
            games = [g for g in all_games if g['enabled']]

        return render_template_string(
            _LOBBY_HTML,
            sidebar=get_user_sidebar('casino', '🎬 Live Casino'),
            user_css=USER_CSS,
            balance=f"{balance:.2f}",
            configured=configured,
            enabled=enabled,
            games=games,
            min_buyin=float(_wallet.get_lucko_setting('min_buyin', '1.00')),
            max_buyin=float(_wallet.get_lucko_setting('max_buyin', '500.00')),
            default_buyin=float(_wallet.get_lucko_setting('default_buyin', '10.00')),
        )

    # ── Play initiation API ───────────────────────────────────────────────────

    @app.route('/api/casino/live/play', methods=['POST'])
    @user_required
    def api_lucko_play():
        user_id = session.get('user_id')
        data = request.get_json(silent=True) or {}
        game_id = str(data.get('game_id', ''))
        buyin = float(data.get('buyin') or _wallet.get_lucko_setting('default_buyin', '10'))

        if not game_id:
            return jsonify({'ok': False, 'error': 'Missing game_id'})
        if not _api.is_configured():
            return jsonify({'ok': False, 'error': 'Lucko API not configured'})
        if not _wallet.is_enabled():
            return jsonify({'ok': False, 'error': 'Live casino is disabled'})

        res = _wallet.buy_in(user_id, buyin, game_id)
        if not res['ok']:
            return jsonify(res)

        # Store game context in session so the play page can retrieve the URL
        session[f'lucko_order_{res["order_id"]}'] = {
            'game_id': game_id,
            'game_name': data.get('game_name', game_id),
            'lucko_balance': res['lucko_balance'],
        }
        return jsonify({'ok': True, 'order_id': res['order_id']})

    # ── Game iframe page ──────────────────────────────────────────────────────

    @app.route('/user/casino/live/play/<game_id>')
    @user_required
    def user_lucko_game(game_id):
        user_id = session.get('user_id')
        order_id = request.args.get('order', '')
        ctx = session.get(f'lucko_order_{order_id}', {})
        game_name = ctx.get('game_name') or game_id
        lucko_balance = ctx.get('lucko_balance', 0)

        game_url = ''
        error = ''
        if _api.is_configured():
            return_url = request.url_root.rstrip('/') + '/user/casino/live'
            res = _wallet.get_game_url(user_id, game_id, return_url=return_url)
            if res.get('ok'):
                game_url = res['url']
            else:
                error = res.get('error', 'Could not get game URL')
        else:
            error = 'Lucko API not configured'

        return render_template_string(
            _PLAY_HTML,
            game_id=game_id,
            game_name=game_name,
            game_url=game_url,
            lucko_balance=lucko_balance,
            error=error,
        )

    # ── Cashout API ───────────────────────────────────────────────────────────

    @app.route('/api/casino/live/cashout', methods=['POST'])
    @user_required
    def api_lucko_cashout():
        user_id = session.get('user_id')
        data = request.get_json(silent=True) or {}
        game_id = str(data.get('game_id', ''))
        result = _wallet.cash_out(user_id, game_id)
        return jsonify(result)

    # ── Balance API ───────────────────────────────────────────────────────────

    @app.route('/api/casino/live/balance')
    @user_required
    def api_lucko_balance():
        user_id = session.get('user_id')
        lucko_id = _wallet.ensure_member(user_id)
        bal = _api.get_member_balance(lucko_id) if lucko_id else None
        return jsonify({'lucko_balance': bal})

    # ── Webhook ───────────────────────────────────────────────────────────────

    @app.route('/webhook/lucko/notify', methods=['POST'])
    def webhook_lucko():
        """Lucko.ai bet/payout notification webhook."""
        data = request.get_json(silent=True) or {}
        # Log and acknowledge — full processing can be added per Lucko docs
        return jsonify({'code': 0, 'msg': 'ok'})

    # ── Admin panel ───────────────────────────────────────────────────────────

    @app.route('/admin/casino/live', methods=['GET', 'POST'])
    @owner_required
    def admin_casino_live():
        from modules.database import _execute_with_retry as _q

        message = ''
        msg_ok = True
        ping_result = None

        if request.method == 'POST':
            action = request.form.get('action', '')

            if action == 'save_global':
                _wallet.set_lucko_setting('enabled', 'true' if request.form.get('enabled') else 'false')
                _wallet.set_lucko_setting('default_commission_pct', request.form.get('default_commission_pct', '5'))
                _wallet.set_lucko_setting('default_buyin', request.form.get('default_buyin', '10'))
                _wallet.set_lucko_setting('min_buyin', request.form.get('min_buyin', '1'))
                _wallet.set_lucko_setting('max_buyin', request.form.get('max_buyin', '500'))
                message = '✅ Settings saved!'

            elif action == 'ping_api':
                res = _api.ping()
                ping_result = json.dumps(res)
                msg_ok = res.get('code') == 0
                message = 'API ping sent — see response below.'

            elif action == 'refresh_games':
                games = _refresh_games()
                message = f'✅ Refreshed game list — {len(games)} games loaded.'

            elif action == 'save_games':
                all_games = _get_cached_games()
                for g in all_games:
                    gid = g['game_id']
                    enabled = bool(request.form.get(f'game_enabled_{gid}'))
                    try:
                        comm = float(request.form.get(f'game_commission_{gid}', _wallet.get_lucko_setting('default_commission_pct', '5')))
                    except (ValueError, TypeError):
                        comm = 5.0
                    _wallet.set_game_setting(gid, 'enabled', enabled)
                    _wallet.set_game_setting(gid, 'commission_pct', comm)
                message = '✅ Game settings saved!'

            elif action == 'sweep_all':
                result = _wallet.sweep_all_members()
                message = f"✅ Swept {result['swept']} wallets, ${result['total_back']:.2f} returned. Errors: {result['errors']}"
                msg_ok = result['errors'] == 0

        # Stats
        member_count = (_q("SELECT COUNT(*) as c FROM lucko_members", fetch_one=True) or {}).get('c', 0)
        total_in_row = _q("SELECT COALESCE(SUM(credits_lucko),0) as s FROM lucko_transfers WHERE direction='in' AND status='completed'", fetch_one=True) or {}
        total_comm_row = _q("SELECT COALESCE(SUM(commission_amount),0) as s FROM lucko_transfers WHERE direction='out' AND status='completed'", fetch_one=True) or {}

        games = _get_cached_games()
        transfers = _wallet.get_recent_transfers(50)
        configured = _api.is_configured()
        lucko_enabled = _wallet.is_enabled()

        if configured:
            status_class = 'badge-ok'
            status_text = '✅ API Connected'
        else:
            status_class = 'badge-err'
            status_text = '❌ Not Configured'

        return render_template_string(
            _ADMIN_HTML,
            admin_css=ADMIN_CSS,
            message=message,
            msg_ok=msg_ok,
            configured=configured,
            lucko_enabled=lucko_enabled,
            commission_pct=float(_wallet.get_lucko_setting('default_commission_pct', '5')),
            default_buyin=float(_wallet.get_lucko_setting('default_buyin', '10')),
            min_buyin=float(_wallet.get_lucko_setting('min_buyin', '1')),
            max_buyin=float(_wallet.get_lucko_setting('max_buyin', '500')),
            games=games,
            transfers=transfers,
            status_class=status_class,
            status_text=status_text,
            ping_result=ping_result,
            member_count=member_count,
            total_in=f"{float(total_in_row.get('s', 0)):.2f}",
            total_commission=f"{float(total_comm_row.get('s', 0)):.2f}",
        )
