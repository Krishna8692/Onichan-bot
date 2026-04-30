import { motion } from "framer-motion";
import { ChevronRight, ArrowUpRight } from "lucide-react";

const items = [
  { label: "Gates",    hasDropdown: false },
  { label: "Checker",  hasDropdown: true  },
  { label: "Hitter",   hasDropdown: true  },
  { label: "Docs",     hasDropdown: false },
];

export function Navbar() {
  return (
    <nav className="flex items-center justify-between py-6 px-6 md:px-10 w-full relative z-10">
      <div className="flex-1 hidden md:block" />

      <ul className="hidden md:flex items-center gap-8 font-normal text-sm" style={{ color: "rgba(200,215,240,0.85)" }}>
        {items.map((item) => (
          <li
            key={item.label}
            className="cursor-pointer transition-opacity flex items-center gap-1 group"
            style={{ opacity: 1 }}
            onMouseEnter={e => (e.currentTarget.style.opacity = "0.6")}
            onMouseLeave={e => (e.currentTarget.style.opacity = "1")}
          >
            {item.label}
            {item.hasDropdown && (
              <ChevronRight className="w-4 h-4 transition-transform group-hover:translate-x-0.5" />
            )}
          </li>
        ))}
      </ul>

      <div className="md:hidden">
        <span className="font-regular tracking-tighter text-xl" style={{ color: "rgba(200,215,240,0.9)" }}>
          Onichan
        </span>
      </div>

      <div className="flex-1 flex justify-end">
        <motion.button
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          className="flex items-center text-white rounded-full pl-2 pr-4 md:pr-6 py-1.5 md:py-2 gap-2 md:gap-3 transition-colors group"
          style={{ background: "rgba(255,255,255,0.15)", backdropFilter: "blur(12px)", border: "1px solid rgba(255,255,255,0.2)" }}
        >
          <div className="bg-white/20 p-1 md:p-1.5 rounded-full flex items-center justify-center">
            <ArrowUpRight className="w-4 h-4 md:w-5 md:h-5 text-white" />
          </div>
          <span className="text-xs md:text-sm font-normal">Get Access</span>
        </motion.button>
      </div>
    </nav>
  );
}
