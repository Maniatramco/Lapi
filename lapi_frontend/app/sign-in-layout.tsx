import type { ReactNode } from "react";
import Image from "next/image";
import { LapiBanner } from "./lapi-banner";

const PILLARS = ["Data from anywhere", "One unified knowledge base", "Answers with sources", "Secure by design", "Governed and compliant"];

/** Keep the sign-in task first in reading order at every viewport size. */
export function SignInLayout({ children }: { children: ReactNode }) {
  return <main className="login-shell">
    <div className="login-ambient" aria-hidden="true"><span className="login-glow cyan" /><span className="login-glow violet" /></div>
    <div className="login-layout">
      <section className="login-card" aria-labelledby="login-heading">
        <div className="login-identity">
          <Image src="/lapi-platform-logo.png" alt="" width={48} height={48} />
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
