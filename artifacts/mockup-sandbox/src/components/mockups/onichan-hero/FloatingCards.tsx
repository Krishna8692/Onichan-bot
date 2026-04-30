import { motion } from "framer-motion";

function ContactlessIcon() {
  return (
    <svg width="18" height="22" viewBox="0 0 18 22" fill="none">
      <path d="M9 4C12.866 4 16 7.134 16 11C16 14.866 12.866 18 9 18" stroke="rgba(255,255,255,0.55)" strokeWidth="1.4" strokeLinecap="round" fill="none"/>
      <path d="M9 7C11.209 7 13 8.791 13 11C13 13.209 11.209 15 9 15" stroke="rgba(255,255,255,0.55)" strokeWidth="1.4" strokeLinecap="round" fill="none"/>
      <path d="M9 10C9.552 10 10 10.448 10 11C10 11.552 9.552 12 9 12" stroke="rgba(255,255,255,0.55)" strokeWidth="1.8" strokeLinecap="round" fill="none"/>
    </svg>
  );
}

function Chip({ dark = false }: { dark?: boolean }) {
  const gold = dark ? "#b8970a" : "#d4af37";
  const goldMid = dark ? "#d4a80a" : "#f0d060";
  const goldDark = dark ? "#8a6d00" : "#b8860b";
  return (
    <svg width="38" height="28" viewBox="0 0 38 28" fill="none">
      <rect x="0.5" y="0.5" width="37" height="27" rx="4.5" fill={`url(#chip-grad-${dark ? "d" : "l"})`} stroke={`rgba(255,255,255,0.25)`} strokeWidth="0.5"/>
      <line x1="13" y1="0" x2="13" y2="28" stroke={goldDark} strokeWidth="0.5" opacity="0.6"/>
      <line x1="25" y1="0" x2="25" y2="28" stroke={goldDark} strokeWidth="0.5" opacity="0.6"/>
      <line x1="0" y1="9" x2="38" y2="9" stroke={goldDark} strokeWidth="0.5" opacity="0.6"/>
      <line x1="0" y1="19" x2="38" y2="19" stroke={goldDark} strokeWidth="0.5" opacity="0.6"/>
      <rect x="13.5" y="9.5" width="11" height="9" rx="1" fill={goldDark} opacity="0.35"/>
      <defs>
        <linearGradient id={`chip-grad-${dark ? "d" : "l"}`} x1="0" y1="0" x2="38" y2="28" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor={goldMid}/>
          <stop offset="40%" stopColor={gold}/>
          <stop offset="100%" stopColor={goldDark}/>
        </linearGradient>
      </defs>
    </svg>
  );
}

function VisaLogo() {
  return (
    <svg width="68" height="22" viewBox="0 0 68 22" fill="none">
      <text x="0" y="18" fontFamily="serif" fontSize="22" fontWeight="900" fontStyle="italic" fill="white" letterSpacing="-1">VISA</text>
    </svg>
  );
}

function MastercardLogo() {
  return (
    <svg width="54" height="34" viewBox="0 0 54 34" fill="none">
      <circle cx="20" cy="17" r="17" fill="#EB001B"/>
      <circle cx="34" cy="17" r="17" fill="#F79E1B" opacity="0.9"/>
      <path d="M27 5.2C29.8 7.5 31.7 10.9 31.7 17C31.7 23.1 29.8 26.5 27 28.8C24.2 26.5 22.3 23.1 22.3 17C22.3 10.9 24.2 7.5 27 5.2Z" fill="#FF5F00"/>
    </svg>
  );
}

function AmexLogo() {
  return (
    <svg width="64" height="28" viewBox="0 0 64 28" fill="none">
      <rect width="64" height="28" rx="3" fill="rgba(255,255,255,0.18)"/>
      <text x="50%" y="19" textAnchor="middle" fontFamily="Arial, sans-serif" fontSize="11" fontWeight="900" fill="white" letterSpacing="2">AMEX</text>
    </svg>
  );
}

