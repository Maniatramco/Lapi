import type { ReactNode } from "react";
import { Lock } from "lucide-react";
import { LapiBanner } from "./lapi-banner";

/** Keep the sign-in task first in reading order at every viewport size.
 * One blended background runs behind the Connect · Unify · Ask diagram and the glass sign-in card. */
export function SignInLayout({ children }: { children: ReactNode }) {
  return <main className="login-shell">
    <div className="login-layout">
      <section className="login-card" aria-labelledby="login-heading">
        <div className="login-identity">
          <img src="/lapi-mark.svg" alt="" width={48} height={48} />
          <div><p className="login-brand-name">Lapi</p>
            <p className="login-brand-tagline">Connect · Unify · Ask</p></div>
        </div>
        {children}
        <p className="login-trust"><Lock size={15} aria-hidden="true" />Secure sign-in. Sessions end after 12 hours.</p>
      </section>
      <section className="login-story" aria-label="Lapi platform artwork">
        <div className="login-story-panel">
          <h2 className="login-story-title">Connect. <span className="login-story-unify">Unify.</span> <span className="login-story-ask">Ask.</span></h2>
          <p className="login-story-lead">Lapi connects your documents, databases and apps into one knowledge base, then answers
            in plain language with the sources to check.</p>
          <LapiBanner className="login-artwork" />
        </div>
      </section>
    </div>
  </main>;
}
