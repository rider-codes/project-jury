"use client";

import { useEffect, useState } from "react";

/** Light or dark Cobalt theme: ?theme=dark|light wins, then the visitor's saved choice, then light. */
export function useTheme(): [boolean, (dark: boolean) => void] {
  const [dark, setDark] = useState(false);
  useEffect(() => {
    const q = new URLSearchParams(window.location.search).get("theme");
    let saved: string | null = null;
    try { saved = window.localStorage.getItem("jury-theme"); } catch {}
    setDark((q ?? saved) === "dark");
  }, []);
  const pick = (d: boolean) => {
    setDark(d);
    try { window.localStorage.setItem("jury-theme", d ? "dark" : "light"); } catch {}
  };
  return [dark, pick];
}

export function ThemeSwitch({ dark, onPick }: { dark: boolean; onPick: (dark: boolean) => void }) {
  return (
    <button type="button" className="theme-btn" onClick={() => onPick(!dark)}
            aria-label={dark ? "Switch to light mode" : "Switch to dark mode"} title={dark ? "Light mode" : "Dark mode"}>
      {dark ? (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
          <circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
        </svg>
      ) : (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z" />
        </svg>
      )}
    </button>
  );
}
