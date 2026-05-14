import { Router, type Request, type Response } from "express";

const casinoProxyRouter = Router();

const FLASK_BASE = "http://localhost:5000";

casinoProxyRouter.use(async (req: Request, res: Response) => {
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

    const contentType = response.headers.get("content-type") ?? "";
    if (contentType) {
      res.setHeader("Content-Type", contentType);
    }

    const isBinary =
      contentType.startsWith("image/") ||
      contentType.startsWith("audio/") ||
      contentType.startsWith("video/") ||
      contentType === "application/octet-stream" ||
      contentType.startsWith("application/pdf");

    if (isBinary) {
      const buf = await response.arrayBuffer();
      res.status(response.status).send(Buffer.from(buf));
    } else {
      const text = await response.text();
      res.status(response.status).send(text);
    }
  } catch {
    res.status(502).json({ error: "Casino service temporarily unavailable" });
  }
});

export default casinoProxyRouter;
