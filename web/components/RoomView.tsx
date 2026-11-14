"use client";

import { useState } from "react";
import type { RoomState } from "@/lib/room";
import type { Persona } from "@/lib/types";
import { Avatar, Claims, StanceBadge, accentStyle } from "./bits";

type Props = {
  room: RoomState;
  names: Record<string, string>;
  personas: Persona[];
  onAnswer: (answers: Record<string, string>) => Promise<void>;
  readOnly?: boolean; // the public replay: questions are shown, not answered
  compact?: boolean; // the public replay: one claim per card, short debate turns
};

/** The first sentence, for the compact replay. */
function short(text: string): string {
  const parts = text.match(/[^.!?]+[.!?]+(\s|$)/g);
  return parts && parts.length > 1 ? parts.slice(0, 1).join("").trim() : text;
}

export function RoomView({ room, names, onAnswer, readOnly, compact }: Props) {
  const limit = compact ? 1 : undefined;
  const name = (id: string) => names[id] ?? id;
  const questionCard = room.pending && room.status !== "done" ? (
    <QuestionCard key={room.pending.map((q) => q.id).join()} questions={room.pending} names={names}
                  onAnswer={onAnswer} ready={room.status === "paused"} readOnly={readOnly} />
  ) : null;
  return (
    <>
      {room.status === "ingesting" && <p className="muted">Reading the repository and building the project brief…</p>}
      {room.project && room.project.notes.length > 0 && (
        <p className="muted" style={{ fontSize: 13 }}>Brief notes: {room.project.notes.join(" · ")}</p>
      )}

      {room.round >= 1 && (
        <section className="section" aria-labelledby="r1">
          <div className="section-head">
            <div id="r1" className="label">Round 1 · First impressions</div>
            <div className="muted" style={{ fontSize: 13 }}>Each reviewer judged alone</div>
          </div>
          <div className="grid">
            {room.impressions.map((imp) => (
              <article key={imp.persona_id} className="card" style={accentStyle(imp.persona_id)}>
                <div className="card-head">
                  <Avatar id={imp.persona_id} />
                  <span className="who">The {name(imp.persona_id)}</span>
                  <StanceBadge stance={imp.stance} />
                </div>
                <div className="headline">{imp.headline}</div>
                <Claims claims={imp.claims} rejected={imp.rejected} limit={limit} brief={compact} />
              </article>
            ))}
            {room.personaIds
              .filter((p) => room.personaState[p] === "error" && !room.impressions.some((i) => i.persona_id === p))
              .map((p) => (
                <article key={p} className="card" style={accentStyle(p)}>
                  <div className="card-head"><Avatar id={p} /><span className="who">The {name(p)}</span></div>
                  <div className="body">Could not answer, so they sit out the rest of this review.</div>
                </article>
              ))}
          </div>
        </section>
      )}

      {room.answered.length > 0 && (
        <details className="section answered-list" open={room.answered.length <= 3}>
          <summary className="label" style={{ cursor: "pointer" }}>
            Your answers · {room.answered.length} question{room.answered.length > 1 ? "s" : ""} asked,{" "}
            {room.answered.filter((a) => a.answer).length} answered
          </summary>
          {room.answered.map(({ question, answer }) => (
            <div key={question.id} className="answered">
              <strong style={{ color: "var(--text-2)" }}>{question.text}</strong>
              <br />
              {answer ? answer : <em>Skipped</em>}
            </div>
          ))}
        </details>
      )}

      {room.round < 2 && questionCard}

      {room.round >= 2 && (
        <section className="section" aria-labelledby="r2">
          <div id="r2" className="label">Round 2 · Debate</div>
          {room.feed.map((item, i) =>
            item.kind === "note" ? (
              <div key={i} className="note">
                {item.note.action === "speak"
                  ? `Moderator: ${name(item.note.speaker!)} next — ${item.note.reason}`
                  : `Moderator: debate over — ${item.note.reason}`}
              </div>
            ) : (
              <div key={i} className="turn" style={accentStyle(item.turn.speaker)}>
                <Avatar id={item.turn.speaker} />
                <div className="bubble">
                  <span className="name">{name(item.turn.speaker)}</span>
                  {item.turn.error ? (
                    <div className="msg muted">Could not respond this turn.</div>
                  ) : (
                    <>
                      <div className="msg">{compact ? short(item.turn.message) : item.turn.message}</div>
                      {item.turn.stance_changed && (
                        <div className="change">
                          Changed stance to {item.turn.stance}: {item.turn.stance_change_reason}
                        </div>
                      )}
                      {!compact && <Claims claims={item.turn.claims} rejected={item.turn.rejected} />}
                      {item.turn.challenges.length > 0 && (
                        <div className="evidence">challenges {item.turn.challenges.map(name).join(", ")}</div>
                      )}
                    </>
                  )}
                </div>
              </div>
            ),
          )}
          {room.speaking && room.status === "running" && (
            <div className="note thinking">{name(room.speaking)} is thinking</div>
          )}
          {questionCard /* a debate question belongs under the turn that asked it */}
        </section>
      )}

      {room.round >= 3 && (
        <section className="section" aria-labelledby="r3">
          <div id="r3" className="label">Round 3 · Final verdicts</div>
          <div className="grid">
            {room.verdicts.map((v) => (
              <article key={v.persona_id} className="card" style={accentStyle(v.persona_id)}>
                <div className="card-head">
                  <Avatar id={v.persona_id} />
                  <span className="who">The {name(v.persona_id)}</span>
                  <StanceBadge stance={v.verdict} />
                </div>
                <div className="headline">{v.headline}</div>
                <Claims claims={v.reasons} rejected={v.rejected} limit={limit} brief={compact} />
                {!compact && v.what_would_change_my_mind.length > 0 && (
                  <div className="body" style={{ fontSize: 14 }}>
                    <strong>What would change my mind:</strong>
                    <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>
                      {v.what_would_change_my_mind.slice(0, compact ? 1 : undefined).map((w, i) => <li key={i}>{w}</li>)}
                    </ul>
                  </div>
                )}
              </article>
            ))}
          </div>
        </section>
      )}

      {room.status !== "idle" && (
        <section className={`summary ${room.summary ? "ready" : ""}`} aria-labelledby="sum">
          <h2 id="sum">Final summary</h2>
          {room.summary ? (
            <>
              <div className="tally">
                {(["useful", "unsure", "not useful"] as const).map((s) =>
                  room.summary!.tally[s] ? (
                    <span key={s} className="row" style={{ gap: 6 }}>
                      <StanceBadge stance={s} /> <span className="mono">×{room.summary!.tally[s]}</span>
                    </span>
                  ) : null,
                )}
              </div>
              <div className="headline">{room.summary.headline}</div>
              {[["Agreed", room.summary.agreed], ["Split", room.summary.split], ["Top changes", room.summary.top_changes]].map(
                ([label, items]) =>
                  (items as string[]).length ? (
                    <div key={label as string}>
                      <div className="label" style={{ marginBottom: 6 }}>{label as string}</div>
                      <ul>{(items as string[]).map((t, i) => <li key={i}>{t}</li>)}</ul>
                    </div>
                  ) : null,
              )}
              {room.usage && (
                <div className="evidence">{room.usage.calls} model calls · {room.usage.tokens.toLocaleString()} tokens</div>
              )}
            </>
          ) : room.status === "error" ? (
            <div className="form-error">The review stopped: {room.error}</div>
          ) : (
            <div className="body muted">
              Appears after round 3. The moderator writes it from each verdict and shows where reviewers agreed and split.
            </div>
          )}
        </section>
      )}
    </>
  );
}

