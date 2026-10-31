"use client";
import {AgentLogo} from './agent-logo';
import './lapi-bot-button.css';

/** The Help Bot's face: the Lapi robot waving, with its "?" bubble, so it reads apart from the Agent.
 * It sits in the phone tab bar and at the bottom of the side menu, never floating over the screen. */
export function HelpBotIcon({size=24}:{size?:number}){
 return <span className="lapi-bot-icon" aria-hidden="true"><AgentLogo size={size} variant="help"/></span>;
}

/** The side-menu entry on computers. */
export function HelpBotMenuButton({onOpen}:{onOpen:()=>void}){
 return <button type="button" className="sidebar-help-bot" onClick={onOpen}><HelpBotIcon size={30}/><span><strong>Help from Lapi</strong><small>Set up, pull out data, or email Mani</small></span></button>;
}
