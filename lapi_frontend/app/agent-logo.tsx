import './agent-logo.css';

/** Two Lapi robots, drawn inline so they can move. The Agent is the visor robot: a square head whose light
 * bar scans left and right inside a dark visor, hovering with a glowing antenna. The Help Bot is the friendly
 * round-headed robot that blinks, waves and holds a "?" bubble. Both still under prefers-reduced-motion.
 * Gradient and clip ids are shared, so many copies on one page are fine. */
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
  <defs><linearGradient id="lapi-robo-blue" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#3b82f6"/><stop offset="1" stopColor="#1d4ed8"/></linearGradient><clipPath id="lapi-robo-visor"><rect x="15" y="21" width="34" height="14" rx="7"/></clipPath></defs>
  <g className="lapi-robo">
   <rect x="20" y="46" width="24" height="12" rx="5" fill="url(#lapi-robo-blue)"/>
   <rect x="12" y="48" width="6" height="8" rx="3" fill="#1d4ed8"/>
   <rect x="46" y="48" width="6" height="8" rx="3" fill="#1d4ed8"/>
   <g className="lapi-robo-head">
    <rect x="29" y="8" width="6" height="5" rx="2" fill="#1d4ed8"/>
    <circle className="lapi-robo-light" cx="32" cy="6" r="3" fill="#fdba74"/>
    <rect x="9" y="12" width="46" height="34" rx="9" fill="url(#lapi-robo-blue)"/>
    <rect x="15" y="21" width="34" height="14" rx="7" fill="#14213d"/>
    <g clipPath="url(#lapi-robo-visor)"><rect className="lapi-robo-scan" x="22" y="25" width="20" height="6" rx="3" fill="#93c5fd"/></g>
    <rect x="24" y="39" width="16" height="3" rx="1.5" fill="#93c5fd"/>
   </g>
  </g>
 </svg>;
}