function QuestionCard({ questions, names, onAnswer, ready, readOnly }: {
  questions: { id: string; text: string; asked_by: string[] }[];
  names: Record<string, string>;
  onAnswer: (a: Record<string, string>) => Promise<void>;
  ready: boolean;
  readOnly?: boolean;
}) {
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const first = questions[0]?.asked_by[0];
  const submit = async () => {
    setSending(true);
    setError(null);
    try {
      await onAnswer(Object.fromEntries(questions.map((q) => [q.id, (answers[q.id] ?? "").trim()])));
    } catch (e) {
      setError((e as Error).message);
      setSending(false);
    }
  };
  return (
    <section className="ask" aria-labelledby="ask-title">
      <div className="card-head">
        {first && <Avatar id={first} />}
        <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
          <span id="ask-title" style={{ fontSize: 16, fontWeight: 800 }}>
            The room has {questions.length === 1 ? "a question" : `${questions.length} questions`}
          </span>
          <span style={{ fontSize: 13, fontWeight: 700, color: "var(--ask)" }}>
            {readOnly ? "In a live review the room pauses here for your answers. In this run they were skipped." : "Waiting for your reply · leave one blank to skip it"}
          </span>
        </div>
      </div>
      {questions.map((q) => (
        <div key={q.id} className="ask-q">
          <label htmlFor={`a-${q.id}`} className="text">{q.text}</label>
          <span className="evidence">asked by {q.asked_by.map((p) => names[p] ?? p).join(", ")}</span>
          {!readOnly && <textarea
            id={`a-${q.id}`}
            className="textarea"
            placeholder="Type your answer"
            value={answers[q.id] ?? ""}
            onChange={(e) => setAnswers({ ...answers, [q.id]: e.target.value })}
          />}
        </div>
      ))}
      {error && <div className="form-error">{error}</div>}
      {!readOnly && <div className="row">
        <button type="button" className="btn" onClick={submit} disabled={sending || !ready}>
          {sending ? "Sending…" : "Send answers"}
        </button>
      </div>}
    </section>
  );
}
