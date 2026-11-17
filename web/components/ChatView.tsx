"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { STANCE_LABEL } from "@/lib/personas";
import type { Chat, ChatMessage, Persona } from "@/lib/types";
import { Avatar, Claims, Icon, More, ReadMore, StanceBadge, Typed, accentStyle, evidenceLabel, plural } from "./bits";
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
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fresh, setFresh] = useState<number | null>(null); // index of a reply that just arrived, typed out
  const endRef = useRef<HTMLDivElement>(null);
  const names = Object.fromEntries(personas.map((p) => [p.id, p.name]));

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [chat?.messages.length]);

  const start = async () => {
    if (!reviewId) return; // one-on-one is reached from a review only
    setBusy(true);
    setError(null);
    try {
      const c = await api.startChat({ persona_id: persona, review_id: reviewId, with_history: withHistory && reviewDone });
      setChat(c);
      // a one-on-one review: this reviewer gives their own verdict first, then you can ask about it
      try {
        const v = await api.chatVerdict(c.id);
        setChat({ ...c, messages: [v] });
        setFresh(0);
      } catch (e) {
        setError(`Could not get their verdict: ${(e as Error).message}. You can still ask them directly.`);
      }
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
      setFresh(before.messages.length + 1);
    } catch (e) {
      setChat(before); // nothing was saved on the server either
      setText(mine.text);
      setError((e as Error).message);
    }
    setBusy(false);
  };

  if (!chat && !reviewId) {
    return <p className="muted">Start a review first, then pick a reviewer in the &ldquo;To:&rdquo; box to ask them about it.</p>;
  }

  if (!chat) {
    const p = personas.find((x) => x.id === persona);
    return (
      <section className="section">
        <div className="section-head"><h2>Who do you want to talk to?</h2></div>
        <PersonaPicker personas={personas} selected={[persona]} onToggle={setPersona} single />
        <div className="inputs">
          <div className="body">
            {p?.name} will answer &ldquo;{p?.verdict_question}&rdquo; about the project in this review.
          </div>
          <label className="check-row">
            <input type="checkbox" checked={withHistory} disabled={!reviewDone}
                   onChange={(e) => setWithHistory(e.target.checked)} />
            Bring in what the room said{!reviewDone && " (available when the review finishes)"}
          </label>
          {error && <div className="form-error">{error}</div>}
          <div className="row">
            <button className="btn" type="button" onClick={start} disabled={busy}>
              {busy ? `${p?.name ?? "They"} is reviewing…` : `Get ${p?.name ?? "their"}'s review`}
            </button>
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

      {chat.messages.length === 0 && !busy && <p className="muted">Ask what they think of the project.</p>}
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
              {m.kind === "verdict" ? (
                <>
                  <div className="label">Their review</div>
                  <div className="headline"><Typed text={m.headline ?? m.text} on={fresh === i} /></div>
                  {(m.claims?.length ?? 0) + (m.rejected?.length ?? 0) > 0 && (
                    <More label={`Why · ${plural(m.claims?.length ?? 0, "reason")} with evidence`}>
                      <Claims claims={m.claims ?? []} rejected={m.rejected ?? []} />
                    </More>
                  )}
                  {(m.what_would_change_my_mind?.length ?? 0) > 0 && (
                    <More label="What would change my mind">
                      <ul className="more-list">{m.what_would_change_my_mind!.map((w, j) => <li key={j}>{w}</li>)}</ul>
                    </More>
                  )}
                </>
              ) : (
                <>
                  <ReadMore text={m.text} sentences={3} animate={fresh === i} />
                  {(m.claims?.length ?? 0) + (m.rejected?.length ?? 0) > 0 && (
                    <More label={evidenceLabel(m.claims?.length ?? 0, m.rejected?.length ?? 0)}>
                      <Claims claims={m.claims ?? []} rejected={m.rejected ?? []} />
                    </More>
                  )}
                </>
              )}
              {m.question && <div className="change">Asks you: {m.question}</div>}
            </div>
          </div>
        ),
      )}
      {busy && <div className="note thinking">{names[chat.persona_id]} is {chat.messages.length ? "thinking" : "reading the project"}</div>}
      {error && <div className="form-error">Could not get a reply: {error}</div>}
      <div ref={endRef} />

      <form className="bar" onSubmit={(e) => { e.preventDefault(); send(); }}>
        <label htmlFor="chat-msg" className="sr">Message {names[chat.persona_id]}</label>
        <input id="chat-msg" className="input" placeholder={chat.messages.some((m) => m.kind === "verdict") ? "Ask about their review…" : `Message ${names[chat.persona_id]}…`} value={text}
               onChange={(e) => setText(e.target.value)} disabled={busy} maxLength={4000} />
        <button type="submit" className="send" aria-label="Send" disabled={busy || !text.trim()}>{Icon.send}</button>
      </form>
    </section>
  );
}
