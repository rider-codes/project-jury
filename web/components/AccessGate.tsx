"use client";

import { useState } from "react";
import { api } from "@/lib/api";

/** Shown on a deployment that has JURY_ACCESS_CODE set, until the right code is entered. */
export function AccessGate() {
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
    <main className="main" style={{ alignItems: "center", minHeight: "100vh" }}>
      <form className="inputs" style={{ maxWidth: 420, width: "100%" }} onSubmit={(e) => { e.preventDefault(); submit(); }}>
        <h1 style={{ fontSize: 34 }}>Project Jury</h1>
        <p className="muted" style={{ margin: 0 }}>This deployment is private. Enter the access code to continue.</p>
        <div className="field">
          <label htmlFor="code" className="label">Access code</label>
          <input id="code" className="input" type="password" autoComplete="current-password" value={code}
                 onChange={(e) => setCode(e.target.value)} />
        </div>
        {error && <div className="form-error" role="alert">{error}</div>}
        <div className="row"><button className="btn" type="submit" disabled={busy || !code.trim()}>Continue</button></div>
      </form>
    </main>
  );
}
