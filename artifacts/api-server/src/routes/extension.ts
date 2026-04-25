import { Router } from "express";
import { createReadStream, statSync, existsSync } from "fs";
import { resolve } from "path";

const router = Router();

const FLASK_BASE  = "http://localhost:5000";
const ZIP_PATH    = resolve("/home/runner/workspace/onichan-bypasser-extension.zip");
const ZIP_NAME    = "onichan-bypasser-extension.zip";

// ── Download extension ZIP ───────────────────────────────────────────────────
router.get("/extension/download", (_req, res) => {
  if (!existsSync(ZIP_PATH)) {
    res.status(404).json({ error: "Extension not built yet." });
    return;
  }
  const { size } = statSync(ZIP_PATH);
  res.setHeader("Content-Type", "application/zip");
  res.setHeader("Content-Disposition", `attachment; filename="${ZIP_NAME}"`);
  res.setHeader("Content-Length", size);
  res.setHeader("Cache-Control", "no-cache");
  createReadStream(ZIP_PATH).pipe(res);
});

// ── Validate key (proxy to Flask bot) ───────────────────────────────────────
router.post("/extension/validate_key", async (req, res) => {
  try {
    const resp = await fetch(`${FLASK_BASE}/api/extension/validate_key`, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify(req.body),
      signal:  AbortSignal.timeout(8000),
    });
    const data = await resp.json();
    res.setHeader("Access-Control-Allow-Origin", "*");
    res.status(resp.ok ? 200 : resp.status).json(data);
  } catch {
    res.setHeader("Access-Control-Allow-Origin", "*");
    res.status(503).json({ valid: false, error: "Bot server unavailable. Try again shortly." });
  }
});

router.options("/extension/validate_key", (_req, res) => {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "POST, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");
  res.sendStatus(204);
});

export default router;
