import { useScroll, useTransform, motion, useSpring } from "framer-motion";

function Chip() {
  return (
    <svg width="40" height="30" viewBox="0 0 40 30" fill="none">
      <rect x="0.5" y="0.5" width="39" height="29" rx="4.5"
        fill="url(#cg)" stroke="rgba(255,255,255,0.2)" strokeWidth="0.5"/>
      <line x1="14" y1="0" x2="14" y2="30" stroke="rgba(140,100,0,0.5)" strokeWidth="0.5"/>
      <line x1="26" y1="0" x2="26" y2="30" stroke="rgba(140,100,0,0.5)" strokeWidth="0.5"/>
      <line x1="0" y1="10" x2="40" y2="10" stroke="rgba(140,100,0,0.5)" strokeWidth="0.5"/>
      <line x1="0" y1="20" x2="40" y2="20" stroke="rgba(140,100,0,0.5)" strokeWidth="0.5"/>
      <rect x="14" y="10" width="12" height="10" rx="1" fill="rgba(120,80,0,0.25)"/>
      <defs>
        <linearGradient id="cg" x1="0" y1="0" x2="40" y2="30" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#f0d060"/>
          <stop offset="45%" stopColor="#d4af37"/>
          <stop offset="100%" stopColor="#9a7000"/>
        </linearGradient>
      </defs>
    </svg>
  );
}

function Contactless() {
  return (
    <svg width="20" height="24" viewBox="0 0 20 24" fill="none">
      <path d="M10 5C14.418 5 18 8.582 18 13" stroke="rgba(255,255,255,0.5)" strokeWidth="1.5" strokeLinecap="round"/>
      <path d="M10 8.5C12.761 8.5 15 10.739 15 13.5" stroke="rgba(255,255,255,0.5)" strokeWidth="1.5" strokeLinecap="round"/>
      <path d="M10 12C11.105 12 12 12.895 12 14" stroke="rgba(255,255,255,0.5)" strokeWidth="1.5" strokeLinecap="round"/>
      <circle cx="10" cy="19" r="1.2" fill="rgba(255,255,255,0.5)"/>
    </svg>
  );
}

function VisaCard() {
  return (
    <div style={{
      width: 320, height: 200, borderRadius: 18,
      background: "linear-gradient(135deg, #e8f0fe 0%, #c7d8f8 25%, #90b4f0 55%, #1a56c4 100%)",
      boxShadow: "0 30px 70px rgba(0,0,0,0.45), 0 8px 20px rgba(0,0,0,0.25), inset 0 1px 0 rgba(255,255,255,0.6)",
      border: "1px solid rgba(255,255,255,0.4)",
      padding: "22px 26px",
      display: "flex", flexDirection: "column", justifyContent: "space-between",
      overflow: "hidden", position: "relative",
    }}>
      <div style={{
        position: "absolute", top: -40, right: -20, width: 220, height: 220,
        borderRadius: "50%", background: "rgba(255,255,255,0.18)",
      }}/>
      <div style={{
        position: "absolute", bottom: -60, left: -30, width: 180, height: 180,
        borderRadius: "50%", background: "rgba(255,255,255,0.1)",
      }}/>
      <div style={{ display: "flex", justifyContent: "space-between" }}>
        <Chip />
        <Contactless />
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        <span style={{ color: "rgba(20,50,120,0.7)", fontSize: 14, fontFamily: "monospace", letterSpacing: 3 }}>
          4532 •••• •••• 1847
        </span>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end" }}>
          <div style={{ display: "flex", flexDirection: "column" }}>
            <span style={{ color: "rgba(20,50,120,0.5)", fontSize: 8, letterSpacing: 2 }}>CARD HOLDER</span>
            <span style={{ color: "rgba(10,30,90,0.9)", fontSize: 13, fontWeight: 700, letterSpacing: 1.5 }}>J. MORRISON</span>
          </div>
          <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end" }}>
            <span style={{ color: "rgba(20,50,120,0.5)", fontSize: 8, letterSpacing: 2 }}>EXPIRES</span>
            <span style={{ color: "rgba(10,30,90,0.9)", fontSize: 13, fontWeight: 700 }}>09/28</span>
          </div>
          <svg width="72" height="24" viewBox="0 0 72 24">
            <text x="0" y="21" fontFamily="serif" fontSize="24" fontWeight="900"
              fontStyle="italic" fill="rgba(10,30,100,0.85)" letterSpacing="-1">VISA</text>
          </svg>
        </div>
      </div>
    </div>
  );
}

