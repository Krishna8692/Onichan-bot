import { motion } from "framer-motion";
import { ArrowUpRight } from "lucide-react";

export function BottomLeftCard() {
  return (
    <motion.div
      initial={{ x: -20, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      transition={{ duration: 0.8, delay: 0.2 }}
      className="absolute bottom-28 right-4 left-auto md:left-6 md:right-auto md:bottom-6 lg:bottom-10 lg:left-10 p-3 md:p-4 lg:p-5 rounded-[1.2rem] md:rounded-[1.5rem] lg:rounded-[2.2rem] flex flex-col gap-2 lg:gap-3 min-w-[140px] md:min-w-[150px] lg:min-w-[180px] w-fit"
      style={{
        background: "rgba(255,255,255,0.12)",
        backdropFilter: "blur(24px)",
        border: "1px solid rgba(255,255,255,0.15)",
      }}
    >
      <div className="flex flex-col">
        <span
          className="text-2xl md:text-3xl font-normal tracking-tight"
          style={{ color: "rgba(210,230,255,0.95)" }}
        >
          847K+
        </span>
        <span
          className="text-[10px] md:text-[12px] font-normal uppercase tracking-wider"
          style={{ color: "rgba(160,190,230,0.65)" }}
        >
          Cards Checked
        </span>
      </div>

      <motion.button
        whileHover={{ scale: 1.02 }}
        whileTap={{ scale: 0.98 }}
        className="flex items-center rounded-full pl-1.5 pr-5 py-1.5 gap-2 transition-colors self-start"
        style={{ background: "rgba(255,255,255,0.15)", border: "1px solid rgba(255,255,255,0.2)" }}
      >
        <div
          className="p-1 rounded-full flex items-center justify-center"
          style={{ background: "rgba(255,255,255,0.15)" }}
        >
          <ArrowUpRight className="w-4 h-4" style={{ color: "rgba(200,220,255,0.9)" }} />
        </div>
        <span className="text-[14px] font-normal" style={{ color: "rgba(200,220,255,0.9)" }}>
          Join Telegram
        </span>
      </motion.button>
    </motion.div>
  );
}
