const ONICHAN_API_BASE = "https://6cb67840-8f90-4a25-8429-c01871a517a5-00-ahul1e8n76y8.riker.replit.dev";
const KEY_STORAGE_KEY = "onichan_ext_key";
const KEY_CACHE_TTL = 24 * 60 * 60 * 1000;

async function getStoredKey() {
  return new Promise(resolve => {
    chrome.storage.local.get([KEY_STORAGE_KEY, "onichan_key_ts", "onichan_api_url"], result => {
      resolve({
        key: result[KEY_STORAGE_KEY] || null,
        ts: result["onichan_key_ts"] || 0,
        apiUrl: result["onichan_api_url"] || ONICHAN_API_BASE
      });
    });
  });
}

async function saveKey(key, apiUrl) {
  return new Promise(resolve => {
    chrome.storage.local.set({
      [KEY_STORAGE_KEY]: key,
      "onichan_key_ts": Date.now(),
      "onichan_api_url": apiUrl || ONICHAN_API_BASE
    }, resolve);
  });
}

async function clearKey() {
  return new Promise(resolve => {
    chrome.storage.local.remove([KEY_STORAGE_KEY, "onichan_key_ts"], resolve);
  });
}

async function validateKeyRemote(key, apiUrl) {
  try {
    const base = (apiUrl || ONICHAN_API_BASE).replace(/\/$/, "");
    const res = await fetch(`${base}/api/extension/validate_key`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key })
    });
    if (!res.ok) return false;
    const data = await res.json();
    return data.valid === true;
  } catch {
    return null;
  }
}

function showLockScreen() {
  document.getElementById("lockScreen").style.display = "flex";
  document.getElementById("mainApp").style.display = "none";
}

function showMainApp() {
  document.getElementById("lockScreen").style.display = "none";
  document.getElementById("mainApp").style.display = "flex";
}

function setAuthStatus(msg, type) {
  const el = document.getElementById("authStatus");
  if (!el) return;
  el.textContent = msg;
  el.className = "auth-status " + (type || "");
  el.style.display = msg ? "block" : "none";
}

function setAuthLoading(loading) {
  const btn = document.getElementById("authSubmitBtn");
  const input = document.getElementById("authKeyInput");
  if (btn) {
    btn.disabled = loading;
    btn.textContent = loading ? "Verifying…" : "Unlock";
  }
  if (input) input.disabled = loading;
}

async function handleAuthSubmit() {
  const keyInput = document.getElementById("authKeyInput");
  const apiInput = document.getElementById("authApiInput");
  const key = (keyInput?.value || "").trim();
  const apiUrl = (apiInput?.value || "").trim() || ONICHAN_API_BASE;

  if (!key) {
    setAuthStatus("Please enter your Onichan Bot key.", "error");
    return;
  }

  setAuthLoading(true);
  setAuthStatus("Connecting to Onichan Bot…", "info");

  const valid = await validateKeyRemote(key, apiUrl);

  if (valid === true) {
    await saveKey(key, apiUrl);
    setAuthStatus("✅ Key verified! Loading…", "success");
    setTimeout(() => showMainApp(), 600);
  } else if (valid === false) {
    setAuthStatus("❌ Invalid or expired key. Get a new one with /extkey in the bot.", "error");
    setAuthLoading(false);
  } else {
    setAuthStatus("⚠️ Could not reach Onichan server. Check the API URL or try again.", "warn");
    setAuthLoading(false);
  }
}

async function initAuth() {
  const { key, ts, apiUrl } = await getStoredKey();

  const apiInput = document.getElementById("authApiInput");
  if (apiInput && apiUrl) apiInput.value = apiUrl;

  if (!key) {
    showLockScreen();
    return;
  }

  const age = Date.now() - ts;
  if (age < KEY_CACHE_TTL) {
    showMainApp();
    return;
  }

  setAuthStatus("Re-verifying key…", "info");
  const valid = await validateKeyRemote(key, apiUrl);
  if (valid === true) {
    await saveKey(key, apiUrl);
    showMainApp();
  } else if (valid === false) {
    await clearKey();
    setAuthStatus("Key expired or revoked. Please re-enter your key.", "error");
    showLockScreen();
  } else {
    showMainApp();
  }
}

document.addEventListener("DOMContentLoaded", () => {
  initAuth();

  document.getElementById("authSubmitBtn")?.addEventListener("click", handleAuthSubmit);

  document.getElementById("authKeyInput")?.addEventListener("keydown", e => {
    if (e.key === "Enter") handleAuthSubmit();
  });

  document.getElementById("authLogoutBtn")?.addEventListener("click", async () => {
    await clearKey();
    showLockScreen();
    setAuthStatus("", "");
    const keyInput = document.getElementById("authKeyInput");
    if (keyInput) keyInput.value = "";
  });

  document.getElementById("authApiToggle")?.addEventListener("click", () => {
    const row = document.getElementById("authApiRow");
    if (row) row.style.display = row.style.display === "none" ? "flex" : "none";
  });
});
