import type { ReactElement } from "react";

/* Sign-in diagram: Connect -> Unify -> Ask, drawn for the brand-blue story panel
   (transparent background, white and orange on blue). 1200x580 drawing space;
   the headline and supporting copy live in the page as real text. */

const BLUE = "#2563eb", BLUE_DEEP = "#1d4ed8", BLUE_SOFT = "#eaf1ff", ORANGE = "#fdba74",
  ORANGE_DEEP = "#c2410c", ORANGE_SOFT = "#fff4e8", INK = "#14213d", MUTED = "#5b6782", LINE = "#dbe5f7",
  ON_BLUE = "#dbeafe", ON_BLUE_MUTED = "#bfdbfe";

const SOURCES = ["Documents", "Databases", "Cloud storage", "Apps & APIs", "Sheets", "Email"] as const;
const TILE = { x: 24, y: 92, w: 236, h: 62, gap: 14 };
const CORE = { x: 560, y: 318, r: 108 };
const ASK = { x: 830, y: 150, w: 346, h: 318 };
const tileY = (i: number) => TILE.y + i * (TILE.h + TILE.gap);
const tileMid = (i: number) => tileY(i) + TILE.h / 2;
const sourcePath = (i: number) => {
  const x = TILE.x + TILE.w, y = tileMid(i), tx = CORE.x - CORE.r - 26, ty = CORE.y + (i - 2.5) * 26;
  return `M${x} ${y} C${x + 110} ${y} ${tx - 100} ${ty} ${tx} ${ty}`;
};
const ASK_PATH = `M${CORE.x + CORE.r + 30} ${CORE.y} L${ASK.x} ${CORE.y}`;
const FLOW_SECONDS = 2.8;
const CITATIONS = ["Contracts.pdf", "CRM", "Drive"] as const;
const chipWidth = (label: string) => label.length * 7.8 + 40;
const chipX = (i: number) => CITATIONS.slice(0, i).reduce((x, label) => x + chipWidth(label) + 6, 0);
const QUESTION = { w: 232, h: 40 };
const QX = ASK.x + ASK.w - 16 - QUESTION.w;

