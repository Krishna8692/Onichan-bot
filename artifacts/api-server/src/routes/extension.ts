import { Router } from "express";
import { createReadStream, statSync, existsSync } from "fs";
import { resolve } from "path";

const router = Router();

const FLASK_BASE = "http://localhost:5000";
const ZIP_PATH   = resolve("/home/runner/workspace/onichan-bypasser-extension.zip");
const ZIP_NAME   = "onichan-bypasser-extension.zip";
const SRC_ZIP    = resolve("/home/runner/workspace/onichan-bypasser-extension-src.zip");
const SRC_NAME   = "onichan-bypasser-extension-src.zip";

const CORS = {
  "Access-Control-Allow-Origin":  "*",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

// ── Download built (obfuscated) ZIP ──────────────────────────────────────────
router.get("/extension/download", (_req, res) => {
  if (!existsSync(ZIP_PATH)) { res.status(404).json({ error: "Not built yet." }); return; }
  const { size } = statSync(ZIP_PATH);
  res.set({ "Content-Type": "application/zip", "Content-Disposition": `attachment; filename="${ZIP_NAME}"`, "Content-Length": size, "Cache-Control": "no-cache" });
  createReadStream(ZIP_PATH).pipe(res);
});

// ── Download source ZIP ───────────────────────────────────────────────────────
router.get("/extension/download/src", (_req, res) => {
  if (!existsSync(SRC_ZIP)) { res.status(404).json({ error: "Not found." }); return; }
  const { size } = statSync(SRC_ZIP);
  res.set({ "Content-Type": "application/zip", "Content-Disposition": `attachment; filename="${SRC_NAME}"`, "Content-Length": size, "Cache-Control": "no-cache" });
  createReadStream(SRC_ZIP).pipe(res);
});

// ── Internal helper: validate key via Flask ───────────────────────────────────
async function validateKey(key: string): Promise<Record<string, unknown>> {
  const resp = await fetch(`${FLASK_BASE}/api/extension/validate_key`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ key }),
    signal: AbortSignal.timeout(8000),
  });
  return await resp.json() as Record<string, unknown>;
}

// ── V1 compat: POST /api/bypasser/validate ────────────────────────────────────
// Onichan V1 popup.js / background.js call this endpoint.
// Our Flask returns: { valid, is_premium, expires_at, expires_ts }
// V1 expects:        { valid, key, tier, expires_at, days, error }
router.post("/bypasser/validate", async (req, res) => {
  res.set(CORS);
  const key = (req.body?.key || "").trim();
  if (!key) { res.status(400).json({ valid: false, error: "No key provided." }); return; }
  try {
    const data = await validateKey(key);
    if (!data.valid) {
      res.json({ valid: false, error: data.error || "Invalid or expired key." });
      return;
    }
    // Calculate days remaining
    const expiresAt = data.expires_at as string | null;
    const days = expiresAt
      ? Math.max(0, Math.floor((new Date(expiresAt).getTime() - Date.now()) / 86400000))
      : 0;
    res.json({
      valid: true,
      key,
      tier:       data.is_premium ? "PREMIUM" : "FREE",
      expires_at: expiresAt,
      days,
    });
  } catch {
    res.status(503).json({ valid: false, error: "Bot server unavailable. Try again." });
  }
});

router.options("/bypasser/validate", (_req, res) => { res.set(CORS).sendStatus(204); });

// ── Legacy validate_key route (old extension) ─────────────────────────────────
router.post("/extension/validate_key", async (req, res) => {
  res.set(CORS);
  try {
    const data = await validateKey((req.body?.key || "").trim());
    res.json(data);
  } catch {
    res.status(503).json({ valid: false, error: "Bot server unavailable." });
  }
});

router.options("/extension/validate_key", (_req, res) => { res.set(CORS).sendStatus(204); });

export default router;
