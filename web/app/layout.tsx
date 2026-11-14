import type { Metadata } from "next";
import localFont from "next/font/local";
import "./globals.css";
import "./showcase.css";
import "./showcase-theme.css";

// fonts ship with the app (no download at build time): Plus Jakarta Sans (variable weight) and
// JetBrains Mono 500, both SIL Open Font License, latin subset
const sans = localFont({ src: "./fonts/PlusJakartaSans-latin.woff2", weight: "200 800", variable: "--font-sans", display: "swap" });
const mono = localFont({ src: "./fonts/JetBrainsMono-latin.woff2", weight: "500", variable: "--font-mono", display: "swap" });

export const metadata: Metadata = {
  title: "Project Jury",
  description: "A panel of AI reviewers tells you whether your project is useful, with evidence.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${sans.variable} ${mono.variable}`}>
      <body>{children}</body>
    </html>
  );
}
