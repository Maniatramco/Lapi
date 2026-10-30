import './agent-logo.css';

/** Two Lapi marks, drawn inline so they can move. The Agent is the Reader spark: a page in the Lapi tile whose
 * lines light up as an orange spark reads down them, then flares when the answer is ready. The Help Bot is the
 * friendly robot that blinks, waves and holds a "?" bubble. Both still under prefers-reduced-motion. Gradient
 * ids are shared, so many copies on one page are fine. */
export function AgentLogo({size=24,label='',variant='agent'}:{size?:number;label?:string;variant?:'agent'|'help'}){
 const common={className:`lapi-agent-logo is-${variant}`,viewBox:'0 0 64 64',width:size,height:size,role:label?'img':undefined,'aria-label':label||undefined,'aria-hidden':label?undefined:true,focusable:'false'} as const;
 if(variant==='help')return <svg {...common}>
  <defs><linearGradient id="lapi-robo-blue" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#3b82f6"/><stop offset="1" stopColor="#1d4ed8"/></linearGradient></defs>
  <g className="lapi-robo">
   <rect x="22" y="45" width="20" height="13" rx="6.5" fill="url(#lapi-robo-blue)"/>
   <circle cx="32" cy="51.5" r="2.4" fill="#fdba74"/>
   <rect x="14" y="47" width="6" height="9" rx="3" fill="#1d4ed8"/>
   <g className="lapi-robo-arm"><rect x="44" y="40" width="6" height="16" rx="3" fill="#1d4ed8"/><circle cx="47" cy="39" r="3.2" fill="#fdba74"/></g>
   <g className="lapi-robo-head">
    <line x1="32" y1="7" x2="32" y2="12" stroke="#1d4ed8" strokeWidth="2.4" strokeLinecap="round"/>
    <circle className="lapi-robo-light" cx="32" cy="5.2" r="3.4" fill="#fdba74"/>
    <rect x="7" y="24" width="5" height="11" rx="2.5" fill="#1d4ed8"/>
    <rect x="52" y="24" width="5" height="11" rx="2.5" fill="#1d4ed8"/>
    <rect x="11" y="12" width="42" height="33" rx="13" fill="url(#lapi-robo-blue)"/>
    <rect x="16" y="18" width="32" height="23" rx="10" fill="#ffffff"/>
    <ellipse className="lapi-robo-eye" cx="25.5" cy="29" rx="3.4" ry="4" fill="#1d4ed8"/>
    <ellipse className="lapi-robo-eye" cx="38.5" cy="29" rx="3.4" ry="4" fill="#1d4ed8"/>
    <circle cx="26.8" cy="27.4" r="1.1" fill="#ffffff"/>
    <circle cx="39.8" cy="27.4" r="1.1" fill="#ffffff"/>
    <path d="M25 37.5 Q32 43 39 37.5" fill="none" stroke="#1d4ed8" strokeWidth="2" strokeLinecap="round"/>
   </g>
   <g className="lapi-robo-bubble"><path d="M48 2H60A4 4 0 0 1 64 6V14A4 4 0 0 1 60 18H53L48 22V18A4 4 0 0 1 44 14V6A4 4 0 0 1 48 2Z" fill="#fdba74"/><text x="54" y="14.6" textAnchor="middle" fontFamily="system-ui, sans-serif" fontSize="11" fontWeight="800" fill="#14213d">?</text></g>
  </g>
 </svg>;
 return <svg {...common}>
  <defs><linearGradient id="lapi-reader-blue" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#3b82f6"/><stop offset="1" stopColor="#1d4ed8"/></linearGradient></defs>
  <g className="lapi-reader">
   <rect x="6" y="4" width="52" height="56" rx="14" fill="url(#lapi-reader-blue)"/>
   <path d="M19 12H38L47 21V49A3 3 0 0 1 44 52H19A3 3 0 0 1 16 49V15A3 3 0 0 1 19 12Z" fill="#ffffff"/>
   <path d="M38 12V21H47Z" fill="#c7d7fb"/>
   <rect className="lapi-reader-line" x="21" y="20" width="12" height="3" rx="1.5" fill="#c7d7fb"/>
   <rect className="lapi-reader-line" x="21" y="28" width="22" height="3" rx="1.5" fill="#c7d7fb"/>
   <rect className="lapi-reader-line" x="21" y="36" width="18" height="3" rx="1.5" fill="#c7d7fb"/>
   <rect className="lapi-reader-line" x="21" y="44" width="22" height="3" rx="1.5" fill="#c7d7fb"/>
   <g transform="translate(40 14)"><path className="lapi-reader-spark" d="M0 -6.5 Q1.5 -1.5 6.5 0 Q1.5 1.5 0 6.5 Q-1.5 1.5 -6.5 0 Q-1.5 -1.5 0 -6.5Z" fill="#fb923c"/></g>
  </g>
 </svg>;
}
