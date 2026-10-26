import './agent-logo.css';

/** Shared Agent identity uses the Lapi LP monogram; workflow status icons stay separate. */
export function AgentLogo({size=24,label=''}:{size?:number;label?:string}){
 return <img className="lapi-agent-logo" src="/lapi-mark.svg" width={size} height={size} alt={label} aria-hidden={label?undefined:true}/>;
}
