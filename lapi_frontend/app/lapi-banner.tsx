import type { ReactElement } from "react";

/* Sign-in banner: Connect -> Vectorize -> Ask, in the Lapi white / blue / light-orange palette.
   Drawn in a 906x1280 space so it keeps the banner's portrait proportions. */

const BLUE = "#2563eb", BLUE_DEEP = "#1d4ed8", BLUE_SOFT = "#eaf1ff", ORANGE = "#fdba74",
  ORANGE_DEEP = "#c2410c", ORANGE_SOFT = "#fff4e8", INK = "#14213d", MUTED = "#5b6782", LINE = "#dbe5f7";

const TILE_W = 118, TILE_GAP = 14, TILE_Y = 448, TILE_H = 132;
const TILE_X0 = (906 - (6 * TILE_W + 5 * TILE_GAP)) / 2;
const CORE = { x: 453, y: 800, r: 104 };
const SOURCES = ["Documents", "Databases", "Cloud", "Apps & APIs", "Sheets", "Email"] as const;
const tileX = (i: number) => TILE_X0 + i * (TILE_W + TILE_GAP);
const tileCenter = (i: number) => tileX(i) + TILE_W / 2;
const sourcePath = (i: number) => {
  const x = tileCenter(i), y = TILE_Y + TILE_H, tx = CORE.x + (i - 2.5) * 26, ty = CORE.y - CORE.r + 6;
  return `M${x} ${y} C${x} ${y + 70} ${tx} ${ty - 80} ${tx} ${ty}`;
};
const ASK_PATH = `M${CORE.x} 1014 L${CORE.x} 1070`;
const FLOW_SECONDS = 2.8;
const CITATIONS = [{ label: "Contracts.pdf", x: 150 }, { label: "CRM", x: 316 }, { label: "Drive", x: 382 }];

