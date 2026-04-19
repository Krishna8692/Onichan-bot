import { Router, type IRouter } from "express";
import healthRouter from "./health";
import casinoProxyRouter from "./casino-proxy";

const router: IRouter = Router();

router.use(healthRouter);
router.use("/casino", casinoProxyRouter);

export default router;
