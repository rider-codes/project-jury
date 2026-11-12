"use client";

import { useCallback, useEffect, useReducer, useState } from "react";
import { AccessGate } from "@/components/AccessGate";
import { ChatView } from "@/components/ChatView";
import { PersonaPicker } from "@/components/PersonaPicker";
import { RoomView } from "@/components/RoomView";
import { Icon } from "@/components/bits";
import { api } from "@/lib/api";
import { ROUND_LABEL, emptyRoom, roomReducer } from "@/lib/room";
import type { Chat, Persona, ReviewListItem } from "@/lib/types";

type Mode = "room" | "chat";

function setUrl(params: Record<string, string | null>) {
  const url = new URL(window.location.href);
  for (const [k, v] of Object.entries(params)) (v ? url.searchParams.set(k, v) : url.searchParams.delete(k));
  window.history.replaceState(null, "", url);
}

export default function Home() {
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
  const [repo, setRepo] = useState("");
  const [demo, setDemo] = useState("");
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  const [to, setTo] = useState("");
  const [barText, setBarText] = useState("");
  const [barBusy, setBarBusy] = useState(false);
  const [quota, setQuota] = useState<{ demo_model: boolean; free_quota: { remaining: number; limit: number } | null } | null>(null);

  const [locked, setLocked] = useState(false);

  // personas, and a review or chat from the URL
  useEffect(() => {
    api.session().then((s) => setLocked(s.needs_code && !s.ok)).catch(() => {});
    api.personas()
      .then((ps) => {
        setPersonas(ps);
        setSelected(ps.filter((p) => p.default).map((p) => p.id));
      })
      .catch(() => setLoadError("Cannot reach the API. Start it with: uv run python -m jury.api"));
    api.quota().then(setQuota).catch(() => setQuota(null));
    const q = new URLSearchParams(window.location.search);
    if (q.get("review")) setReviewId(q.get("review"));
    if (q.get("chat")) {
      api.chat(q.get("chat")!).then((c) => { setChat(c); setMode("chat"); }).catch(() => setUrl({ chat: null }));
    }
  }, []);

  // live event stream for the review on screen; replays from the start on reload
  useEffect(() => {
    if (!reviewId) return;
    dispatch({ type: "reset", personaIds: [] });
    setUrl({ review: reviewId });
    const es = new EventSource(api.eventsUrl(reviewId));
    es.onmessage = (m) => dispatch({ type: "event", event: JSON.parse(m.data) });
    es.addEventListener("end", () => es.close());
    return () => es.close();
  }, [reviewId]);

  useEffect(() => {
    setUrl({ chat: chat?.id ?? null });
  }, [chat?.id]);

  const started = reviewId !== null;
  const names = Object.fromEntries(personas.map((p) => [p.id, p.name]));
  const inRoom = started ? room.personaIds : selected;
  const projectName = room.project?.name ?? (started ? "…" : "your project");

  // round 1 + debate (2 turns each, 12 at most) + verdicts + summary
  const needed = selected.length ? selected.length + Math.min(12, 2 * selected.length) + selected.length + 1 : 0;
  const left = quota?.free_quota?.remaining ?? null;
  const short = left !== null && left < needed;

  const toggle = (id: string) =>
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));

  const start = async (sample: boolean) => {
    setStarting(true);
    setStartError(null);
    try {
      const { id } = await api.startReview(sample ? { sample: true, persona_ids: selected }
                                                  : { repo_url: repo.trim(), demo, persona_ids: selected });
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
    try { setPast(await api.reviews()); } catch {}
  };

  const answer = useCallback(async (answers: Record<string, string>) => {
    if (reviewId) await api.answer(reviewId, answers);
  }, [reviewId]);

  // message bar: after the review, talk to one reviewer with the room's history
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

  if (locked) return <AccessGate />;

  return (
    <div className="shell">
      <nav className="rail" aria-label="Main">
        <button type="button" className="rail-btn primary" aria-label="New review" title="New review" onClick={newReview}>{Icon.plus()}</button>
        <button type="button" className="rail-btn" aria-label="Past reviews" title="Past reviews" aria-expanded={drawer} onClick={openDrawer}>{Icon.history}</button>
      </nav>

      {drawer && (
        <aside className="drawer" aria-label="Past reviews">
          <div className="row" style={{ justifyContent: "space-between" }}>
            <h2>Past reviews</h2>
            <button type="button" className="link-btn" onClick={() => setDrawer(false)}>Close</button>
          </div>
          {past.length === 0 && <p className="muted">No reviews yet.</p>}
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
            <div className="crumb">Project reviews / {projectName}</div>
            <div className="row">
              <div className="toggle" role="group" aria-label="Mode">
                <button type="button" aria-pressed={mode === "room"} onClick={() => setMode("room")}>Room</button>
                <button type="button" aria-pressed={mode === "chat"} onClick={() => setMode("chat")}>One-on-one</button>
              </div>
              {mode === "room" && (
                <div className="pill">
                  {room.status === "done" ? "Review complete" : room.status === "paused" ? `${ROUND_LABEL[room.round]} · waiting for you` : ROUND_LABEL[room.round]}
                </div>
              )}
            </div>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <h1>Is {projectName} useful?</h1>
            <div className="mono" style={{ fontSize: 13, color: "var(--faint)", overflowWrap: "anywhere" }}>
              {room.project ? `${room.project.repo_url} · ${room.project.files} files read · ${room.project.demo_steps ? `${room.project.demo_steps} demo steps` : "no demo"}`
                            : "Give a GitHub link and a short walkthrough. The panel reads it, asks what is missing, debates, and decides."}
            </div>
            {loadError && <div className="form-error">{loadError}</div>}
          </div>

          {mode === "chat" ? (
            <ChatView personas={personas} reviewId={reviewId} reviewDone={room.status === "done"}
                      chat={chat} setChat={setChat} initialPersona={chatPersona} />
          ) : (
            <>
              <section className="section" aria-labelledby="who">
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
                          ? `Needs about ${needed} model requests · ${left} of ${quota.free_quota!.limit} free requests left today.` +
                            (short ? " Not enough: it would stop partway. Pick fewer reviewers or wait for the daily reset." : "")
                          : `Needs about ${needed} model requests.`}
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
                    <span className="muted" style={{ fontSize: 13 }}>Public repos only. A review takes 1 to 3 minutes.</span>
                  </div>
                </form>
              )}

              <RoomView room={room} names={names} personas={personas} onAnswer={answer} />

              {started && (
                <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                  <form className="bar" onSubmit={(e) => { e.preventDefault(); sendToReviewer(); }}>
                    <label htmlFor="msg" className="sr">Message a reviewer</label>
                    <input id="msg" className="input" value={barText} onChange={(e) => setBarText(e.target.value)}
                           disabled={room.status !== "done" || barBusy} maxLength={4000}
                           placeholder={room.status === "done" ? "Ask one reviewer about their verdict…" : "You can talk to a reviewer when the review ends"} />
                    <label htmlFor="to" className="sr">Send to</label>
                    <select id="to" className="select" value={to} onChange={(e) => { setTo(e.target.value); setChatPersona(e.target.value); }}
                            disabled={room.status !== "done"}>
                      <option value="">To: pick a reviewer</option>
                      {room.personaIds.filter((p) => room.verdicts.some((v) => v.persona_id === p)).map((p) => (
                        <option key={p} value={p}>To: {names[p]}</option>
                      ))}
                    </select>
                    <button type="submit" className="send" aria-label="Send" disabled={room.status !== "done" || !to || !barText.trim() || barBusy}>
                      {Icon.send}
                    </button>
                  </form>
                  <div className="hint">Opens a one-on-one chat that knows what the room said</div>
                </div>
              )}
            </>
          )}
        </div>
      </main>
    </div>
  );
}
