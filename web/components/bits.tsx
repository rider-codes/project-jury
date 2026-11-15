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
        <li key={i} className="claim">
          {first(c.text)}
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
