import { Router } from "express";

const router = Router();

const FLASK_BASE = "http://localhost:5000";

router.post("/extension/validate_key", async (req, res) => {
  try {
    const resp = await fetch(`${FLASK_BASE}/api/extension/validate_key`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req.body),
      signal: AbortSignal.timeout(8000),
    });
    const data = await resp.json();
    res.setHeader("Access-Control-Allow-Origin", "*");
    res.status(resp.ok ? 200 : resp.status).json(data);
  } catch (err: any) {
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
