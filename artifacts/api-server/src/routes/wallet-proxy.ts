import { Router, type Request, type Response } from "express";

const walletProxyRouter = Router();

const FLASK_BASE = "http://localhost:5000";

walletProxyRouter.use(async (req: Request, res: Response) => {
  const targetUrl = `${FLASK_BASE}${req.originalUrl}`;

  try {
    const isJson = req.headers["content-type"]?.includes("application/json");
    const body =
      req.method !== "GET" && req.method !== "HEAD"
        ? isJson
          ? JSON.stringify(req.body)
          : new URLSearchParams(req.body as Record<string, string>).toString()
        : undefined;

    const headers: Record<string, string> = {
      "Content-Type": req.headers["content-type"] ?? "application/json",
    };
    if (req.headers.cookie) {
      headers["Cookie"] = req.headers.cookie;
    }

    const response = await fetch(targetUrl, {
      method: req.method,
      headers,
      body,
    });

    const setCookie = response.headers.get("set-cookie");
    if (setCookie) {
      res.setHeader("Set-Cookie", setCookie);
    }

    const contentType = response.headers.get("content-type");
    if (contentType) {
      res.setHeader("Content-Type", contentType);
    }

    const text = await response.text();
    res.status(response.status).send(text);
  } catch {
    res.status(502).json({ error: "Wallet service temporarily unavailable" });
  }
});

export default walletProxyRouter;
