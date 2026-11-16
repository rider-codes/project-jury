"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { REQUEST_CODE_URL } from "@/lib/site";

/** The access-code form. Used on the public showcase of a deployment that has JURY_ACCESS_CODE set. */
export function AccessForm({ id = "code" }: { id?: string }) {
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.login(code);
      window.location.reload();
    } catch (e) {
      setError((e as Error).message === "wrong access code" ? "That code is not right." : (e as Error).message);
      setBusy(false);
    }
  };

  return (
    <form className="inputs" style={{ maxWidth: 460, width: "100%" }} onSubmit={(e) => { e.preventDefault(); submit(); }}>
      <h2>Have an access code?</h2>
      <p className="muted" style={{ margin: 0 }}>
        Running reviews uses paid-for model time, so this deployment is private. Enter your code to review your own
        project. A review is free and needs a public GitHub repo.
      </p>
      <div className="field" style={{ flex: "none" }}>
        <label htmlFor={id} className="label">Access code</label>
        <input id={id} className="input" type="password" autoComplete="current-password" value={code}
               onChange={(e) => setCode(e.target.value)} />
      </div>
      {error && <div className="form-error" role="alert">{error}</div>}
      <div className="row">
        <button className="btn" type="submit" disabled={busy || !code.trim()}>Continue</button>
        <a className="link-btn" href="#replay" style={{ color: "var(--text)", display: "inline-grid", placeItems: "center" }}>Watch a real review first</a>
      </div>
      <p className="muted" style={{ margin: 0, fontSize: 14 }}>
        No code? <a href={REQUEST_CODE_URL} target="_blank" rel="noreferrer" style={{ color: "var(--text)", fontWeight: 700 }}>Request one here</a>.
        Say which project you want reviewed and you will get a code back.
      </p>
    </form>
  );
}
