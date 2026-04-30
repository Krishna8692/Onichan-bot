import { motion } from "framer-motion";
import { Navbar } from "./Navbar";
import { HeroBadge } from "./HeroBadge";
import { BottomLeftCard } from "./BottomLeftCard";
import { BottomRightCorner } from "./BottomRightCorner";
import { CardBrands } from "./CardBrands";

export function Hero() {
  return (
    <div className="w-full h-screen flex items-center justify-center p-3 md:p-5 bg-[#f0f0f0]">
      <section
        className="relative w-full max-w-[1536px] h-full rounded-[1.5rem] md:rounded-[3rem] overflow-hidden shadow-none flex flex-col items-center group"
        style={{
          background:
            "linear-gradient(135deg, #0d1b2a 0%, #1a2744 30%, #0f1e35 60%, #162035 100%)",
        }}
      >
        <div
          className="absolute inset-0 z-0"
          style={{
            background:
              "radial-gradient(ellipse 80% 60% at 50% 0%, rgba(30,60,120,0.45) 0%, transparent 70%), radial-gradient(ellipse 60% 50% at 80% 80%, rgba(20,40,90,0.3) 0%, transparent 60%)",
          }}
        />

        <CardBrands />

        <div
          className="absolute inset-0 z-10 pointer-events-none"
          style={{
            background:
              "radial-gradient(ellipse 70% 60% at 50% 40%, rgba(13,27,42,0.55) 0%, transparent 80%)",
          }}
        />

        <div className="relative z-20 w-full h-full flex flex-col items-center">
          <Navbar />

          <div className="w-full flex flex-col items-center pt-8 px-6 text-center max-w-4xl">
            <HeroBadge />

            <motion.h1
              initial={{ opacity: 0, scale: 0.98 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.8, delay: 0.2 }}
              className="text-4xl sm:text-5xl md:text-6xl lg:text-[80px] font-normal mb-2 tracking-tight leading-[1.05]"
              style={{ color: "rgba(230,235,245,0.95)" }}
            >
              Elite Card Operations
            </motion.h1>

            <motion.p
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.8, delay: 0.4 }}
              className="text-sm sm:text-base md:text-lg leading-relaxed max-w-xl font-normal"
              style={{ color: "rgba(190,205,230,0.75)" }}
            >
              Run gates, check bins, and hit checkouts with surgical precision.
              Built for speed, zero friction, maximum output.
            </motion.p>
          </div>

          <BottomLeftCard />
          <BottomRightCorner />
        </div>
      </section>
    </div>
  );
}
