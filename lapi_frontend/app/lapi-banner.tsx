import type { ReactElement } from "react";

/* Sign-in banner: Connect -> Unify -> Ask, flowing left to right in the Lapi palette.
   Drawn in a 1280x900 space; the Lapi mark sits at the centre of the knowledge core. */

const BLUE = "#2563eb", BLUE_DEEP = "#1d4ed8", BLUE_SOFT = "#eaf1ff", ORANGE = "#fdba74",
  ORANGE_DEEP = "#c2410c", ORANGE_SOFT = "#fff4e8", INK = "#14213d", MUTED = "#5b6782", LINE = "#dbe5f7";

const SOURCES = ["Documents", "Databases", "Cloud storage", "Apps & APIs", "Sheets", "Email"] as const;
const TILE = { x: 64, y: 330, w: 236, h: 58, gap: 12 };
const CORE = { x: 640, y: 534, r: 124 };
const ASK = { x: 884, y: 392, w: 340, h: 318 };
const tileY = (i: number) => TILE.y + i * (TILE.h + TILE.gap);
const tileMid = (i: number) => tileY(i) + TILE.h / 2;
const sourcePath = (i: number) => {
  const x = TILE.x + TILE.w, y = tileMid(i), tx = CORE.x - CORE.r + 4, ty = CORE.y + (i - 2.5) * 30;
  return `M${x} ${y} C${x + 110} ${y} ${tx - 110} ${ty} ${tx} ${ty}`;
};
const ASK_PATH = `M${CORE.x + CORE.r + 20} ${CORE.y} L${ASK.x} ${CORE.y}`;
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

function StageLabel({ n, label, x, anchor = "start" }: { n: number; label: string; x: number; anchor?: "start" | "middle" }) {
  const width = 46 + label.length * 15;
  const left = anchor === "middle" ? x - width / 2 : x;
  return <g transform={`translate(${left} 292)`}>
    <circle r="17" cx="17" cy="0" fill={ORANGE} />
    <text x="17" y="7" textAnchor="middle" fontSize="19" fontWeight="700" fill={INK}>{n}</text>
    <text x="44" y="8" fontSize="21" fontWeight="700" letterSpacing="3" fill={BLUE_DEEP}>{label}</text>
  </g>;
}

function FlowDot({ path, tone, delay }: { path: string; tone: "blue" | "orange"; delay: number }) {
  return <>{[delay, delay + FLOW_SECONDS / 2].map(start => {
    const begin = `${start}s`, dur = `${FLOW_SECONDS}s`;
    return <g key={start} className={`lapi-banner-dot ${tone}`} opacity={0}>
      <circle r="9" fill={tone === "blue" ? "#93c5fd" : ORANGE} opacity={0.45} />
      <circle r="4" fill={tone === "blue" ? BLUE : "#f97316"} />
      <animateMotion dur={dur} begin={begin} repeatCount="indefinite" path={path} />
      <animate attributeName="opacity" values="0;1;1;0" keyTimes="0;0.12;0.82;1" dur={dur} begin={begin} repeatCount="indefinite" />
    </g>;
  })}</>;
}