function SourceIcon({ kind }: { kind: (typeof SOURCES)[number] }) {
  const s = { fill: "none", stroke: BLUE, strokeWidth: 3, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  switch (kind) {
    case "Documents":
      return <g {...s}><path d="M-13 -19h17l9 9v29h-26z" /><path d="M4 -19v9h9" /><path d="M-7 0h14M-7 8h14" stroke={ORANGE_DEEP} /></g>;
    case "Databases":
      return <g {...s}><ellipse cx="0" cy="-13" rx="16" ry="6" /><path d="M-16 -13v26c0 3.3 7.2 6 16 6s16-2.7 16-6v-26" /><path d="M-16 0c0 3.3 7.2 6 16 6s16-2.7 16-6" stroke={ORANGE_DEEP} /></g>;
    case "Cloud":
      return <g {...s}><path d="M-12 12h25a10 10 0 0 0 0-20 14 14 0 0 0-27-3A9 9 0 0 0-12 12z" /><path d="M0 -2v12M-5 5l5 5 5-5" stroke={ORANGE_DEEP} /></g>;
    case "Apps & APIs":
      return <g {...s}><path d="M-8 -12l-11 12 11 12M8 -12l11 12-11 12" /><path d="M4 -16l-8 32" stroke={ORANGE_DEEP} /></g>;
    case "Sheets":
      return <g {...s}><rect x="-17" y="-15" width="34" height="30" rx="3" /><path d="M-17 -5h34M-17 5h34M-5 -15v30" /><path d="M-17 -10h34" stroke={ORANGE_DEEP} strokeWidth={5} opacity={0.5} /></g>;
    case "Email":
      return <g {...s}><rect x="-17" y="-12" width="34" height="24" rx="3" /><path d="M-17 -10l17 13 17-13" stroke={ORANGE_DEEP} /></g>;
    default:
      return null;
  }
}

function StageLabel({ n, label, y }: { n: number; label: string; y: number }) {
  return <g transform={`translate(64 ${y})`}>
    <circle r="17" cx="17" cy="0" fill={ORANGE} />
    <text x="17" y="7" textAnchor="middle" fontSize="20" fontWeight="700" fill={INK}>{n}</text>
    <text x="46" y="8" fontSize="22" fontWeight="700" letterSpacing="3" fill={BLUE_DEEP}>{label}</text>
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
  const grid: ReactElement[] = [];
  for (let r = -3; r <= 3; r++) for (let c = -3; c <= 3; c++) {
    const d = Math.hypot(r, c);
    if (d > 3.3) continue;
    const warm = (r * 7 + c * 3 + 21) % 5 === 0;
    grid.push(<circle key={`${r}${c}`} cx={CORE.x + c * 22} cy={CORE.y + r * 22} r={warm ? 4.5 : 3.5}
      fill={warm ? ORANGE : "#ffffff"} opacity={warm ? 1 : 0.9 - d * 0.12} />);
  }
  return <svg className={className} viewBox="0 0 906 1280" role="img" aria-label="Lapi: connect your data, vectorize it into one knowledge base, and ask"
    fontFamily="Inter, ui-sans-serif, system-ui, sans-serif">
    <defs>
      <linearGradient id="lb-bg" x1="0" y1="0" x2="0.35" y2="1">
        <stop offset="0" stopColor="#ffffff" /><stop offset="0.55" stopColor="#f4f8ff" /><stop offset="1" stopColor={ORANGE_SOFT} />
      </linearGradient>
      <radialGradient id="lb-core" cx="0.38" cy="0.32" r="0.8">
        <stop offset="0" stopColor="#60a5fa" /><stop offset="0.6" stopColor={BLUE} /><stop offset="1" stopColor={BLUE_DEEP} />
      </radialGradient>
      <radialGradient id="lb-glow" cx="0.5" cy="0.5" r="0.5">
        <stop offset="0" stopColor={ORANGE} stopOpacity="0.55" /><stop offset="1" stopColor={ORANGE} stopOpacity="0" />
      </radialGradient>
      <filter id="lb-shadow" x="-20%" y="-20%" width="140%" height="160%">
        <feDropShadow dx="0" dy="8" stdDeviation="10" floodColor={BLUE} floodOpacity="0.12" />
      </filter>
    </defs>

    <rect width="906" height="1280" fill="url(#lb-bg)" />
    <g opacity="0.5" stroke={LINE} strokeWidth="1">
      {Array.from({ length: 21 }, (_, i) => <path key={`v${i}`} d={`M${i * 44} 0V1280`} />)}
      {Array.from({ length: 30 }, (_, i) => <path key={`h${i}`} d={`M0 ${i * 44}H906`} />)}
    </g>
    <circle cx="820" cy="90" r="190" fill="url(#lb-glow)" />

    {/* Identity */}
    <image href="/lapi-platform-logo.png" x="408" y="44" width="90" height="90" />
    <text x="453" y="250" textAnchor="middle" fontSize="118" fontWeight="800" letterSpacing="-4" fill={BLUE_DEEP}>Lapi</text>
    <text x="453" y="306" textAnchor="middle" fontSize="34" fontWeight="700" letterSpacing="1">
      <tspan fill={INK}>Connect</tspan><tspan fill={ORANGE_DEEP}> · </tspan><tspan fill={INK}>Vectorize</tspan><tspan fill={ORANGE_DEEP}> · </tspan><tspan fill={INK}>Ask</tspan>
    </text>
    <text x="453" y="350" textAnchor="middle" fontSize="23" fill={MUTED}>Bring data from anywhere into one unified knowledge base.</text>

    {/* 1 Connect */}
    <StageLabel n={1} label="CONNECT" y={410} />
    {SOURCES.map((name, i) => <g key={name} filter="url(#lb-shadow)">
      <rect x={tileX(i)} y={TILE_Y} width={TILE_W} height={TILE_H} rx="18" fill="#ffffff" stroke={LINE} strokeWidth="1.5" />
      <rect x={tileX(i)} y={TILE_Y} width={TILE_W} height="6" rx="3" fill={i % 2 ? BLUE : ORANGE} />
      <circle cx={tileCenter(i)} cy={TILE_Y + 52} r="31" fill={i % 2 ? BLUE_SOFT : ORANGE_SOFT} />
      <g transform={`translate(${tileCenter(i)} ${TILE_Y + 52})`}><SourceIcon kind={name} /></g>
      <text x={tileCenter(i)} y={TILE_Y + 112} textAnchor="middle" fontSize="19" fontWeight="600" fill={INK}>{name}</text>
    </g>)}
    {SOURCES.map((_, i) => <path key={`p${i}`} d={sourcePath(i)} fill="none" stroke={i % 2 ? "#bcd0fb" : "#fcd3ad"} strokeWidth="3" strokeLinecap="round" />)}

    {/* 2 Vectorize */}
    <StageLabel n={2} label="VECTORIZE" y={690} />
    <circle cx={CORE.x} cy={CORE.y} r={CORE.r + 58} fill="url(#lb-glow)" />
    <circle className="lapi-banner-ring" cx={CORE.x} cy={CORE.y} r={CORE.r + 16} fill="none" stroke={ORANGE} strokeWidth="3" strokeDasharray="6 12" />
    <circle cx={CORE.x} cy={CORE.y} r={CORE.r} fill="url(#lb-core)" />
    <g stroke="#ffffff" strokeOpacity="0.35" strokeWidth="1.5">
      <path d={`M${CORE.x - 66} ${CORE.y - 22}L${CORE.x - 22} ${CORE.y - 44}L${CORE.x + 22} ${CORE.y}L${CORE.x + 66} ${CORE.y - 22}`} fill="none" />
      <path d={`M${CORE.x - 44} ${CORE.y + 44}L${CORE.x} ${CORE.y + 22}L${CORE.x + 44} ${CORE.y + 44}`} fill="none" />
    </g>
    {grid}
    <text x={CORE.x} y={CORE.y + CORE.r + 62} textAnchor="middle" fontSize="28" fontWeight="700" fill={INK}>One unified knowledge base</text>
    <text x={CORE.x} y={CORE.y + CORE.r + 94} textAnchor="middle" fontSize="20" fill={MUTED}>Embeddings · hybrid search · reranking</text>

    {/* 3 Ask */}
    <path d={ASK_PATH} stroke="#fcd3ad" strokeWidth="3" strokeLinecap="round" strokeDasharray="2 9" />
    <StageLabel n={3} label="ASK" y={1046} />
    <g filter="url(#lb-shadow)">
      <rect x="112" y="1074" width="682" height="134" rx="22" fill="#ffffff" stroke={LINE} strokeWidth="1.5" />
    </g>
    <rect x="456" y="1092" width="318" height="40" rx="20" fill={BLUE} />
    <text x="615" y="1118" textAnchor="middle" fontSize="19" fontWeight="600" fill="#ffffff">What changed in our renewals?</text>
    <rect x="132" y="1146" width="4" height="46" rx="2" fill={ORANGE} />
    <text x="150" y="1164" fontSize="19" fill={INK}>Three contracts moved to net-60 terms.</text>
    {CITATIONS.map(({ label, x }) => <g key={label}>
      <rect x={x} y="1174" width={label.length * 10 + 26} height="26" rx="13" fill={ORANGE_SOFT} stroke={ORANGE} />
      <text x={x + 13} y="1192" fontSize="15" fontWeight="600" fill={ORANGE_DEEP}>{label}</text>
    </g>)}

    <text x="453" y="1252" textAnchor="middle" fontSize="17" fontWeight="600" letterSpacing="4" fill={MUTED}>
      YOUR DATA · ONE KNOWLEDGE BASE · <tspan fill={ORANGE_DEEP}>CITED ANSWERS</tspan>
    </text>

    <g className="lapi-banner-flow">
      {SOURCES.map((_, i) => <FlowDot key={i} path={sourcePath(i)} tone={i % 2 ? "blue" : "orange"} delay={i * 0.35} />)}
      <FlowDot path={ASK_PATH} tone="orange" delay={0.6} />
    </g>
  </svg>;
}