const cards = [
  {
    id: "visa",
    gradient: "linear-gradient(135deg, #1a237e 0%, #283593 40%, #1565c0 100%)",
    shimmer: "rgba(255,255,255,0.07)",
    number: "4532 •••• •••• 1847",
    name: "J. MORRISON",
    expiry: "09/28",
    rotate: -14,
    x: "4%",
    y: "12%",
    floatDelay: 0,
    Logo: VisaLogo,
    darkChip: false,
  },
  {
    id: "mastercard",
    gradient: "linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%)",
    shimmer: "rgba(255,255,255,0.05)",
    number: "5412 •••• •••• 3390",
    name: "A. BLACKWOOD",
    expiry: "03/27",
    rotate: 8,
    x: "62%",
    y: "8%",
    floatDelay: 0.6,
    Logo: MastercardLogo,
    darkChip: true,
  },
  {
    id: "amex",
    gradient: "linear-gradient(135deg, #006FAD 0%, #0087C8 45%, #00A8E8 100%)",
    shimmer: "rgba(255,255,255,0.09)",
    number: "3714 •••••• 43609",
    name: "R. KINGSLEY",
    expiry: "11/29",
    rotate: 5,
    x: "30%",
    y: "62%",
    floatDelay: 1.1,
    Logo: AmexLogo,
    darkChip: false,
  },
];

export function FloatingCards() {
  return (
    <div style={{ position: "absolute", inset: 0, overflow: "hidden", pointerEvents: "none" }}>
      {cards.map((card, i) => (
        <motion.div
          key={card.id}
          initial={{ opacity: 0, scale: 0.82, rotate: card.rotate - 6 }}
          animate={{
            opacity: 0.92,
            scale: 1,
            rotate: card.rotate,
            y: [0, -18, 0],
          }}
          transition={{
            opacity: { duration: 0.9, delay: card.floatDelay },
            scale:   { duration: 0.9, delay: card.floatDelay },
            rotate:  { duration: 0.9, delay: card.floatDelay },
            y: {
              duration: 5 + i * 0.8,
              delay: card.floatDelay + 0.9,
              repeat: Infinity,
              ease: "easeInOut",
            },
          }}
          style={{
            position: "absolute",
            left: card.x,
            top: card.y,
            width: 320,
            height: 200,
            borderRadius: 18,
            background: card.gradient,
            boxShadow: "0 24px 60px rgba(0,0,0,0.38), 0 6px 18px rgba(0,0,0,0.22), inset 0 1px 0 rgba(255,255,255,0.18)",
            border: "1px solid rgba(255,255,255,0.14)",
            padding: "22px 26px",
            display: "flex",
            flexDirection: "column",
            justifyContent: "space-between",
            overflow: "hidden",
          }}
        >
          <div
            style={{
              position: "absolute",
              top: -60,
              right: -40,
              width: 240,
              height: 240,
              borderRadius: "50%",
              background: card.shimmer,
              pointerEvents: "none",
            }}
          />
          <div
            style={{
              position: "absolute",
              bottom: -80,
              left: -30,
              width: 200,
              height: 200,
              borderRadius: "50%",
              background: "rgba(255,255,255,0.04)",
              pointerEvents: "none",
            }}
          />

          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
            <Chip dark={card.darkChip} />
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <ContactlessIcon />
            </div>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <span style={{
              color: "rgba(255,255,255,0.85)",
              fontSize: 15,
              fontFamily: "'Courier New', monospace",
              letterSpacing: 3,
              fontWeight: 500,
            }}>
              {card.number}
            </span>

            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end" }}>
              <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                <span style={{ color: "rgba(255,255,255,0.45)", fontSize: 8, letterSpacing: 2, textTransform: "uppercase" }}>
                  Card Holder
                </span>
                <span style={{ color: "rgba(255,255,255,0.88)", fontSize: 13, letterSpacing: 1.5, fontWeight: 600 }}>
                  {card.name}
                </span>
              </div>
              <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 2 }}>
                <span style={{ color: "rgba(255,255,255,0.45)", fontSize: 8, letterSpacing: 2, textTransform: "uppercase" }}>
                  Expires
                </span>
                <span style={{ color: "rgba(255,255,255,0.88)", fontSize: 13, letterSpacing: 1.5, fontWeight: 600 }}>
                  {card.expiry}
                </span>
              </div>
              <card.Logo />
            </div>
          </div>
        </motion.div>
      ))}
    </div>
  );
}
