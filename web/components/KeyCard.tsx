"use client";

import { useId, useState } from "react";
import { getKey, setKey } from "@/lib/key";

/** Ask for the visitor's own OpenRouter key. Shown when the shared free quota is gone, and on request. */
export function KeyCard({ exhausted, hasKey, onChange, then }: {
  exhausted: boolean;
  hasKey: boolean;
  onChange: () => void;
  /** what to do once a key is saved, e.g. "Press Retry." */
  then?: string;
}) {
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  // the card can be on the page twice (the start form and the meter's panel), so its ids are unique
  const uid = useId();
  const titleId = `${uid}-title`, inputId = `${uid}-key`, errorId = `${uid}-error`;

  const save = () => {
    const key = draft.trim();
    // the server checks the shape too; this only catches an obvious paste mistake before a request
    if (key.length < 16 || /\s/.test(key)) {
      setError("That does not look like an API key. Paste the whole key, with no spaces.");
      return;
    }
    setKey(key);
    setDraft("");
    setError(null);
    onChange();
  };
  const remove = () => {
    setKey("");
    onChange();
  };

  return (
    <section className={`keycard${exhausted && !hasKey ? " empty" : ""}`} aria-labelledby={titleId}>
      <h3 id={titleId}>
        {hasKey ? "Using your own key" : exhausted ? "Oops, today's free reviews are used up" : "Use your own key"}
      </h3>
      {hasKey ? (
        <>
          <p className="muted">
            Your runs are paid from your own OpenRouter account. The key stays in this tab and is gone when you close it.
            {then ? ` ${then}` : ""}
          </p>
          <div className="row">
            <span className="mono keycard-mask" aria-label="A key is set">{getKey().slice(0, 7)}…{getKey().slice(-3)}</span>
            <button type="button" className="btn ghost" onClick={remove}>Remove key</button>
          </div>
        </>
      ) : (
        <>
          <p className="muted">
            {exhausted
              ? "Please try again after the daily reset, or use your own API key to keep going now. "
              : "Run it on your own OpenRouter account. "}
            You pay OpenRouter directly, and it costs us nothing.
            A full review usually costs roughly $0.50 to $3 on paid models, depending on the project.
          </p>
          <ol className="keycard-steps">
            <li>
              Create a key at <a href="https://openrouter.ai/keys" target="_blank" rel="noreferrer noopener">openrouter.ai/keys</a>.
              Give it a small credit limit (for example $5), and delete it when you are done.
            </li>
            <li>Paste it here. It stays in this tab only, is sent with your requests over HTTPS, and is never saved on our server.</li>
          </ol>
          {/* not a <form>: this card sits inside the start form, and Enter here must save the key, not start a review */}
          <div className="row">
            <label htmlFor={inputId} className="sr">Your OpenRouter API key</label>
            <input id={inputId} className="input" type="password" autoComplete="off" spellCheck={false}
                   placeholder="sk-or-v1-…" value={draft} onChange={(e) => { setDraft(e.target.value); setError(null); }}
                   onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); save(); } }}
                   aria-describedby={error ? errorId : undefined} />
            <button type="button" className="btn" disabled={!draft.trim()} onClick={save}>Use this key</button>
          </div>
          {error && <div id={errorId} className="form-error" role="alert">{error}</div>}
        </>
      )}
    </section>
  );
}