function SourceIcon({ kind }: { kind: (typeof SOURCES)[number] }) {
  const s = { fill: "none", stroke: BLUE, strokeWidth: 2.6, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  switch (kind) {
    case "Documents":
      return <g {...s}><path d="M-10 -14h12l7 7v21h-19z" /><path d="M2 -14v7h7" /><path d="M-5 0h10M-5 6h10" stroke={ORANGE_DEEP} /></g>;
    case "Databases":
      return <g {...s}><ellipse cx="0" cy="-9" rx="12" ry="4.5" /><path d="M-12 -9v18c0 2.5 5.4 4.5 12 4.5s12-2 12-4.5v-18" /><path d="M-12 0c0 2.5 5.4 4.5 12 4.5s12-2 12-4.5" stroke={ORANGE_DEEP} /></g>;
    case "Cloud storage":
      return <g {...s}><path d="M-9 9h19a7.5 7.5 0 0 0 0-15 10.5 10.5 0 0 0-20-2.5A7 7 0 0 0-9 9z" /><path d="M0 -2v9M-4 3l4 4 4-4" stroke={ORANGE_DEEP} /></g>;
    case "Apps & APIs":
      return <g {...s}><path d="M-6 -9l-8 9 8 9M6 -9l8 9-8 9" /><path d="M3 -12l-6 24" stroke={ORANGE_DEEP} /></g>;
    case "Sheets":
      return <g {...s}><rect x="-13" y="-11" width="26" height="22" rx="3" /><path d="M-13 -3h26M-13 4h26M-4 -11v22" /></g>;
    case "Email":
      return <g {...s}><rect x="-13" y="-9" width="26" height="18" rx="3" /><path d="M-13 -7l13 10 13-10" stroke={ORANGE_DEEP} /></g>;
    default:
      return null;
  }
}


function FlowDot({ path, tone, delay }: { path: string; tone: "light" | "orange"; delay: number }) {
  return <>{[delay, delay + FLOW_SECONDS / 2].map(start => {
    const begin = `${start}s`, dur = `${FLOW_SECONDS}s`;
    return <g key={start} className={`lapi-banner-dot ${tone}`} opacity={0}>
      <circle r="9" fill={tone === "light" ? "#ffffff" : ORANGE} opacity={0.3} />
      <circle r="4" fill={tone === "light" ? "#ffffff" : "#fb923c"} />
      <animateMotion dur={dur} begin={begin} repeatCount="indefinite" path={path} />
      <animate attributeName="opacity" values="0;1;1;0" keyTimes="0;0.12;0.82;1" dur={dur} begin={begin} repeatCount="indefinite" />
    </g>;
  })}</>;
}

/** The Connect -> Unify -> Ask story as one responsive SVG, for a brand-blue background. */
export function LapiBanner({ className }: { className?: string }) {
  const orbit: ReactElement[] = [];
  for (let i = 0; i < 16; i++) {
    const a = (i / 16) * Math.PI * 2, r = CORE.r + 40;
    orbit.push(<circle key={i} cx={CORE.x + Math.cos(a) * r} cy={CORE.y + Math.sin(a) * r} r={i % 4 ? 3 : 5}
      fill={i % 4 ? ON_BLUE_MUTED : ORANGE} opacity={i % 4 ? 0.7 : 1} />);
  }
  return <svg className={className} viewBox="0 70 1200 510" role="img" aria-label="Lapi: connect your data, unify it into one knowledge base, and ask"
    fontFamily="Inter, ui-sans-serif, system-ui, sans-serif">
    <defs>
      <radialGradient id="lb-glow" cx="0.5" cy="0.5" r="0.5">
        <stop offset="0" stopColor={ORANGE} stopOpacity="0.55" /><stop offset="1" stopColor={ORANGE} stopOpacity="0" />
      </radialGradient>
      <linearGradient id="lb-agent" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stopColor={INK} /><stop offset="1" stopColor="#1e3a8a" />
      </linearGradient>
      <clipPath id="lb-ask"><rect x={ASK.x} y={ASK.y} width={ASK.w} height={ASK.h} rx="22" /></clipPath>
      <filter id="lb-shadow" x="-20%" y="-30%" width="140%" height="170%">
        <feDropShadow dx="0" dy="14" stdDeviation="16" floodColor="#0b1b4d" floodOpacity="0.32" />
      </filter>
    </defs>

    {/* 1 Connect: glass source tiles */}
    {SOURCES.map((_, i) => <path key={`p${i}`} d={sourcePath(i)} fill="none" stroke={i % 2 ? "#ffffff" : ORANGE}
      strokeOpacity={i % 2 ? 0.3 : 0.55} strokeWidth="2.5" strokeLinecap="round" />)}
    {SOURCES.map((name, i) => <g key={name}>
      <rect x={TILE.x} y={tileY(i)} width={TILE.w} height={TILE.h} rx="16" fill="#ffffff" fillOpacity="0.1" stroke="#ffffff" strokeOpacity="0.24" strokeWidth="1.5" />
      <circle cx={TILE.x + 36} cy={tileMid(i)} r="21" fill="#ffffff" />
      <g transform={`translate(${TILE.x + 36} ${tileMid(i)})`}><SourceIcon kind={name} /></g>
      <text x={TILE.x + 70} y={tileMid(i) + 7} fontSize="20" fontWeight="600" fill="#ffffff">{name}</text>
    </g>)}

    {/* 2 Unify: one knowledge base carrying the Lapi mark */}
    <circle cx={CORE.x} cy={CORE.y} r={CORE.r + 90} fill="url(#lb-glow)" />
    <g className="lapi-banner-orbit">{orbit}</g>
    <circle className="lapi-banner-ring" cx={CORE.x} cy={CORE.y} r={CORE.r + 20} fill="none" stroke={ORANGE} strokeWidth="3" strokeDasharray="6 12" />
    <circle cx={CORE.x} cy={CORE.y} r={CORE.r} fill="#ffffff" filter="url(#lb-shadow)" />
    <circle cx={CORE.x} cy={CORE.y} r={CORE.r - 14} fill={BLUE_SOFT} />
    <image href="/lapi-mark.svg" x={CORE.x - 62} y={CORE.y - 62} width="124" height="124" />
    <text x={CORE.x} y={CORE.y + CORE.r + 78} textAnchor="middle" fontSize="25" fontWeight="700" fill="#ffffff">One knowledge base</text>
    <text x={CORE.x} y={CORE.y + CORE.r + 108} textAnchor="middle" fontSize="18" fill={ON_BLUE}>Embeddings · hybrid search · reranking</text>

    {/* 3 Ask: a grounded, cited answer in a Lapi Agent chat card */}
    <path d={ASK_PATH} stroke={ORANGE} strokeOpacity="0.7" strokeWidth="3" strokeLinecap="round" strokeDasharray="2 9" />
    <g filter="url(#lb-shadow)">
      <rect x={ASK.x} y={ASK.y} width={ASK.w} height={ASK.h} rx="22" fill="#ffffff" />
    </g>
    <g clipPath="url(#lb-ask)">
      <rect x={ASK.x} y={ASK.y} width={ASK.w} height="64" fill="url(#lb-agent)" />
      <circle cx={ASK.x + ASK.w - 24} cy={ASK.y - 8} r="48" fill={ORANGE} opacity="0.3" />
    </g>
    <image href="/lapi-mark.svg" x={ASK.x + 16} y={ASK.y + 12} width="40" height="40" />
    <text x={ASK.x + 68} y={ASK.y + 30} fontSize="18" fontWeight="700" fill="#ffffff">Lapi Agent</text>
    <text x={ASK.x + 68} y={ASK.y + 49} fontSize="13" fill={ON_BLUE}>Answers with citations</text>
    <rect x={ASK.x + ASK.w - 104} y={ASK.y + 20} width="88" height="24" rx="12" fill="#ffffff" fillOpacity="0.14" stroke="#ffffff" strokeOpacity="0.4" />
    <circle cx={ASK.x + ASK.w - 90} cy={ASK.y + 32} r="4" fill={ORANGE} />
    <text x={ASK.x + ASK.w - 80} y={ASK.y + 36.5} fontSize="12.5" fontWeight="600" fill="#ffffff">3 sources</text>

    <rect x={QX} y={ASK.y + 80} width={QUESTION.w} height={QUESTION.h} rx="20" fill={BLUE} />
    <rect x={QX + QUESTION.w - 20} y={ASK.y + 80 + QUESTION.h - 20} width="20" height="20" rx="5" fill={BLUE} />
    <text x={QX + QUESTION.w / 2} y={ASK.y + 105} textAnchor="middle" fontSize="16" fontWeight="600" fill="#ffffff">What changed in renewals?</text>

    <rect x={ASK.x + 16} y={ASK.y + 136} width={ASK.w - 32} height="86" rx="16" fill="#f6f9ff" stroke={LINE} />
    <rect x={ASK.x + 28} y={ASK.y + 150} width="4" height="58" rx="2" fill={ORANGE} />
    <text x={ASK.x + 44} y={ASK.y + 170} fontSize="17" fill={INK}>Three contracts moved to</text>
    <text x={ASK.x + 44} y={ASK.y + 196} fontSize="17" fill={INK}><tspan fontWeight="700" fill={BLUE_DEEP}>net-60</tspan> payment terms.</text>
    {CITATIONS.map((_, i) => <g key={i}>
      <circle cx={ASK.x + 236 + i * 22} cy={ASK.y + 190} r="9.5" fill={ORANGE_SOFT} stroke={ORANGE} />
      <text x={ASK.x + 236 + i * 22} y={ASK.y + 194} textAnchor="middle" fontSize="11" fontWeight="700" fill={ORANGE_DEEP}>{i + 1}</text>
    </g>)}

    <text x={ASK.x + 18} y={ASK.y + 246} fontSize="11.5" fontWeight="700" letterSpacing="2" fill={MUTED}>SOURCES</text>
    {CITATIONS.map((label, i) => <g key={label} transform={`translate(${ASK.x + 16 + chipX(i)} ${ASK.y + 256})`}>
      <rect width={chipWidth(label)} height="28" rx="14" fill="#ffffff" stroke={LINE} />
      <circle cx="15" cy="14" r="9" fill={ORANGE_SOFT} stroke={ORANGE} />
      <text x="15" y="18" textAnchor="middle" fontSize="11" fontWeight="700" fill={ORANGE_DEEP}>{i + 1}</text>
      <text x="30" y="19" fontSize="14" fontWeight="600" fill={INK}>{label}</text>
    </g>)}
    <path d={`M${ASK.x + 19} ${ASK.y + 300}l4 4 8-9`} fill="none" stroke={BLUE} strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
    <text x={ASK.x + 38} y={ASK.y + 304} fontSize="13" fill={MUTED}>Verified against your data</text>

    <g className="lapi-banner-flow">
      {SOURCES.map((_, i) => <FlowDot key={i} path={sourcePath(i)} tone={i % 2 ? "light" : "orange"} delay={i * 0.35} />)}
      <FlowDot path={ASK_PATH} tone="orange" delay={0.6} />
    </g>
  </svg>;
}
