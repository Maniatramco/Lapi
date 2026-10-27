import type { ReactNode } from "react";
import { Lock, Quote, Server, ShieldCheck } from "lucide-react";
import { LapiBanner } from "./lapi-banner";

const PROOF = [
  { icon: Quote, title: "Cited answers", text: "Every answer links to the passages it came from." },
  { icon: ShieldCheck, title: "Governed access", text: "People only search the datasets they may see." },
  { icon: Server, title: "Self-hosted", text: "Runs on your own infrastructure, with keys you control." },
];

/** Keep the sign-in task first in reading order at every viewport size. */
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
          <p className="login-story-eyebrow">One knowledge base for everything you know</p>
          <h2 className="login-story-title">Ask your data.<span>Get answers you can trust.</span></h2>
          <p className="login-story-lead">Lapi connects your documents, databases and apps into one knowledge base, then answers
            in plain language with the sources to check.</p>
          <LapiBanner className="login-artwork" />
          <ul className="login-proof">
            {PROOF.map(({ icon: Icon, title, text }) => <li key={title}>
              <Icon size={20} aria-hidden="true" />
              <div><strong>{title}</strong><span>{text}</span></div>
            </li>)}
          </ul>
        </div>
      </section>
    </div>
  </main>;
}
