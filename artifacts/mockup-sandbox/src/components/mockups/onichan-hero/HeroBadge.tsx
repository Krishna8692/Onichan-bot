import { motion } from "framer-motion";
import { ShieldCheck } from "lucide-react";

export function HeroBadge() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.6, ease: "easeOut" }}
      className="flex items-center gap-2 px-4 py-2 rounded-full mx-auto mb-3 w-fit"
      style={{
        background: "rgba(255,255,255,0.1)",
        backdropFilter: "blur(12px)",
        border: "1px solid rgba(255,255,255,0.15)",
      }}
    >
      <ShieldCheck className="w-4 h-4" style={{ color: "rgba(130,180,255,0.9)" }} />
      <span className="text-[14px] font-normal" style={{ color: "rgba(200,220,255,0.9)" }}>
        Ghost Mode Active
      </span>
    </motion.div>
  );
}
