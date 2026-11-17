"use client";

import { ThemeSwitch, useTheme } from "./Theme";
import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { emptyRoom, roomReducer, ROUND_LABEL } from "@/lib/room";
import type { Persona, ReviewEvent } from "@/lib/types";
import { AccessForm } from "./AccessGate";
import { PersonaPicker } from "./PersonaPicker";
import { RoomView } from "./RoomView";
import { EvidenceDemo, HeroArt, Pipeline, StatsBand, Ticker } from "./showcase/Visuals";

type Recording = {
  recorded: string;
  about: string;
  models: { cheap: string; mid: string };
  personas: Persona[];
  events: ReviewEvent[];
};

// How long each kind of event stays on screen before the next one, in ms.
const PACE: Record<string, number> = {
  brief: 900, impression: 1500, agent_error: 800, questions_merged: 500, needs_answers: 1800, paused: 300,
  answers_received: 700, router: 700, debate_turn: 2400, verdict: 1600, summary: 1200,
};

/** Real claims from the recording, shortened, for the ticker tape. */
function findings(rec: Recording): string[] {
  const seen = new Set<string>();
  for (const e of rec.events as any[]) {
    const claims = e.type === "impression" || e.type === "debate_turn" ? e.claims : e.type === "verdict" ? e.reasons : [];
    for (const c of claims ?? []) {
      const t = String(c.text).replace(/\s+/g, " ").trim();
      const short = t.length > 92 ? t.slice(0, t.lastIndexOf(" ", 90)) + "…" : t;
      seen.add(short);
    }
  }
  return [...seen].slice(0, 9);
}

/** Headline numbers, counted from the recording itself. */
function stats(rec: Recording): [string, string][] {
  const ev = rec.events as any[];
  const claims = ev.reduce((n, e) =>
    n + (e.type === "impression" || e.type === "debate_turn" ? e.claims.length : e.type === "verdict" ? e.reasons.length : 0), 0);
  const turns = ev.filter((e) => e.type === "debate_turn").length;
  const usage = ev.find((e) => e.type === "usage");
  return [
    // the panel a visitor can pick from, not the four who happened to sit in the recorded room
    [String(rec.personas.length), `reviewers to pick from, up to ${rec.personas.length} in a room`],
    [String(claims), "claims, each checked against the files"],
    [String(turns), "debate turns, picked by the moderator"],
    [usage ? String(usage.calls) : "–", "model calls on free models"],
  ];
}

