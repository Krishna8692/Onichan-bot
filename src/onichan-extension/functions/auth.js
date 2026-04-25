const ONICHAN_API_BASE = "https://6cb67840-8f90-4a25-8429-c01871a517a5-00-ahul1e8n76y8.riker.replit.dev";
const KEY_STORAGE_KEY  = "onichan_ext_key";
const EXPIRY_STORAGE   = "onichan_key_expires_ts";
const API_URL_STORAGE  = "onichan_api_url";
const PREMIUM_STORAGE  = "onichan_is_premium";

async function getStored() {
  return new Promise(resolve => {
    chrome.storage.local.get(
      [KEY_STORAGE_KEY, EXPIRY_STORAGE, API_URL_STORAGE, PREMIUM_STORAGE],
      r => resolve({
        key:       r[KEY_STORAGE_KEY]  || null,
        expiresTs: r[EXPIRY_STORAGE]   || 0,
        apiUrl:    r[API_URL_STORAGE]  || ONICHAN_API_BASE,
        isPremium: r[PREMIUM_STORAGE]  || false
      })
    );
  });
}

async function storeAuth(key, data, apiUrl) {
  return new Promise(resolve => {
    chrome.storage.local.set({
      [KEY_STORAGE_KEY]: key,
      [EXPIRY_STORAGE]:  data.expires_ts || (Date.now() + 30 * 24 * 60 * 60 * 1000),
      [API_URL_STORAGE]: apiUrl || ONICHAN_API_BASE,
      [PREMIUM_STORAGE]: data.is_premium || false
    }, resolve);
  });
}

async function clearAuth() {
  return new Promise(resolve => {
    chrome.storage.local.remove(
      [KEY_STORAGE_KEY, EXPIRY_STORAGE, PREMIUM_STORAGE],
      resolve
    );
  });
}

async function validateKeyRemote(key, apiUrl) {
  try {
    const base = (apiUrl || ONICHAN_API_BASE).replace(/\/$/, "");
    const res = await fetch(`${base}/api/extension/validate_key`, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ key })
    });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

function showLock() {
  document.getElementById("landingPage").style.display = "flex";
  document.getElementById("mainApp").style.display = "none";
}

function showApp(isPremium) {
  document.getElementById("landingPage").style.display = "none";
  document.getElementById("mainApp").style.display   = "flex";
  const badge = document.getElementById("statusBadge");
  if (badge) {
    badge.textContent = isPremium ? "⭐ Premium" : "Free";
    badge.className   = isPremium ? "status-badge premium" : "status-badge";
  }
}

function setStatus(msg, type) {
  const el = document.getElementById("authStatus");
  if (!el) return;
  el.textContent = msg;
  el.className   = "auth-status " + (type || "");
  el.style.display = msg ? "block" : "none";
}

function setBtnState(loading) {
  const btn   = document.getElementById("authSubmitBtn");
  const input = document.getElementById("authKeyInput");
  if (btn)   { btn.disabled = loading; btn.innerHTML = loading
    ? '<span class="spinner"></span>Verifying…'
    : '<i class="fa-solid fa-unlock"></i>Unlock Extension'; }
  if (input) input.disabled = loading;
}

function formatExpiry(ts) {
  if (!ts) return "";
  const d = new Date(ts);
  return d.toLocaleDateString("en-US", { day:"numeric", month:"short", year:"numeric" });
}

async function doValidate() {
  const keyInput = document.getElementById("authKeyInput");
  const apiInput = document.getElementById("authApiInput");
  const key      = (keyInput?.value || "").trim();
  const apiUrl   = (apiInput?.value  || "").trim() || ONICHAN_API_BASE;

  if (!key) { setStatus("Please enter your Onichan Bot key.", "error"); return; }

  setBtnState(true);
  setStatus("Connecting to Onichan Bot…", "info");

  const data = await validateKeyRemote(key, apiUrl);

  if (data && data.valid === true) {
    await storeAuth(key, data, apiUrl);
    const expLabel = formatExpiry(data.expires_ts);
    setStatus(`✅ Unlocked${data.is_premium ? " ⭐ Premium" : ""}${expLabel ? " · Expires " + expLabel : ""}`, "success");
    setTimeout(() => showApp(data.is_premium), 700);
  } else if (data && data.valid === false) {
    setStatus("❌ Invalid or expired key. Get a new one with /extkey in the bot.", "error");
    setBtnState(false);
  } else {
    setStatus("⚠️ Could not reach Onichan server. Check API URL or try again.", "warn");
    setBtnState(false);
  }
}

async function initAuth() {
  const { key, expiresTs, apiUrl, isPremium } = await getStored();

  const apiInput = document.getElementById("authApiInput");
  if (apiInput && apiUrl !== ONICHAN_API_BASE) apiInput.value = apiUrl;

  if (!key) { showLock(); return; }

  if (Date.now() < expiresTs) {
    showApp(isPremium);
    return;
  }

  setStatus("Re-verifying session…", "info");
  const data = await validateKeyRemote(key, apiUrl);
  if (data && data.valid === true) {
    await storeAuth(key, data, apiUrl);
    showApp(data.is_premium);
  } else if (data && data.valid === false) {
    await clearAuth();
    setStatus("Key expired. Please enter your key again.", "error");
    showLock();
  } else {
    showApp(isPremium);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  initAuth();

  document.getElementById("authSubmitBtn")?.addEventListener("click", doValidate);
  document.getElementById("authKeyInput")?.addEventListener("keydown", e => {
    if (e.key === "Enter") doValidate();
  });

  document.getElementById("authLogoutBtn")?.addEventListener("click", async () => {
    await clearAuth();
    document.getElementById("authKeyInput").value = "";
    setStatus("", "");
    setBtnState(false);
    showLock();
  });

  document.getElementById("authApiToggle")?.addEventListener("click", () => {
    const row = document.getElementById("authApiRow");
    if (row) row.style.display = row.style.display === "none" ? "flex" : "none";
  });

  document.querySelectorAll(".sparkle").forEach((el, i) => {
    el.style.animationDelay = `${i * 0.4}s`;
    el.style.left = `${10 + Math.random() * 80}%`;
    el.style.top  = `${10 + Math.random() * 80}%`;
  });
});
