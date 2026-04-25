import { Router, type IRouter } from "express";
import healthRouter from "./health";
import casinoProxyRouter from "./casino-proxy";
import extensionRouter from "./extension";

const router: IRouter = Router();

router.use(healthRouter);
router.use("/casino", casinoProxyRouter);
router.use(extensionRouter);

export default router;