/** The public dashboard. signedIn: reached from the app's Home button, so it links back instead of asking for a code. */
export function Showcase({ signedIn = false }: { signedIn?: boolean }) {
  const [rec, setRec] = useState<Recording | null>(null);
  const [room, dispatch] = useReducer(roomReducer, emptyRoom);
  const [pos, setPos] = useState(0); // events applied so far
  const [playing, setPlaying] = useState(false);
  const replayRef = useRef<HTMLElement>(null);
  const [dark, pickTheme] = useTheme();

  useEffect(() => {
    fetch("/showcase/review.json", { cache: "no-cache" }).then((r) => r.json()).then(setRec).catch(() => setRec(null));
  }, []);

  const total = rec?.events.length ?? 0;

  // advance one event at a time while playing
  useEffect(() => {
    if (!rec || !playing) return;
    if (pos >= total) { setPlaying(false); return; }
    const e = rec.events[pos];
    const t = setTimeout(() => {
      dispatch({ type: "event", event: e });
      setPos(pos + 1);
    }, pos === 0 ? 200 : PACE[rec.events[pos - 1].type] ?? 400);
    return () => clearTimeout(t);
  }, [rec, playing, pos, total]);

  const restart = useCallback(() => {
    dispatch({ type: "reset" });
    setPos(0);
    setPlaying(true);
  }, []);

  const skipToEnd = () => {
    if (!rec) return;
    rec.events.slice(pos).forEach((e) => dispatch({ type: "event", event: e }));
    setPos(total);
    setPlaying(false);
    // after React draws round 3, take the visitor to it
    setTimeout(() => {
      const el = document.getElementById("r3");
      if (el) window.scrollTo({ top: el.getBoundingClientRect().top + window.scrollY - 24 });
    }, 300);
  };

  const watch = () => {
    replayRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    if (pos === 0 || pos >= total) restart(); else setPlaying(true);
  };

  const names = Object.fromEntries((rec?.personas ?? []).map((p) => [p.id, p.name]));
  const started = pos > 0;
  const claims = room.impressions.reduce((n, i) => n + i.claims.length, 0)
    + room.feed.reduce((n, f) => n + (f.kind === "turn" ? f.turn.claims.length : 0), 0)
    + room.verdicts.reduce((n, v) => n + v.reasons.length, 0);

  return (
    <div className={`shell sc-page${dark ? " dark" : ""}`}>
      <main className="main">
        <div className="column">
          <div className="topbar">
            <img className="sc-logo" src={dark ? "/brand/logo-dark.svg" : "/brand/logo-light.svg"} alt="Project Jury" height={44} />
            <div className="row">
              <ThemeSwitch dark={dark} onPick={pickTheme} />
              <a className="btn ghost" href={signedIn ? "/" : "#access"} style={{ display: "inline-grid", placeItems: "center", textDecoration: "none" }}>
                {signedIn ? "Open the app" : "I have an access code"}
              </a>
            </div>
          </div>

          <section className="section sc-hero-copy" style={{ gap: 18 }}>
            <h1>Is your project <mark className="sc-mark">useful</mark>? Ask a jury.</h1>
            <p className="body" style={{ fontSize: 18, maxWidth: 760 }}>
              Six AI reviewers read your GitHub repo, debate it, and give an honest verdict.
              Every claim has to quote your real files.
            </p>
            <div className="row">
              <button type="button" className="btn" onClick={watch}>Watch a real review</button>
              <a className="btn ghost" href={signedIn ? "/" : "#access"} style={{ display: "inline-grid", placeItems: "center", textDecoration: "none" }}>
                Review your own project
              </a>
              <a className="link-btn" href="#how" style={{ color: "var(--text)" }}>How it works</a>
            </div>
            <span className="muted" style={{ fontSize: 14 }}>
              Free · public GitHub repos · {signedIn ? "1 to 3 minutes" : "needs an access code"}
            </span>
            {rec && <HeroArt personas={rec.personas} />}
          </section>

          {rec && <div className="sc-bleed sc-band"><StatsBand items={stats(rec)} /></div>}

          <section className="section" id="how" aria-labelledby="how-h">
            <div className="section-head">
              <div><span className="sc-kicker">01 / Method</span><h2 id="how-h">How it works</h2></div>
              <span className="muted" style={{ fontSize: 14 }}>One review, four rounds, about 1 to 3 minutes</span>
            </div>
            <Pipeline />
          </section>

          {rec && <div className="sc-bleed"><Ticker items={findings(rec)} /></div>}

          <section className="section" aria-labelledby="ev-h">
            <div className="section-head">
              <div><span className="sc-kicker">02 / Evidence</span><h2 id="ev-h">No evidence, no claim</h2></div>
              <span className="muted" style={{ fontSize: 14 }}>A checker written in plain code, not a model</span>
            </div>
            <p className="body" style={{ margin: 0, maxWidth: 760 }}>
              Each point must quote your project. A checker looks the quote up and drops anything it cannot find.
            </p>
            <EvidenceDemo />
          </section>

          <section className="section" aria-labelledby="panel-h">
            <div className="section-head">
              <div><span className="sc-kicker">03 / The panel</span><h2 id="panel-h">Six reviewers, six questions</h2></div>
              <span className="muted" style={{ fontSize: 14 }}>Pick who sits in your room. Each answers one question.</span>
            </div>
            {rec && (
              <PersonaPicker personas={rec.personas} selected={started ? room.personaIds : rec.personas.map((p) => p.id)}
                             stance={room.stance} state={room.personaState} speaking={room.speaking} />
            )}
          </section>

          <section className="section" id="replay" ref={replayRef} aria-labelledby="replay-h">
            <div className="section-head">
              <div><span className="sc-kicker">04 / Proof</span><h2 id="replay-h">A real review, replayed</h2></div>
              <div className="pill">{pos >= total && total ? "Review complete" : ROUND_LABEL[room.round]}</div>
            </div>
            {rec && (
              <div className="sc-about">
                <span className="sc-about-tag">About this run</span>
                <p>{rec.about}</p>
                <span className="sc-about-date">Recorded {rec.recorded}</span>
              </div>
            )}
            <div className="row">
              <button type="button" className="btn" onClick={() => (playing ? setPlaying(false) : pos >= total ? restart() : setPlaying(true))} disabled={!rec}>
                {playing ? "Pause" : pos >= total && total ? "Replay" : started ? "Resume" : "Play"}
              </button>
              <button type="button" className="btn ghost" onClick={restart} disabled={!rec || !started}>Restart</button>
              <button type="button" className="btn ghost" onClick={skipToEnd} disabled={!rec || pos >= total}>Skip to the verdicts</button>
              <span className="mono muted" style={{ fontSize: 12 }} aria-live="polite">
                {started ? `${pos} / ${total} events · ${claims} checked claims shown` : "Not playing"}
              </span>
            </div>
            {started && <RoomView room={room} names={names} personas={rec?.personas ?? []} onAnswer={async () => {}} readOnly compact />}
            {pos >= total && total > 0 && (
              <div className="sc-about">
                <span className="sc-about-tag">Your turn</span>
                <p>That was one project. The same panel can read yours and tell you what it finds.</p>
                <div className="row">
                  <a className="btn" href={signedIn ? "/" : "#access"} style={{ display: "inline-grid", placeItems: "center", textDecoration: "none" }}>
                    Now review your project
                  </a>
                </div>
              </div>
            )}
          </section>

          <section className="section" id="access" style={{ alignItems: "flex-start" }}>
            {signedIn
              ? <a className="btn" href="/" style={{ display: "inline-grid", placeItems: "center", textDecoration: "none" }}>Open the app and review your project</a>
              : <AccessForm id="showcase-code" />}
          </section>

          <footer className="sc-footer">
            <span className="mono">Project Jury</span>
            <span className="evidence" style={{ margin: 0 }}>
              Replay recorded on free models ({rec?.models.cheap ?? "…"} and {rec?.models.mid ?? "…"}). Opinions are the models&rsquo;, checked against the project&rsquo;s files.
            </span>
          </footer>
        </div>
      </main>
    </div>
  );
}