function MastercardCard() {
  return (
    <div style={{
      width: 320, height: 200, borderRadius: 18,
      background: "linear-gradient(135deg, #c0392b 0%, #e74c3c 40%, #f39c12 80%, #f1c40f 100%)",
      boxShadow: "0 30px 70px rgba(0,0,0,0.45), 0 8px 20px rgba(0,0,0,0.25), inset 0 1px 0 rgba(255,255,255,0.25)",
      border: "1px solid rgba(255,255,255,0.2)",
      padding: "22px 26px",
      display: "flex", flexDirection: "column", justifyContent: "space-between",
      overflow: "hidden", position: "relative",
    }}>
      <div style={{
        position: "absolute", top: -50, right: -30, width: 220, height: 220,
        borderRadius: "50%", background: "rgba(255,255,255,0.08)",
      }}/>
      <div style={{ display: "flex", justifyContent: "space-between" }}>
        <Chip />
        <Contactless />
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        <span style={{ color: "rgba(255,255,255,0.8)", fontSize: 14, fontFamily: "monospace", letterSpacing: 3 }}>
          5412 •••• •••• 3390
        </span>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end" }}>
          <div style={{ display: "flex", flexDirection: "column" }}>
            <span style={{ color: "rgba(255,255,255,0.55)", fontSize: 8, letterSpacing: 2 }}>CARD HOLDER</span>
            <span style={{ color: "white", fontSize: 13, fontWeight: 700, letterSpacing: 1.5 }}>A. BLACKWOOD</span>
          </div>
          <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end" }}>
            <span style={{ color: "rgba(255,255,255,0.55)", fontSize: 8, letterSpacing: 2 }}>EXPIRES</span>
            <span style={{ color: "white", fontSize: 13, fontWeight: 700 }}>03/27</span>
          </div>
          <div style={{ position: "relative", width: 56, height: 34 }}>
            <div style={{ position: "absolute", left: 0, width: 34, height: 34, borderRadius: "50%", background: "#c0392b", opacity: 0.92 }}/>
            <div style={{ position: "absolute", right: 0, width: 34, height: 34, borderRadius: "50%", background: "#f39c12", opacity: 0.88 }}/>
            <span style={{
              position: "absolute", left: "50%", top: "50%",
              transform: "translate(-50%,-50%)",
              fontSize: 8, fontWeight: 700, color: "white",
              letterSpacing: 0.5, whiteSpace: "nowrap",
            }}>mastercard</span>
          </div>
        </div>
      </div>
    </div>
  );
}

function AmexCard() {
  return (
    <div style={{
      width: 320, height: 200, borderRadius: 18,
      background: "linear-gradient(135deg, #1a6b3c 0%, #2e8b57 35%, #27ae60 65%, #52c27a 100%)",
      boxShadow: "0 30px 70px rgba(0,0,0,0.45), 0 8px 20px rgba(0,0,0,0.25), inset 0 1px 0 rgba(255,255,255,0.2)",
      border: "1px solid rgba(255,255,255,0.18)",
      padding: "18px 22px",
      display: "flex", flexDirection: "column", justifyContent: "space-between",
      overflow: "hidden", position: "relative",
    }}>
      <div style={{
        position: "absolute", top: -30, right: -30, width: 200, height: 200,
        borderRadius: "50%", background: "rgba(255,255,255,0.07)",
      }}/>
      <div style={{
        position: "absolute", bottom: -50, left: 40, width: 160, height: 160,
        borderRadius: "50%", background: "rgba(0,0,0,0.08)",
      }}/>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div style={{
          background: "rgba(255,255,255,0.15)", backdropFilter: "blur(4px)",
          border: "1px solid rgba(255,255,255,0.25)",
          borderRadius: 6, padding: "3px 10px",
        }}>
          <span style={{ color: "white", fontSize: 11, fontWeight: 900, letterSpacing: 2 }}>AMERICAN EXPRESS</span>
        </div>
        <Contactless />
      </div>
      <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <Chip />
          <span style={{ color: "rgba(255,255,255,0.75)", fontSize: 13, fontFamily: "monospace", letterSpacing: 2, marginTop: 6 }}>
            3714 •••••• 43609
          </span>
          <div style={{ display: "flex", gap: 20 }}>
            <div style={{ display: "flex", flexDirection: "column" }}>
              <span style={{ color: "rgba(255,255,255,0.5)", fontSize: 8, letterSpacing: 1.5 }}>MEMBER SINCE</span>
              <span style={{ color: "white", fontSize: 12, fontWeight: 700 }}>R. KINGSLEY</span>
            </div>
            <div style={{ display: "flex", flexDirection: "column" }}>
              <span style={{ color: "rgba(255,255,255,0.5)", fontSize: 8, letterSpacing: 1.5 }}>VALID THRU</span>
              <span style={{ color: "white", fontSize: 12, fontWeight: 700 }}>11/29</span>
            </div>
          </div>
        </div>
        <div style={{
          width: 64, height: 64, borderRadius: "50%",
          background: "rgba(255,255,255,0.12)",
          border: "2px solid rgba(255,255,255,0.2)",
          display: "flex", alignItems: "center", justifyContent: "center",
        }}>
          <span style={{ fontSize: 9, color: "rgba(255,255,255,0.7)", textAlign: "center", fontWeight: 600, letterSpacing: 0.5 }}>
            CENTURION
          </span>
        </div>
      </div>
    </div>
  );
}

