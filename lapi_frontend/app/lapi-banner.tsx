import type { ReactElement } from "react";

/* Sign-in banner: Connect -> Vectorize -> Ask, flowing left to right in the Lapi palette.
   Drawn in a 1280x900 space; the Lapi mark sits at the centre of the knowledge core. */

const BLUE = "#2563eb", BLUE_DEEP = "#1d4ed8", BLUE_SOFT = "#eaf1ff", ORANGE = "#fdba74",
  ORANGE_DEEP = "#c2410c", ORANGE_SOFT = "#fff4e8", INK = "#14213d", MUTED = "#5b6782", LINE = "#dbe5f7";

const SOURCES = ["Documents", "Databases", "Cloud storage", "Apps & APIs", "Sheets", "Email"] as const;
const TILE = { x: 64, y: 330, w: 236, h: 58, gap: 12 };
const CORE = { x: 640, y: 534, r: 124 };
const ASK = { x: 884, y: 410, w: 332, h: 250 };
const tileY = (i: number) => TILE.y + i * (TILE.h + TILE.gap);
const tileMid = (i: number) => tileY(i) + TILE.h / 2;
const sourcePath = (i: number) => {
  const x = TILE.x + TILE.w, y = tileMid(i), tx = CORE.x - CORE.r + 4, ty = CORE.y + (i - 2.5) * 30;
  return `M${x} ${y} C${x + 110} ${y} ${tx - 110} ${ty} ${tx} ${ty}`;
};
const ASK_PATH = `M${CORE.x + CORE.r + 20} ${CORE.y} L${ASK.x} ${CORE.y}`;
const FLOW_SECONDS = 2.8;
const CITATIONS = [{ label: "Contracts.pdf", x: 0 }, { label: "CRM", x: 150 }, { label: "Drive", x: 210 }];

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

/** The Connect -> Vectorize -> Ask story as one responsive SVG. */
export function LapiBanner({ className }: { className?: string }) {
  const orbit: ReactElement[] = [];
  for (let i = 0; i < 18; i++) {
    const a = (i / 18) * Math.PI * 2, r = CORE.r - 18;
    orbit.push(<circle key={i} cx={CORE.x + Math.cos(a) * r} cy={CORE.y + Math.sin(a) * r} r={i % 3 ? 3 : 4.5}
      fill={i % 3 ? "#ffffff" : ORANGE} opacity={i % 3 ? 0.75 : 1} />);
  }
  return <svg className={className} viewBox="0 0 1280 900" role="img" aria-label="Lapi: connect your data, vectorize it into one knowledge base, and ask"
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
      <tspan fill={INK}>Connect</tspan><tspan fill={ORANGE_DEEP}> · </tspan><tspan fill={INK}>Vectorize</tspan><tspan fill={ORANGE_DEEP}> · </tspan><tspan fill={INK}>Ask</tspan>
    </text>
    <text x="640" y="228" textAnchor="middle" fontSize="22" fill={MUTED}>Bring data from anywhere into one unified knowledge base, then ask.</text>

    {/* Stage row */}
    <StageLabel n={1} label="CONNECT" x={TILE.x} />
    <StageLabel n={2} label="VECTORIZE" x={CORE.x} anchor="middle" />
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

    {/* 2 Vectorize: the knowledge core carries the Lapi mark */}
    <circle cx={CORE.x} cy={CORE.y} r={CORE.r + 70} fill="url(#lb-glow)" />
    <circle className="lapi-banner-ring" cx={CORE.x} cy={CORE.y} r={CORE.r + 16} fill="none" stroke={ORANGE} strokeWidth="3" strokeDasharray="6 12" />
    <circle cx={CORE.x} cy={CORE.y} r={CORE.r} fill="url(#lb-core)" />
    <g className="lapi-banner-orbit">{orbit}</g>
    <circle cx={CORE.x} cy={CORE.y} r="68" fill="#ffffff" opacity="0.16" />
    <image href="/lapi-mark.svg" x={CORE.x - 58} y={CORE.y - 58} width="116" height="116" />
    <text x={CORE.x} y={CORE.y + CORE.r + 54} textAnchor="middle" fontSize="27" fontWeight="700" fill={INK}>One unified knowledge base</text>
    <text x={CORE.x} y={CORE.y + CORE.r + 86} textAnchor="middle" fontSize="19" fill={MUTED}>Embeddings · hybrid search · reranking</text>

    {/* 3 Ask: a cited answer on the right */}
    <path d={ASK_PATH} stroke="#fcd3ad" strokeWidth="3" strokeLinecap="round" strokeDasharray="2 9" />
    <g filter="url(#lb-shadow)">
      <rect x={ASK.x} y={ASK.y} width={ASK.w} height={ASK.h} rx="22" fill="#ffffff" stroke={LINE} strokeWidth="1.5" />
    </g>
    <rect x={ASK.x + 46} y={ASK.y + 24} width={ASK.w - 66} height="44" rx="22" fill={BLUE} />
    <text x={ASK.x + 46 + (ASK.w - 66) / 2} y={ASK.y + 53} textAnchor="middle" fontSize="18" fontWeight="600" fill="#ffffff">What changed in renewals?</text>
    <image href="/lapi-agent.svg" x={ASK.x + 20} y={ASK.y + 92} width="34" height="34" />
    <text x={ASK.x + 64} y={ASK.y + 114} fontSize="17" fontWeight="700" fill={INK}>Lapi Agent</text>
    <rect x={ASK.x + 20} y={ASK.y + 138} width="4" height="52" rx="2" fill={ORANGE} />
    <text x={ASK.x + 36} y={ASK.y + 158} fontSize="18" fill={INK}>Three contracts moved</text>
    <text x={ASK.x + 36} y={ASK.y + 184} fontSize="18" fill={INK}>to net-60 terms.</text>
    {CITATIONS.map(({ label, x }) => <g key={label}>
      <rect x={ASK.x + 20 + x} y={ASK.y + 204} width={label.length * 9.5 + 22} height="28" rx="14" fill={ORANGE_SOFT} stroke={ORANGE} />
      <text x={ASK.x + 31 + x} y={ASK.y + 223} fontSize="15" fontWeight="600" fill={ORANGE_DEEP}>{label}</text>
    </g>)}

    <text x="640" y="862" textAnchor="middle" fontSize="17" fontWeight="600" letterSpacing="4" fill={MUTED}>
      YOUR DATA · ONE KNOWLEDGE BASE · <tspan fill={ORANGE_DEEP}>CITED ANSWERS</tspan>
    </text>

    <g className="lapi-banner-flow">
      {SOURCES.map((_, i) => <FlowDot key={i} path={sourcePath(i)} tone={i % 2 ? "blue" : "orange"} delay={i * 0.35} />)}
      <FlowDot path={ASK_PATH} tone="orange" delay={0.6} />
    </g>
  </svg>;
}
