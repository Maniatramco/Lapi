import type { Metadata } from "next";
import "./globals.css";
import "./responsive.css";
import "./readability.css";
import "./screen-heading.css";
import "./workspace-region.css";
import "./typography.css";
import "./workspace-tools.css";
import "./action-button.css";
import "./review-layout.css";
import "./sign-in.css";
import "./buttons.css";
import "./lapi-theme.css";
import "./login.css";
export const metadata: Metadata = {
  title: "Lapi · AI Data Platform",
  description: "AI data platform for collections, agents, chat, extraction, and review.",
  icons: { icon: [{ url: "/favicon.ico?v=lp2", sizes: "any" }, { url: "/lapi-agent.svg?v=lp2", type: "image/svg+xml" }], apple: "/lapi-mark-180.png?v=lp2" },
};
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <head><link rel="preload" href="/lapi_assets/lapi_fonts/inter-variable.woff2" as="font" type="font/woff2" crossOrigin="anonymous" /></head>
      <body>{children}</body>
    </html>
  );
}