export function FloatingCards() {
  const { scrollY } = useScroll();

  const visaX   = useSpring(useTransform(scrollY, [0, 600], [0, -160]), { stiffness: 60, damping: 20 });
  const visaY   = useSpring(useTransform(scrollY, [0, 600], [0,  -60]), { stiffness: 60, damping: 20 });
  const visaR   = useSpring(useTransform(scrollY, [0, 600], [-18, -38]), { stiffness: 60, damping: 20 });
  const visaS   = useSpring(useTransform(scrollY, [0, 600], [1, 1.08]), { stiffness: 60, damping: 20 });

  const mcX     = useSpring(useTransform(scrollY, [0, 600], [0,  160]), { stiffness: 60, damping: 20 });
  const mcY     = useSpring(useTransform(scrollY, [0, 600], [0,  -40]), { stiffness: 60, damping: 20 });
  const mcR     = useSpring(useTransform(scrollY, [0, 600], [14,  34]), { stiffness: 60, damping: 20 });
  const mcS     = useSpring(useTransform(scrollY, [0, 600], [1, 1.05]), { stiffness: 60, damping: 20 });

  const amexY   = useSpring(useTransform(scrollY, [0, 600], [0, -100]), { stiffness: 60, damping: 20 });
  const amexS   = useSpring(useTransform(scrollY, [0, 600], [1,  1.1]), { stiffness: 60, damping: 20 });
  const amexR   = useSpring(useTransform(scrollY, [0, 600], [-5,  8]), { stiffness: 60, damping: 20 });

  const float = {
    visa:  { y: [0, -14, 0], transition: { duration: 5,   repeat: Infinity, ease: "easeInOut" } },
    mc:    { y: [0, -10, 0], transition: { duration: 4.5, repeat: Infinity, ease: "easeInOut", delay: 0.8 } },
    amex:  { y: [0, -16, 0], transition: { duration: 6,   repeat: Infinity, ease: "easeInOut", delay: 1.5 } },
  };

  return (
    <div style={{
      position: "absolute", inset: 0, pointerEvents: "none",
      display: "flex", alignItems: "flex-end", justifyContent: "center",
      paddingBottom: 60,
    }}>
      <div style={{ position: "relative", width: 560, height: 320 }}>

        {/* Mastercard — back right */}
        <motion.div
          initial={{ opacity: 0, scale: 0.8, rotate: 14 }}
          animate={{ opacity: 0.95, scale: 1, rotate: 14, ...float.mc }}
          transition={{ opacity: { duration: 0.7, delay: 0.2 }, scale: { duration: 0.7, delay: 0.2 } }}
          style={{
            position: "absolute", right: 0, bottom: 0,
            x: mcX, y: mcY, rotate: mcR, scale: mcS,
            transformOrigin: "bottom center",
            filter: "drop-shadow(0 20px 40px rgba(0,0,0,0.3))",
          }}
        >
          <MastercardCard />
          <div style={{
            height: 28, marginTop: -4, borderRadius: "0 0 18px 18px",
            background: "linear-gradient(to bottom, rgba(180,50,30,0.25), transparent)",
            filter: "blur(8px)", transform: "scaleY(-1) translateY(-4px)",
            opacity: 0.4,
          }}/>
        </motion.div>

        {/* Visa — back left */}
        <motion.div
          initial={{ opacity: 0, scale: 0.8, rotate: -18 }}
          animate={{ opacity: 0.95, scale: 1, rotate: -18, ...float.visa }}
          transition={{ opacity: { duration: 0.7, delay: 0 }, scale: { duration: 0.7, delay: 0 } }}
          style={{
            position: "absolute", left: 0, bottom: 0,
            x: visaX, y: visaY, rotate: visaR, scale: visaS,
            transformOrigin: "bottom center",
            filter: "drop-shadow(0 20px 40px rgba(0,0,0,0.3))",
          }}
        >
          <VisaCard />
          <div style={{
            height: 28, marginTop: -4, borderRadius: "0 0 18px 18px",
            background: "linear-gradient(to bottom, rgba(30,80,200,0.25), transparent)",
            filter: "blur(8px)", transform: "scaleY(-1) translateY(-4px)",
            opacity: 0.4,
          }}/>
        </motion.div>

        {/* Amex — front center */}
        <motion.div
          initial={{ opacity: 0, scale: 0.8, rotate: -5 }}
          animate={{ opacity: 1, scale: 1.04, rotate: -5, ...float.amex }}
          transition={{ opacity: { duration: 0.7, delay: 0.4 }, scale: { duration: 0.7, delay: 0.4 } }}
          style={{
            position: "absolute", left: "50%", bottom: 20,
            marginLeft: -160,
            y: amexY, scale: amexS, rotate: amexR,
            transformOrigin: "bottom center",
            filter: "drop-shadow(0 28px 50px rgba(0,0,0,0.4))",
            zIndex: 10,
          }}
        >
          <AmexCard />
          <div style={{
            height: 32, marginTop: -4,
            background: "linear-gradient(to bottom, rgba(30,140,80,0.3), transparent)",
            filter: "blur(10px)", transform: "scaleY(-1) translateY(-4px)",
            opacity: 0.5, borderRadius: "0 0 18px 18px",
          }}/>
        </motion.div>
      </div>
    </div>
  );
}
