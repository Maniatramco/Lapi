import type { ReactNode } from "react";
import { LapiBanner } from "./lapi-banner";

const PILLARS = ["Any data source", "One knowledge base", "Cited answers", "Secure by design", "Governed access"];

/** Keep the sign-in task first in reading order at every viewport size. */
export function SignInLayout({ children }: { children: ReactNode }) {
  return <main className="login-shell">
    <div className="login-ambient" aria-hidden="true"><span className="login-glow cyan" /><span className="login-glow violet" /></div>
    <div className="login-layout">
      <section className="login-card" aria-labelledby="login-heading">
        <div className="login-identity">
          <img src="/lapi-mark.svg" alt="" width={48} height={48} />
          <div><p className="login-brand-name">Lapi</p>
            <p className="login-brand-tagline">Connect · Vectorize · Ask</p></div>
        </div>
        {children}
        <div className="login-pillars">
          <span className="login-pillars-label">Built for</span>
          <div className="login-pillars-window"><ul className="login-pillars-track">
            {PILLARS.map(pillar => <li key={pillar}>{pillar}</li>)}
          </ul></div>
        </div>
      </section>
      <section className="login-story" aria-label="Lapi platform artwork">
        <figure className="login-illustration">
          <LapiBanner className="login-artwork" />
        </figure>
      </section>
    </div>
  </main>;
}
