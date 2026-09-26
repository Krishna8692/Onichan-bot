import express, { type Express, type Request, type Response, type NextFunction } from "express";
import cors from "cors";
import pinoHttp from "pino-http";
import router from "./routes";
import { logger } from "./lib/logger";
import { flaskProxy } from "./lib/flask-proxy";

const app: Express = express();

app.use(
  pinoHttp({
    logger,
    serializers: {
      req(req) {
        return {
          id: req.id,
          method: req.method,
          url: req.url?.split("?")[0],
        };
      },
      res(res) {
        return {
          statusCode: res.statusCode,
        };
      },
    },
  }),
);
app.use(cors());

// Capture raw body BEFORE parsers consume the stream.
// The flask proxy uses this buffer so it can forward any content-type
// (JSON, multipart/form-data, application/x-www-form-urlencoded, etc.)
// verbatim to Flask without re-serialisation.
app.use((req: Request, _res: Response, next: NextFunction) => {
  const chunks: Buffer[] = [];
  req.on("data", (chunk: Buffer) => chunks.push(Buffer.from(chunk)));
  req.on("end", () => {
    (req as Request & { rawBody?: Buffer }).rawBody = Buffer.concat(chunks);
    next();
  });
  req.on("error", next);
});

app.use(express.json());
app.use(express.urlencoded({ extended: true }));

app.use("/api", router);

// Any /api/* route not handled above is proxied to the Flask bot server.
// This is necessary because the api-server artifact owns the /api path prefix
// in Replit's router, so wallet/admin/user API calls would 404 here without it.
app.use(flaskProxy);

export default app;
