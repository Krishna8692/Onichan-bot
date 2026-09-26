/**
 * flask-proxy.ts
 *
 * Forwards any Express request that wasn't handled by a local route to the
 * Flask/Werkzeug bot server running on FLASK_PORT (default 3000).
 *
 * This is needed because the api-server artifact owns the /api path prefix in
 * Replit's router, so ALL /api/* requests land here first. Local routes (e.g.
 * /api/healthz) are handled normally; everything else is proxied straight
 * through to Flask so the bot's wallet/admin/user APIs remain reachable.
 *
 * Body handling: a rawBody capture middleware in app.ts reads the incoming
 * stream before Express parsers consume it. We forward that raw buffer (and
 * the original Content-Type) verbatim so multipart/form-data, urlencoded, and
 * any other content type reaches Flask intact.
 */

import http from 'node:http';
import type { Request, Response, NextFunction } from 'express';

const FLASK_PORT = parseInt(process.env.FLASK_PORT ?? '3000', 10);

type RequestWithRawBody = Request & { rawBody?: Buffer };

export function flaskProxy(req: RequestWithRawBody, res: Response, _next: NextFunction): void {
  const rawBody: Buffer | undefined = req.rawBody;
  const hasBody =
    rawBody !== undefined &&
    rawBody.length > 0 &&
    req.method !== 'GET' &&
    req.method !== 'HEAD';

  // Forward headers verbatim — this preserves cookies (session auth),
  // Content-Type (JSON / multipart / urlencoded), Accept, etc.
  const forwardedHeaders: http.OutgoingHttpHeaders = {
    ...req.headers,
    host: `localhost:${FLASK_PORT}`,
  };

  if (hasBody) {
    // Use the exact length of the raw bytes we're about to send.
    forwardedHeaders['content-length'] = rawBody!.length.toString();
    // content-type is already set from req.headers above.
  } else {
    // No body — remove stale length/encoding headers so Flask doesn't wait.
    delete forwardedHeaders['content-length'];
    delete forwardedHeaders['transfer-encoding'];
  }

  const options: http.RequestOptions = {
    hostname: 'localhost',
    port: FLASK_PORT,
    path: req.originalUrl,
    method: req.method,
    headers: forwardedHeaders,
  };

  const proxyReq = http.request(options, (proxyRes) => {
    // Stream the Flask response (any content-type: JSON, PNG, HTML…) back.
    res.writeHead(proxyRes.statusCode ?? 502, proxyRes.headers);
    proxyRes.pipe(res, { end: true });
  });

  proxyReq.on('error', (err) => {
    console.error('[flask-proxy] upstream error:', err.message);
    if (!res.headersSent) {
      res.status(502).json({ error: 'Flask upstream unavailable', detail: err.message });
    }
  });

  if (hasBody) {
    proxyReq.write(rawBody!);
  }
  proxyReq.end();
}