/** The Connect -> Unify -> Ask story as one responsive SVG. */
export function LapiBanner({ className }: { className?: string }) {
  const orbit: ReactElement[] = [];
  for (let i = 0; i < 18; i++) {
    const a = (i / 18) * Math.PI * 2, r = CORE.r - 18;
    orbit.push(<circle key={i} cx={CORE.x + Math.cos(a) * r} cy={CORE.y + Math.sin(a) * r} r={i % 3 ? 3 : 4.5}
      fill={i % 3 ? "#ffffff" : ORANGE} opacity={i % 3 ? 0.75 : 1} />);
  }
  return <svg className={className} viewBox="0 0 1280 900" role="img" aria-label="Lapi: connect your data, unify it into one knowledge base, and ask"
    fontFamily="Inter, ui-sans-serif, system-ui, sans-serif">
    <defs>
      <linearGradient id="lb-bg" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stopColor="#ffffff" /><stop offset="0.6" stopColor="#f4f8ff" /><stop offset="1" stopColor={ORANGE_SOFT} />
      </linearGradient>
      <radialGradient id="lb-core" cx="0.38" cy="0.32" r="0.8">
        <stop offset="0" stopColor="#60a5fa" /><stop offset="0.6" stopColor={BLUE} /><stop offset="1" stopColor={BLUE_DEEP} />
      </radialGradient>
      <radialGradient id="lb-glow" cx="0.5" cy="0.5" r="0.5">
        <stop offset="0" stopColor={ORANGE} stopOpacity="0.5" /><stop offset="1" stopColor={ORANGE} stopOpacity="0" />
      </radialGradient>
      <linearGradient id="lb-agent" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stopColor="#3b82f6" /><stop offset="1" stopColor={BLUE_DEEP} />
      </linearGradient>
      <clipPath id="lb-ask"><rect x={ASK.x} y={ASK.y} width={ASK.w} height={ASK.h} rx="22" /></clipPath>
      <filter id="lb-shadow" x="-20%" y="-30%" width="140%" height="170%">
        <feDropShadow dx="0" dy="6" stdDeviation="8" floodColor={BLUE} floodOpacity="0.12" />
      </filter>
    </defs>

    <rect width="1280" height="900" fill="url(#lb-bg)" />
    <g opacity="0.5" stroke={LINE} strokeWidth="1">
      {Array.from({ length: 30 }, (_, i) => <path key={`v${i}`} d={`M${i * 44} 0V900`} />)}
      {Array.from({ length: 21 }, (_, i) => <path key={`h${i}`} d={`M0 ${i * 44}H1280`} />)}
    </g>
    <circle cx="1180" cy="80" r="230" fill="url(#lb-glow)" />

    {/* Identity */}
    <image href="/lapi-wordmark.svg" x="573" y="36" width="134" height="110" />
    <text x="640" y="190" textAnchor="middle" fontSize="34" fontWeight="700" letterSpacing="1">
      <tspan fill={INK}>Connect</tspan><tspan fill={ORANGE_DEEP}> · </tspan><tspan fill={INK}>Unify</tspan><tspan fill={ORANGE_DEEP}> · </tspan><tspan fill={INK}>Ask</tspan>
    </text>
    <text x="640" y="228" textAnchor="middle" fontSize="22" fill={MUTED}>Bring data from anywhere into one unified knowledge base, then ask.</text>

    {/* Stage row */}
    <StageLabel n={1} label="CONNECT" x={TILE.x} />
    <StageLabel n={2} label="UNIFY" x={CORE.x} anchor="middle" />
    <StageLabel n={3} label="ASK" x={ASK.x} />

    {/* 1 Connect: sources stacked on the left */}
    {SOURCES.map((_, i) => <path key={`p${i}`} d={sourcePath(i)} fill="none" stroke={i % 2 ? "#bcd0fb" : "#fcd3ad"} strokeWidth="3" strokeLinecap="round" />)}
    {SOURCES.map((name, i) => <g key={name} filter="url(#lb-shadow)">
      <rect x={TILE.x} y={tileY(i)} width={TILE.w} height={TILE.h} rx="14" fill="#ffffff" stroke={LINE} strokeWidth="1.5" />
      <rect x={TILE.x} y={tileY(i) + 12} width="5" height={TILE.h - 24} rx="2.5" fill={i % 2 ? BLUE : ORANGE} />
      <circle cx={TILE.x + 40} cy={tileMid(i)} r="20" fill={i % 2 ? BLUE_SOFT : ORANGE_SOFT} />
      <g transform={`translate(${TILE.x + 40} ${tileMid(i)})`}><SourceIcon kind={name} /></g>
      <text x={TILE.x + 72} y={tileMid(i) + 7} fontSize="20" fontWeight="600" fill={INK}>{name}</text>
    </g>)}

    {/* 2 Unify: the knowledge core carries the Lapi mark */}
    <circle cx={CORE.x} cy={CORE.y} r={CORE.r + 70} fill="url(#lb-glow)" />
    <circle className="lapi-banner-ring" cx={CORE.x} cy={CORE.y} r={CORE.r + 16} fill="none" stroke={ORANGE} strokeWidth="3" strokeDasharray="6 12" />
    <circle cx={CORE.x} cy={CORE.y} r={CORE.r} fill="url(#lb-core)" />
    <g className="lapi-banner-orbit">{orbit}</g>
    <circle cx={CORE.x} cy={CORE.y} r="68" fill="#ffffff" opacity="0.16" />
    <image href="/lapi-mark.svg" x={CORE.x - 58} y={CORE.y - 58} width="116" height="116" />
    <text x={CORE.x} y={CORE.y + CORE.r + 54} textAnchor="middle" fontSize="27" fontWeight="700" fill={INK}>One unified knowledge base</text>
    <text x={CORE.x} y={CORE.y + CORE.r + 86} textAnchor="middle" fontSize="19" fill={MUTED}>Embeddings · hybrid search · reranking</text>

    {/* 3 Ask: a grounded, cited answer in a Lapi Agent chat card */}
    <path d={ASK_PATH} stroke="#fcd3ad" strokeWidth="3" strokeLinecap="round" strokeDasharray="2 9" />
    <g filter="url(#lb-shadow)">
      <rect x={ASK.x} y={ASK.y} width={ASK.w} height={ASK.h} rx="22" fill="#ffffff" stroke={LINE} strokeWidth="1.5" />
    </g>
    <g clipPath="url(#lb-ask)">
      <rect x={ASK.x} y={ASK.y} width={ASK.w} height="64" fill="url(#lb-agent)" />
      <circle cx={ASK.x + ASK.w - 24} cy={ASK.y - 8} r="48" fill={ORANGE} opacity="0.28" />
    </g>
    <image href="/lapi-mark.svg" x={ASK.x + 16} y={ASK.y + 12} width="40" height="40" />
    <text x={ASK.x + 68} y={ASK.y + 30} fontSize="18" fontWeight="700" fill="#ffffff">Lapi Agent</text>
    <text x={ASK.x + 68} y={ASK.y + 49} fontSize="13" fill="#dbeafe">Answers with citations</text>
    <rect x={ASK.x + ASK.w - 104} y={ASK.y + 20} width="88" height="24" rx="12" fill="#ffffff" fillOpacity="0.16" stroke="#ffffff" strokeOpacity="0.4" />
    <circle cx={ASK.x + ASK.w - 90} cy={ASK.y + 32} r="4" fill={ORANGE} />
    <text x={ASK.x + ASK.w - 80} y={ASK.y + 36.5} fontSize="12.5" fontWeight="600" fill="#ffffff">3 sources</text>

    {/* The question: a right-aligned chat bubble */}
    <rect x={QX} y={ASK.y + 80} width={QUESTION.w} height={QUESTION.h} rx="20" fill={BLUE} />
    <rect x={QX + QUESTION.w - 20} y={ASK.y + 80 + QUESTION.h - 20} width="20" height="20" rx="5" fill={BLUE} />
    <text x={QX + QUESTION.w / 2} y={ASK.y + 105} textAnchor="middle" fontSize="16" fontWeight="600" fill="#ffffff">What changed in renewals?</text>

    {/* The answer: Lapi's accent bar and numbered citations */}
    <rect x={ASK.x + 16} y={ASK.y + 136} width={ASK.w - 32} height="86" rx="16" fill="#f6f9ff" stroke={LINE} />
    <rect x={ASK.x + 28} y={ASK.y + 150} width="4" height="58" rx="2" fill={ORANGE} />
    <text x={ASK.x + 44} y={ASK.y + 170} fontSize="17" fill={INK}>Three contracts moved to</text>
    <text x={ASK.x + 44} y={ASK.y + 196} fontSize="17" fill={INK}><tspan fontWeight="700" fill={BLUE_DEEP}>net-60</tspan> payment terms.</text>
    {CITATIONS.map((_, i) => <g key={i}>
      <circle cx={ASK.x + 236 + i * 22} cy={ASK.y + 190} r="9.5" fill={ORANGE_SOFT} stroke={ORANGE} />
      <text x={ASK.x + 236 + i * 22} y={ASK.y + 194} textAnchor="middle" fontSize="11" fontWeight="700" fill={ORANGE_DEEP}>{i + 1}</text>
    </g>)}

    {/* Sources: the same numbers, tying the answer back to Connect */}
    <text x={ASK.x + 18} y={ASK.y + 246} fontSize="11.5" fontWeight="700" letterSpacing="2" fill={MUTED}>SOURCES</text>
    {CITATIONS.map((label, i) => <g key={label} transform={`translate(${ASK.x + 16 + chipX(i)} ${ASK.y + 256})`}>
      <rect width={chipWidth(label)} height="28" rx="14" fill="#ffffff" stroke={LINE} />
      <circle cx="15" cy="14" r="9" fill={ORANGE_SOFT} stroke={ORANGE} />
      <text x="15" y="18" textAnchor="middle" fontSize="11" fontWeight="700" fill={ORANGE_DEEP}>{i + 1}</text>
      <text x="30" y="19" fontSize="14" fontWeight="600" fill={INK}>{label}</text>
    </g>)}
    <path d={`M${ASK.x + 19} ${ASK.y + 300}l4 4 8-9`} fill="none" stroke={BLUE} strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
    <text x={ASK.x + 38} y={ASK.y + 304} fontSize="13" fill={MUTED}>Verified against your data</text>

    <text x="640" y="862" textAnchor="middle" fontSize="17" fontWeight="600" letterSpacing="4" fill={MUTED}>
      YOUR DATA · ONE KNOWLEDGE BASE · <tspan fill={ORANGE_DEEP}>CITED ANSWERS</tspan>
    </text>

    <g className="lapi-banner-flow">
      {SOURCES.map((_, i) => <FlowDot key={i} path={sourcePath(i)} tone={i % 2 ? "blue" : "orange"} delay={i * 0.35} />)}
      <FlowDot path={ASK_PATH} tone="orange" delay={0.6} />
    </g>
  </svg>;
}
