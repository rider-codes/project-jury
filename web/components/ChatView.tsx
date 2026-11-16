"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { STANCE_LABEL } from "@/lib/personas";
import type { Chat, ChatMessage, Persona } from "@/lib/types";
import { Avatar, Claims, Icon, StanceBadge, accentStyle } from "./bits";
import { PersonaPicker } from "./PersonaPicker";

type Props = {
  personas: Persona[];
  reviewId: string | null; // the review on screen, if any
  reviewDone: boolean;
  chat: Chat | null;
  setChat: (c: Chat | null) => void;
  initialPersona?: string | null;
};

export function ChatView({ personas, reviewId, reviewDone, chat, setChat, initialPersona }: Props) {
  const [persona, setPersona] = useState<string>(initialPersona ?? personas[0]?.id ?? "senior_engineer");
  const [withHistory, setWithHistory] = useState(false); // the plan's default is a clean start
  const [text, setText] = useState("");
  const [repo, setRepo] = useState(""); // with no review on screen: the project to talk about
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const names = Object.fromEntries(personas.map((p) => [p.id, p.name]));

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [chat?.messages.length]);

  const start = async (sample = false) => {
    setBusy(true);
    setError(null);
    try {
      setChat(await api.startChat(reviewId
        ? { persona_id: persona, review_id: reviewId, with_history: withHistory && reviewDone }
        : sample ? { persona_id: persona, sample: true } : { persona_id: persona, repo_url: repo.trim() }));
    } catch (e) {
      setError((e as Error).message);
    }
    setBusy(false);
  };

  const send = async () => {
    if (!chat || !text.trim()) return;
    const mine: ChatMessage = { role: "user", text: text.trim() };
    const before = chat;
    setChat({ ...chat, messages: [...chat.messages, mine] });
    setText("");
    setBusy(true);
    setError(null);
    try {
      const reply = await api.sendChat(chat.id, mine.text);
      setChat({ ...before, messages: [...before.messages, mine, reply] });
    } catch (e) {
      setChat(before); // nothing was saved on the server either
      setText(mine.text);
      setError((e as Error).message);
    }
    setBusy(false);
  };

  if (!chat) {
    const p = personas.find((x) => x.id === persona);
    return (
      <section className="section">
        <div className="section-head"><h2>Who do you want to talk to?</h2></div>
        <PersonaPicker personas={personas} selected={[persona]} onToggle={setPersona} single />
        <div className="inputs">
          <div className="body">
            {p?.name} will answer &ldquo;{p?.verdict_question}&rdquo; about{" "}
            {reviewId ? "the project in this review" : "the project you give below"}.
          </div>
          {!reviewId && (
            <div className="field" style={{ flex: "none" }}>
              <label htmlFor="chat-repo" className="label">GitHub link</label>
              <input id="chat-repo" className="input" placeholder="https://github.com/you/repo" value={repo}
                     onChange={(e) => setRepo(e.target.value)} disabled={busy} />
              <span className="muted" style={{ fontSize: 12 }}>
                Public repos only. Reading it is free; each message you send costs about 1 request.
              </span>
            </div>
          )}
          {reviewId && (
            <label className="check-row">
              <input type="checkbox" checked={withHistory} disabled={!reviewDone}
                     onChange={(e) => setWithHistory(e.target.checked)} />
              Bring in what the room said{!reviewDone && " (available when the review finishes)"}
            </label>
          )}
          {error && <div className="form-error">{error}</div>}
          <div className="row">
            <button className="btn" type="button" onClick={() => start()} disabled={busy || (!reviewId && !repo.trim())}>
              {busy ? (reviewId ? "Starting…" : "Reading the project…") : "Start chat"}
            </button>
            {!reviewId && (
              <button className="btn ghost" type="button" onClick={() => start(true)} disabled={busy}>Use the sample project instead</button>
            )}
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className="section chat" style={accentStyle(chat.persona_id)}>
      <div className="row">
        <Avatar id={chat.persona_id} />
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <h2>{names[chat.persona_id]}</h2>
          <span className="muted" style={{ fontSize: 13 }}>
            About {chat.project_name} · {chat.with_history ? "knows what the room said" : "clean start"}
          </span>
        </div>
        <button className="btn ghost" type="button" style={{ marginLeft: "auto" }} onClick={() => setChat(null)}>New chat</button>
      </div>

      {chat.messages.length === 0 && <p className="muted">Ask what they think, or push back on their view.</p>}
      {chat.messages.map((m, i) =>
        m.role === "user" ? (
          <div key={i} className="me">{m.text}</div>
        ) : (
          <div key={i} className="turn">
            <Avatar id={chat.persona_id} />
            <div className="bubble">
              <div className="row" style={{ gap: 8 }}>
                <span className="name">{names[chat.persona_id]}</span>
                {m.stance && <StanceBadge stance={m.stance} />}
                {m.stance_changed && m.stance && <span className="change">now {STANCE_LABEL[m.stance]}</span>}
              </div>
              <div className="msg">{m.text}</div>
              <Claims claims={m.claims ?? []} rejected={m.rejected ?? []} />
              {m.question && <div className="change">Asks you: {m.question}</div>}
            </div>
          </div>
        ),
      )}
      {busy && <div className="note thinking">{names[chat.persona_id]} is thinking</div>}
      {error && <div className="form-error">Could not get a reply: {error}</div>}
      <div ref={endRef} />

      <form className="bar" onSubmit={(e) => { e.preventDefault(); send(); }}>
        <label htmlFor="chat-msg" className="sr">Message {names[chat.persona_id]}</label>
        <input id="chat-msg" className="input" placeholder={`Message ${names[chat.persona_id]}…`} value={text}
               onChange={(e) => setText(e.target.value)} disabled={busy} maxLength={4000} />
        <button type="submit" className="send" aria-label="Send" disabled={busy || !text.trim()}>{Icon.send}</button>
      </form>
    </section>
  );
}
