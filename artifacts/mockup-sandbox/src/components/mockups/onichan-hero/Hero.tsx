import { motion, useScroll, useTransform } from "framer-motion";
import { Navbar } from "./Navbar";
import { HeroBadge } from "./HeroBadge";
import { BottomLeftCard } from "./BottomLeftCard";
import { BottomRightCorner } from "./BottomRightCorner";
import { FloatingCards } from "./FloatingCards";

export function Hero() {
  const { scrollY } = useScroll();
  const titleY = useTransform(scrollY, [0, 500], [0, -80]);
  const titleO = useTransform(scrollY, [0, 350], [1, 0]);
  const badgeY = useTransform(scrollY, [0, 400], [0, -60]);
  const badgeO = useTransform(scrollY, [0, 280], [1, 0]);
  const bgY    = useTransform(scrollY, [0, 600], [0, 40]);

  return (
    <div style={{ background: "#f0f0f0", minHeight: "180vh" }}>
      <div style={{ position: "sticky", top: 0, height: "100vh", overflow: "hidden" }}>
        <div className="w-full h-full flex items-center justify-center p-3 md:p-5">
          <motion.section
            style={{ y: bgY }}
            className="relative w-full max-w-[1536px] h-full rounded-[1.5rem] md:rounded-[3rem] overflow-hidden shadow-none flex flex-col items-center bg-white/10 group"
          >
            <FloatingCards />

            <div className="relative z-10 w-full h-full flex flex-col items-center">
              <Navbar />

              <div className="w-full flex flex-col items-center pt-8 px-6 text-center max-w-4xl">
                <motion.div style={{ y: badgeY, opacity: badgeO }}>
                  <HeroBadge />
                </motion.div>

                <motion.h1
                  style={{ y: titleY, opacity: titleO }}
                  initial={{ opacity: 0, scale: 0.98 }}
                  animate={{ opacity: 1, scale: 1 }}
                  transition={{ duration: 0.8, delay: 0.2 }}
                  className="text-4xl sm:text-5xl md:text-6xl lg:text-[80px] font-normal text-[#5E6470] mb-2 tracking-tight leading-[1.05]"
                >
                  Elite Card Operations
                </motion.h1>

                <motion.p
                  style={{ y: titleY, opacity: titleO }}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ duration: 0.8, delay: 0.4 }}
                  className="text-sm sm:text-base md:text-lg text-[#5E6470] opacity-80 leading-relaxed max-w-xl font-normal"
                >
                  Run gates, check bins, and hit checkouts with surgical precision.
                  Built for speed, zero friction, maximum output.
                </motion.p>
              </div>

              <BottomLeftCard />
              <BottomRightCorner />
            </div>
          </motion.section>
        </div>
      </div>
    </div>
  );
}
