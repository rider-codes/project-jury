"use client";

import { useEffect, useState } from "react";
import type { CSSProperties } from "react";
import { accent, portrait, STANCE_COLOR, STANCE_LABEL } from "@/lib/personas";
import type { Claim, Rejected, Stance } from "@/lib/types";

export const accentStyle = (id: string) => ({ "--accent": accent(id) }) as CSSProperties;

export function Avatar({ id }: { id: string }) {
  return (
    <div className="avatar" data-p={id} style={accentStyle(id)}>
      <img src={portrait(id)} width={62} height={70} alt="" />
    </div>
  );
}

export function StanceBadge({ stance }: { stance: Stance }) {
  return <span className="badge" style={{ color: STANCE_COLOR[stance] }}>{STANCE_LABEL[stance]}</span>;
}

export function Claims({ claims, rejected = [], limit, brief }: { claims: Claim[]; rejected?: Rejected[]; limit?: number; brief?: boolean }) {
  if (!claims.length && !rejected.length) return null;
  const shown = limit ? claims.slice(0, limit) : claims;
  const first = (t: string) => (brief ? (t.match(/^.*?[.!?](\s|$)/)?.[0] ?? t).trim() : t);
  const cut = brief ? 70 : 140;
  return (
    <ul className="claims">
      {shown.map((c, i) => (
        <li key={i} className={`claim${brief ? "" : " clamp"}`} tabIndex={brief ? undefined : 0}
            title={brief ? undefined : "Click to see it all"}
            onClick={brief ? undefined : (e) => e.currentTarget.classList.toggle("open")}
            onKeyDown={brief ? undefined : (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); e.currentTarget.classList.toggle("open"); } }}>
          <span className="claim-text">{first(c.text)}</span>
          <span className="evidence">
            {c.evidence.kind === "tree" ? (
              <>repo tree · {c.evidence.ref === "absent" ? "no file matching" : "has"} {c.evidence.quote}</>
            ) : (
              <>
                {c.evidence.kind === "demo" ? "demo " : c.evidence.kind === "site" ? "live site " : c.evidence.kind === "answer" ? "the builder said, " : ""}
                {c.evidence.ref} · &ldquo;{c.evidence.quote.length > cut ? c.evidence.quote.slice(0, cut) + "…" : c.evidence.quote}&rdquo;
              </>
            )}
          </span>
        </li>
      ))}
      {!brief && shown.length < claims.length && (
        <li className="dropped">+ {claims.length - shown.length} more checked claim{claims.length - shown.length > 1 ? "s" : ""}</li>
      )}
      {rejected.length > 0 && (
        <li className="dropped">
          {rejected.length} claim{rejected.length > 1 ? "s" : ""} dropped: the evidence was not in the project
        </li>
      )}
    </ul>
  );
}

export const Icon = {
  plus: (c = "#0A0E1A") => (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth="2.4" strokeLinecap="round" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg>
  ),
  home: (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#A6B0CC" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M4 11l8-7 8 7v9H14v-6h-4v6H4z" /></svg>
  ),
  history: (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#A6B0CC" strokeWidth="2" strokeLinejoin="round" aria-hidden="true"><path d="M4 5h16v11H10l-6 4z" /></svg>
  ),
  check: (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><path d="M2 6l3 3 5-6" /></svg>
  ),
  send: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#0A0E1A" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 19V5M6 11l6-6 6 6" /></svg>
  ),
};


/** Split into sentences without losing any text: only a stop followed by a space ends one. */
export function sentences_(text: string): string[] {
  return text.trim().split(/(?<=[.!?])\s+/).filter(Boolean).map((s) => s + " ");
}

/** The first `sentences` sentences, with the rest behind "Read more". People skim; the full reply is one click away. */
export function ReadMore({ text, sentences = 2, animate = false }: { text: string; sentences?: number; animate?: boolean }) {
  const [open, setOpen] = useState(false);
  const parts = sentences_(text);
  let n = sentences;
  while (n < parts.length && parts.slice(0, n).join("").length < 90) n++; // a very short opener is not enough
  const head = parts.length <= n ? text : parts.slice(0, n).join("").trim();
  const typed = useTyped(head, animate);
  if (parts.length <= n) return <div className="msg">{typed.shown}{!typed.done && <span className="caret" aria-hidden="true" />}</div>;
  if (!typed.done) return <div className="msg">{typed.shown}<span className="caret" aria-hidden="true" /></div>;
  return (
    <div className="msg">
      {open ? text : head}{" "}
      <button type="button" className="more-btn" aria-expanded={open} onClick={() => setOpen(!open)}>
        {open ? "Show less" : "Read more"}
      </button>
    </div>
  );
}

/** A closed-by-default block: the evidence is always there, but it does not crowd the page. */
export function More({ label, children, open = false }: { label: string; children: React.ReactNode; open?: boolean }) {
  return (
    <details className="more" open={open}>
      <summary>{label}</summary>
      <div className="more-body">{children}</div>
    </details>
  );
}

export const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;


/** Reveals text a few words at a time, so a reply reads as if it is being said.
 *  The reply has already arrived in full (its claims are checked first); this only paces the reading. */
export function useTyped(text: string, on: boolean): { shown: string; done: boolean } {
  const [count, setCount] = useState<number | null>(null);
  useEffect(() => {
    let reduced = false;
    try { reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches; } catch {}
    if (!on || reduced) { setCount(null); return; }
    const words = text.split(/(\s+)/).length;
    let i = 0;
    setCount(0);
    const id = window.setInterval(() => {
      i += 2;
      setCount(i);
      if (i >= words) { window.clearInterval(id); setCount(null); }
    }, 28);
    return () => window.clearInterval(id);
  }, [text, on]);
  if (count === null) return { shown: text, done: true };
  return { shown: text.split(/(\s+)/).slice(0, count).join(""), done: false };
}

export function Typed({ text, on }: { text: string; on: boolean }) {
  const { shown, done } = useTyped(text, on);
  return <>{shown}{!done && <span className="caret" aria-hidden="true" />}</>;
}

/** The gist of a long point: the part before the first ":", " — " or ";" (or the first ~80 characters),
 *  with the whole point one click away. */
export function gist(text: string, max = 80): string {
  const t = text.trim();
  const cut = t.search(/: | — | – |; /);
  let g = cut > 20 ? t.slice(0, cut) : t;
  if (g.length > max) g = g.slice(0, g.lastIndexOf(" ", max)) + "…";
  return g.replace(/[.,]$/, "");
}

export function Gist({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  const short = gist(text);
  if (short === text.trim() || short === text.trim().replace(/[.,]$/, "")) return <>{text}</>;
  return (
    <>
      {open ? text : short}{" "}
      <button type="button" className="more-btn" aria-expanded={open} onClick={() => setOpen(!open)}>
        {open ? "Less" : "More"}
      </button>
    </>
  );
}

/** "Evidence · 2 points", or, when the checker threw every point out, say so instead of "0 points". */
export function evidenceLabel(kept: number, dropped: number): string {
  if (kept === 0) return `Evidence · ${plural(dropped, "point")} dropped, none could be checked`;
  return `Evidence · ${plural(kept, "point")}${dropped ? ` (${dropped} dropped)` : ""}`;
}
