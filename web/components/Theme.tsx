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
    <div className="sc-switch" role="group" aria-label="Colour theme">
      <button type="button" aria-pressed={!dark} onClick={() => onPick(false)}>Light</button>
      <button type="button" aria-pressed={dark} onClick={() => onPick(true)}>Dark</button>
    </div>
  );
}
