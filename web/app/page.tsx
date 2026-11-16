"use client";

import { useCallback, useEffect, useReducer, useState } from "react";
import { ChatView } from "@/components/ChatView";
import { Showcase } from "@/components/Showcase";
import { PersonaPicker } from "@/components/PersonaPicker";
import { RoomView } from "@/components/RoomView";
import { Icon } from "@/components/bits";
import { ThemeSwitch, useTheme } from "@/components/Theme";
import { api, type Quota } from "@/lib/api";
import { ROUND_LABEL, emptyRoom, roomReducer } from "@/lib/room";
import type { Chat, Persona, ReviewListItem } from "@/lib/types";

type Mode = "room" | "chat";

function setUrl(params: Record<string, string | null>) {
  const url = new URL(window.location.href);
  for (const [k, v] of Object.entries(params)) (v ? url.searchParams.set(k, v) : url.searchParams.delete(k));
  window.history.replaceState(null, "", url);
}

export default function Home() {
  const [dark, pickTheme] = useTheme();
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [mode, setMode] = useState<Mode>("room");
  const [selected, setSelected] = useState<string[]>([]);
  const [reviewId, setReviewId] = useState<string | null>(null);
  const [room, dispatch] = useReducer(roomReducer, emptyRoom);
  const [chat, setChat] = useState<Chat | null>(null);
  const [chatPersona, setChatPersona] = useState<string | null>(null);
  const [drawer, setDrawer] = useState(false);
  const [past, setPast] = useState<ReviewListItem[]>([]);
  const [pastError, setPastError] = useState(false);
  const [loadRun, setLoadRun] = useState(0); // bumped by Retry to load the reviewers again
  const [repo, setRepo] = useState("");
  const [site, setSite] = useState("");
  const [demo, setDemo] = useState("");
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  const [to, setTo] = useState("");
  const [barText, setBarText] = useState("");
  const [barBusy, setBarBusy] = useState(false);
  const [quota, setQuota] = useState<Quota | null>(null);
  const [streamRun, setStreamRun] = useState(0); // bumped to reopen the event stream after a retry

  // ?view=home: the public dashboard, reachable from the app's Home button
  const [home, setHome] = useState(false);
  useEffect(() => { setHome(new URLSearchParams(window.location.search).get("view") === "home"); }, []);

  // checking: nothing is drawn yet, so a private deployment never flashes the app before the showcase
  const [access, setAccess] = useState<"checking" | "locked" | "open">("checking");

  useEffect(() => {
    api.session()
      .then((s) => setAccess(s.needs_code && !s.ok ? "locked" : "open"))
      .catch(() => setAccess("open")); // API down: show the app, which explains it cannot reach the API
  }, []);

  // personas, and a review or chat from the URL
  useEffect(() => {
    if (access !== "open") return;
    setLoadError(null);
    api.personas()
      .then((ps) => {
        setPersonas(ps);
        setSelected(ps.filter((p) => p.default).map((p) => p.id));
      })
      // a hosted visitor cannot start the API, so the command is only shown when developing
      .catch(() => setLoadError("We couldn't reach the review service. Please try again in a moment." +
        (process.env.NODE_ENV === "production" ? "" : " (Developing? Start it with: uv run python -m jury.api)")));
    api.quota().then(setQuota).catch(() => setQuota(null));
    const q = new URLSearchParams(window.location.search);
    if (q.get("review")) setReviewId(q.get("review"));
    if (q.get("chat")) {
      api.chat(q.get("chat")!).then((c) => { setChat(c); setMode("chat"); }).catch(() => setUrl({ chat: null }));
    }
  }, [access, loadRun]);

  // live event stream for the review on screen; replays from the start on reload
  useEffect(() => {
    if (!reviewId) return;
    dispatch({ type: "reset", personaIds: [] });
    setUrl({ review: reviewId });
    const es = new EventSource(api.eventsUrl(reviewId));
    es.onmessage = (m) => dispatch({ type: "event", event: JSON.parse(m.data) });
    es.addEventListener("end", () => es.close());
    return () => es.close();
  }, [reviewId, streamRun]);

  useEffect(() => {
    setUrl({ chat: chat?.id ?? null });
  }, [chat?.id]);

  const started = reviewId !== null;
  const names = Object.fromEntries(personas.map((p) => [p.id, p.name]));
  const inRoom = started ? room.personaIds : selected;
  const projectName = room.project?.name ?? (started ? "…" : "your project");

  // round 1 + debate (2 turns each, 12 at most) + verdicts + summary, plus one vision call per
  // live-site screenshot described
  const siteCalls = site.trim() ? (quota?.site_calls ?? 4) : 0;
  const needed = selected.length ? selected.length + Math.min(12, 2 * selected.length) + selected.length + 1 + siteCalls : 0;
  const left = quota?.free_quota?.remaining ?? null;
  const short = left !== null && left < needed;

  const toggle = (id: string) =>
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));

  const start = async (sample: boolean) => {
    setStarting(true);
    setStartError(null);
    try {
      const { id } = await api.startReview(sample ? { sample: true, persona_ids: selected }
                                                  : { repo_url: repo.trim(), site_url: site.trim(), demo, persona_ids: selected });
      setChat(null);
      setReviewId(id);
    } catch (e) {
      setStartError((e as Error).message);
    }
    setStarting(false);
  };

  const newReview = () => {
    setReviewId(null);
    setChat(null);
    setMode("room");
    dispatch({ type: "reset" });
    setUrl({ review: null, chat: null });
  };

  const openDrawer = async () => {
    setDrawer((d) => !d);
    try {
      setPast(await api.reviews());
      setPastError(false);
    } catch {
      setPastError(true);
    }
  };

  const answer = useCallback(async (answers: Record<string, string>) => {
    if (reviewId) await api.answer(reviewId, answers);
  }, [reviewId]);

  const retry = useCallback(async () => {
    if (!reviewId) return;
    await api.retry(reviewId);
    setStreamRun((n) => n + 1); // the old stream closed when the review ended
  }, [reviewId]);

  // message bar: while the room debates, the message goes to the room and the next speaker answers it
  const live = started && !room.debateOver && (room.status === "running" || room.status === "paused") && room.round >= 1;
  const sendToRoom = async () => {
    if (!reviewId || !barText.trim()) return;
    setBarBusy(true);
    setStartError(null);
    try {
      await api.say(reviewId, to || "everyone", barText.trim());
      setBarText("");
    } catch (e) {
      setStartError((e as Error).message);
    }
    setBarBusy(false);
  };

  // after the review, talk to one reviewer with the room's history
  const sendToReviewer = async () => {
    if (!reviewId || !to || !barText.trim()) return;
    setBarBusy(true);
    try {
      const c = await api.startChat({ persona_id: to, review_id: reviewId, with_history: true });
      const mine = { role: "user" as const, text: barText.trim() };
      setChat({ ...c, messages: [mine] });
      setMode("chat");
      setBarText("");
      const reply = await api.sendChat(c.id, mine.text);
      setChat({ ...c, messages: [mine, reply] });
    } catch (e) {
      setStartError((e as Error).message);
    }
    setBarBusy(false);
  };

  // checking: the app is not drawn yet (see above), but the visitor is told something is happening
  if (access === "checking") {
    return (
      <div className={`shell sc-page${dark ? " dark" : ""}`} aria-busy="true">
        <p className="checking muted" role="status">Checking access…</p>
      </div>
    );
  }
  if (access === "locked") return <Showcase />;
  if (home) return <Showcase signedIn />;

  return (
    <div className={`shell sc-page sc-app${dark ? " dark" : ""}`}>
      <nav className="rail" aria-label="Main">
        {/* labelled, and none styled as the primary action: on the start screen that is "Start review" */}
        <a className="rail-btn" href="/?view=home" title="Back to the dashboard">{Icon.home}<span className="rail-label">Home</span></a>
        <button type="button" className="rail-btn" title="New review" onClick={newReview}>{Icon.plus("currentColor")}<span className="rail-label">New</span></button>
        <button type="button" className="rail-btn" title="Past reviews" aria-expanded={drawer} onClick={openDrawer}>{Icon.history}<span className="rail-label">Past</span></button>
      </nav>

      {drawer && (
        <aside className="drawer" aria-label="Past reviews">
          <div className="row" style={{ justifyContent: "space-between" }}>
            <h2>Past reviews</h2>
            <button type="button" className="link-btn" onClick={() => setDrawer(false)}>Close</button>
          </div>
          {pastError && <p className="form-error" role="alert">Could not load past reviews. Close this and try again.</p>}
          {!pastError && past.length === 0 && <p className="muted">No reviews yet.</p>}
          {past.map((r) => (
            <button key={r.id} type="button" className="drawer-item"
                    onClick={() => { setDrawer(false); setMode("room"); setChat(null); setReviewId(r.id); }}>
              <strong>{r.project_name}</strong>
              <span className="evidence">{r.status} · {r.persona_ids.length} reviewers · {r.created_at.replace("T", " ").slice(0, 16)}</span>
            </button>
          ))}
        </aside>
      )}

      <main className="main">
        <div className="column">
          <div className="topbar">
            <div className="row" style={{ gap: 16 }}>
              <a href="/?view=home" aria-label="Project Jury home"><img className="sc-logo" src={dark ? "/brand/logo-dark.svg" : "/brand/logo-light.svg"} alt="Project Jury" height={44} /></a>
              <div className="crumb">/ {projectName}</div>
              {mode === "room" && (
                <span className="sc-status" role="status">
                  {room.status === "done" ? "Review complete" : room.status === "paused" ? `${ROUND_LABEL[room.round]} · waiting for you` : ROUND_LABEL[room.round]}
                </span>
              )}
            </div>
            <div className="row">
              <ThemeSwitch dark={dark} onPick={pickTheme} />
              <div className="toggle" role="group" aria-label="Mode">
                <button type="button" aria-pressed={mode === "room"} onClick={() => setMode("room")}>Room</button>
                <button type="button" aria-pressed={mode === "chat"} onClick={() => setMode("chat")}>One-on-one</button>
              </div>
            </div>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <h1>Is {projectName} useful?</h1>
            <div className="mono" style={{ fontSize: 13, color: "var(--faint)", overflowWrap: "anywhere" }}>
              {room.project ? `${room.project.repo_url} · ${room.project.files} files read · ${room.project.demo_steps ? `${room.project.demo_steps} demo steps` : "no demo"}` +
                              (room.project.site_views ? ` · ${room.project.site_views} live site views` : "")
                            : "Give a GitHub link and a short walkthrough. The panel reads it, asks what is missing, debates, and decides."}
            </div>
            {loadError && (
              <div className="row" role="alert">
                <span className="form-error">{loadError}</span>
                <button type="button" className="btn ghost" onClick={() => setLoadRun((n) => n + 1)}>Retry</button>
              </div>
            )}
          </div>

          {mode === "chat" ? (
            <ChatView personas={personas} reviewId={reviewId} reviewDone={room.status === "done"}
                      chat={chat} setChat={setChat} initialPersona={chatPersona} />
          ) : (
            <>
              {/* who-pre: at phone width the start form goes above the reviewers, so "Start review" is not buried */}
              <section className={`section${started ? "" : " who-pre"}`} aria-labelledby="who">
                <div className="section-head">
                  <div className="row" style={{ alignItems: "baseline", gap: 14 }}>
                    <h2 id="who">Who is in the room?</h2>
                    <span className="muted" style={{ fontSize: 14 }}>{inRoom.length} selected · {personas.length} available</span>
                  </div>
                  {!started && (
                    <button type="button" className="link-btn"
                            onClick={() => setSelected(selected.length === personas.length ? [] : personas.map((p) => p.id))}>
                      {selected.length === personas.length ? "Clear" : "Select all"}
                    </button>
                  )}
                </div>
                <PersonaPicker personas={personas} selected={inRoom} onToggle={started ? undefined : toggle}
                               stance={room.stance} state={room.personaState} speaking={room.speaking} />
              </section>

              {!started && (
                <form className="inputs" onSubmit={(e) => { e.preventDefault(); start(false); }}>
                  <div className="row" style={{ alignItems: "flex-start" }}>
                    <div className="field">
                      <label htmlFor="repo" className="label">GitHub link</label>
                      <input id="repo" className="input" placeholder="https://github.com/you/repo" value={repo}
                             onChange={(e) => setRepo(e.target.value)} />
                      <label htmlFor="site" className="label">Live site <span className="muted">(optional)</span></label>
                      <input id="site" className="input" type="text" inputMode="url" autoComplete="url" spellCheck={false} placeholder="https://your-app.example.com"
                             value={site} onChange={(e) => setSite(e.target.value)} aria-describedby="site-hint" />
                      <span id="site-hint" className="muted" style={{ fontSize: 12 }}>
                        Public pages only. The panel sees the first screen and up to 3 linked pages, on desktop and phone.
                      </span>
                    </div>
                    <div className="field">
                      <label htmlFor="demo" className="label">Demo walkthrough</label>
                      <textarea id="demo" className="textarea" rows={3} value={demo} onChange={(e) => setDemo(e.target.value)}
                                placeholder={"1. Open the app\n2. Click Start\n3. What you see"} />
                    </div>
                  </div>
                  {quota && (
                    <div className={short ? "form-error" : "muted"} style={{ fontSize: 13 }} role={short ? "alert" : undefined}>
                      {quota.demo_model
                        ? "Demo model: free and offline, opinions are canned."
                        : left !== null
                          ? `Needs about ${needed} model requests${siteCalls ? ` (${siteCalls} to read the live site)` : ""} · ${left} of ${quota.free_quota!.limit} free requests left today.` +
                            (short ? " Not enough: it would stop partway. Pick fewer reviewers or wait for the daily reset." : "")
                          : `Needs about ${needed} model requests${siteCalls ? ` (${siteCalls} to read the live site)` : ""}.`}
                    </div>
                  )}
                  {startError && <div className="form-error">{startError}</div>}
                  <div className="row">
                    <button type="submit" className="btn" disabled={starting || !repo.trim() || !selected.length}>
                      {starting ? "Starting…" : "Start review"}
                    </button>
                    <button type="button" className="btn ghost" disabled={starting || !selected.length} onClick={() => start(true)}>
                      Try the sample project
                    </button>
                    <span className="muted" style={{ fontSize: 13 }}>Free. Public repos only. A review takes 1 to 3 minutes. No repo yet? The sample runs a full review.</span>
                  </div>
                </form>
              )}

              <RoomView room={room} names={names} personas={personas} onAnswer={answer} onRetry={retry} />

              {started && (
                <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                  <form className="bar" onSubmit={(e) => { e.preventDefault(); live ? sendToRoom() : sendToReviewer(); }}>
                    <label htmlFor="msg" className="sr">{live ? "Message the room" : "Message a reviewer"}</label>
                    <input id="msg" className="input" value={barText} onChange={(e) => setBarText(e.target.value)}
                           disabled={(!live && room.status !== "done") || barBusy} maxLength={live ? 2000 : 4000}
                           placeholder={live ? "Say something to the room…" : room.status === "done" ? "Ask one reviewer about their verdict…" : "The debate is over. You can ask a reviewer when the verdicts are in"} />
                    <label htmlFor="to" className="sr">Send to</label>
                    <select id="to" className="select" value={to} onChange={(e) => { setTo(e.target.value); setChatPersona(e.target.value); }}
                            disabled={!live && room.status !== "done"}>
                      <option value="">{live ? "To: Everyone" : "To: pick a reviewer"}</option>
                      {room.personaIds.filter((p) => live ? room.personaState[p] !== "error" : room.verdicts.some((v) => v.persona_id === p)).map((p) => (
                        <option key={p} value={p}>To: {names[p]}</option>
                      ))}
                    </select>
                    <button type="submit" className="send" aria-label="Send"
                            disabled={barBusy || !barText.trim() || (live ? false : room.status !== "done" || !to)}>
                      {Icon.send}
                    </button>
                  </form>
                  {startError && <div className="form-error" role="alert">{startError}</div>}
                  <div className="hint">{live ? "The next reviewer to speak answers you" : "Opens a one-on-one chat that knows what the room said"}</div>
                </div>
              )}
            </>
          )}
        </div>
      </main>
    </div>
  );
}
