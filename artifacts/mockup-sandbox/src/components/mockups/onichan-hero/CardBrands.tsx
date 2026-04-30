import { motion } from "framer-motion";

interface BrandConfig {
  name: string;
  bg: string;
  text: string;
  accent?: string;
  isMastercard?: boolean;
  hasOrange?: boolean;
}

const brands: BrandConfig[] = [
  { name: "VISA",     bg: "#1A1F71", text: "#FFFFFF" },
  { name: "mastercard", bg: "#252525", text: "#EB001B", accent: "#F79E1B", isMastercard: true },
  { name: "AMEX",     bg: "#007BC1", text: "#FFFFFF" },
  { name: "DISCOVER", bg: "#FFFFFF", text: "#231F20", hasOrange: true },
  { name: "JCB",      bg: "#003087", text: "#FFFFFF" },
  { name: "UnionPay", bg: "#C0392B", text: "#FFFFFF" },
  { name: "MAESTRO",  bg: "#1A1F71", text: "#FFFFFF" },
  { name: "Diners",   bg: "#004B87", text: "#FFFFFF" },
  { name: "VISA",     bg: "#1A1F71", text: "#FFFFFF" },
  { name: "mastercard", bg: "#252525", text: "#EB001B", accent: "#F79E1B", isMastercard: true },
  { name: "AMEX",     bg: "#007BC1", text: "#FFFFFF" },
  { name: "DISCOVER", bg: "#FFFFFF", text: "#231F20", hasOrange: true },
  { name: "JCB",      bg: "#003087", text: "#FFFFFF" },
  { name: "UnionPay", bg: "#C0392B", text: "#FFFFFF" },
];

const positions = [
  { x: "3%",  y: "6%",  rotate: -12 },
  { x: "18%", y: "14%", rotate: 6   },
  { x: "36%", y: "3%",  rotate: -5  },
  { x: "54%", y: "12%", rotate: 10  },
  { x: "70%", y: "4%",  rotate: -8  },
  { x: "83%", y: "18%", rotate: 4   },
  { x: "8%",  y: "52%", rotate: 7   },
  { x: "76%", y: "48%", rotate: -10 },
  { x: "2%",  y: "72%", rotate: -6  },
  { x: "20%", y: "76%", rotate: 9   },
  { x: "43%", y: "74%", rotate: -14 },
  { x: "60%", y: "70%", rotate: 5   },
  { x: "78%", y: "76%", rotate: -7  },
  { x: "88%", y: "58%", rotate: 12  },
];

function Chip() {
  return (
    <div style={{
      width: 32, height: 24, borderRadius: 4,
      background: "linear-gradient(135deg, #d4af37 0%, #f0d060 50%, #b8860b 100%)",
      border: "1px solid rgba(255,255,255,0.3)",
      display: "flex", alignItems: "center", justifyContent: "center",
    }}>
      <div style={{
        width: 22, height: 17, borderRadius: 2,
        border: "1px solid rgba(184,134,11,0.6)",
        display: "grid", gridTemplateColumns: "1fr 1fr 1fr",
        gap: 1, padding: 2,
      }}>
        {Array.from({ length: 9 }).map((_, i) => (
          <div key={i} style={{ background: "rgba(184,134,11,0.5)", borderRadius: 1 }} />
        ))}
      </div>
    </div>
  );
}

function MastercardBrand({ text, accent }: { text: string; accent?: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
      <div style={{ position: "relative", width: 40, height: 24 }}>
        <div style={{
          position: "absolute", left: 0, width: 24, height: 24,
          borderRadius: "50%", background: text, opacity: 0.9,
        }} />
        <div style={{
          position: "absolute", left: 16, width: 24, height: 24,
          borderRadius: "50%", background: accent, opacity: 0.85,
        }} />
      </div>
      <span style={{ color: "#fff", fontSize: 10, fontWeight: 600, letterSpacing: 1 }}>
        mastercard
      </span>
    </div>
  );
}

interface CardProps {
  brand: BrandConfig;
  index: number;
  pos: typeof positions[0];
}

function CardItem({ brand, index, pos }: CardProps) {
  const delay = index * 0.07;
  const floatDuration = 3 + (index % 4) * 0.6;

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.75, rotate: pos.rotate - 8 }}
      animate={{
        opacity: 0.82,
        scale: 1,
        rotate: pos.rotate,
        y: [0, -10, 0],
      }}
      transition={{
        opacity:  { duration: 0.6, delay },
        scale:    { duration: 0.6, delay },
        rotate:   { duration: 0.6, delay },
        y: {
          duration: floatDuration,
          delay: delay + 0.6,
          repeat: Infinity,
          ease: "easeInOut",
        },
      }}
      style={{
        position: "absolute",
        left: pos.x,
        top: pos.y,
        width: 168,
        height: 105,
        borderRadius: 14,
        background: brand.bg,
        boxShadow: "0 8px 32px rgba(0,0,0,0.35), 0 2px 8px rgba(0,0,0,0.2)",
        padding: "10px 12px",
        display: "flex",
        flexDirection: "column",
        justifyContent: "space-between",
        border: "1px solid rgba(255,255,255,0.12)",
        backdropFilter: "blur(4px)",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <Chip />
        <div style={{
          width: 22, height: 22, borderRadius: "50%",
          background: "radial-gradient(circle, rgba(255,255,255,0.15) 0%, transparent 70%)",
          border: "1px solid rgba(255,255,255,0.15)",
        }} />
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
        <span style={{
          color: "rgba(255,255,255,0.45)",
          fontSize: 8,
          fontFamily: "monospace",
          letterSpacing: 2,
        }}>
          •••• •••• •••• {(1337 + index * 419) % 9000 + 1000}
        </span>

        {brand.isMastercard ? (
          <MastercardBrand text={brand.text} accent={brand.accent} />
        ) : (
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ color: "rgba(255,255,255,0.4)", fontSize: 8, letterSpacing: 1 }}>
              HOLDER
            </span>
            <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
              <span style={{
                color: brand.text,
                fontSize: brand.name === "DISCOVER" ? 11 : 14,
                fontWeight: 900,
                letterSpacing: brand.name === "VISA" ? 3 : 1,
                fontStyle: brand.name === "VISA" ? "italic" : "normal",
              }}>
                {brand.name}
              </span>
              {brand.hasOrange && (
                <div style={{
                  width: 14, height: 14, borderRadius: "50%",
                  background: "#F76F20",
                }} />
              )}
            </div>
          </div>
        )}
      </div>
    </motion.div>
  );
}

export function CardBrands() {
  return (
    <div style={{
      position: "absolute", inset: 0, overflow: "hidden",
      pointerEvents: "none",
    }}>
      {brands.slice(0, positions.length).map((brand, i) => (
        <CardItem key={i} brand={brand} index={i} pos={positions[i]} />
      ))}
    </div>
  );
}
