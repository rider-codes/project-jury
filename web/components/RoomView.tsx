"use client";

import { useState } from "react";
import type { RoomState } from "@/lib/room";
import type { Persona } from "@/lib/types";
import { downloadPdf } from "@/lib/reportPdf";
import { Avatar, Claims, Gist, More, ReadMore, StanceBadge, accentStyle, evidenceLabel, plural, sentences_ } from "./bits";

type Props = {
  room: RoomState;
  names: Record<string, string>;
  personas: Persona[];
  onAnswer: (answers: Record<string, string>) => Promise<void>;
  onRetry?: () => Promise<void>; // run again only what failed
  readOnly?: boolean; // the public replay: questions are shown, not answered
  compact?: boolean; // the public replay: one claim per card, short debate turns
};

/** The first sentence, for the compact replay. */
function short(text: string): string {
  const parts = sentences_(text);
  return parts && parts.length > 1 ? parts.slice(0, 1).join("").trim() : text;
}

export function RoomView({ room, names, personas, onAnswer, onRetry, readOnly, compact }: Props) {
  const name = (id: string) => names[id] ?? id;
  // what a retry would run: reviewers with no verdict, or a summary the moderator could not write
  const over = room.status === "done" || room.status === "error";
  const unfinished = room.personaIds.filter((p) => !room.verdicts.some((v) => v.persona_id === p));
  const canRetry = !readOnly && !!onRetry && !!room.project && over &&
    (unfinished.length > 0 || !!room.summary?.error || room.status === "error");
  const questionCard = room.pending && room.status !== "done" ? (
    <QuestionCard key={room.pending.map((q) => q.id).join()} questions={room.pending} names={names}
                  onAnswer={onAnswer} ready={room.status === "paused"} readOnly={readOnly} />
  ) : null;
  return (
    <>
      {room.status === "ingesting" && <p className="muted">{room.capturing ? "Opening your live site and taking screenshots at desktop and phone width…" : "Reading the repository and building the project brief…"}</p>}
      {room.project && room.project.notes.length > 0 && (
        <More label={`${plural(room.project.notes.length, "note")} on what was read`}>
          <p className="muted" style={{ fontSize: 13, margin: 0 }}>{room.project.notes.join(" · ")}</p>
        </More>
      )}

      {room.round >= 1 && (
        <section className="section" aria-labelledby="r1">
          <div className="section-head">
            <div id="r1" className="label">Round 1 · First impressions</div>
            <div className="muted" style={{ fontSize: 13 }}>Each reviewer judged alone</div>
          </div>
          {/* the whole room reads as one conversation: each reviewer speaks in a chat bubble */}
          <div className="feed room-chat">
            {room.impressions.map((imp) => (
              <div key={imp.persona_id} className="turn" style={accentStyle(imp.persona_id)}>
                <Avatar id={imp.persona_id} />
                <div className="bubble">
                  <div className="row" style={{ gap: 8 }}>
                    <span className="name">{name(imp.persona_id)}</span>
                    <StanceBadge stance={imp.stance} />
                  </div>
                  <div className="msg">{imp.headline}</div>
                  {imp.claims.length + imp.rejected.length > 0 && (
                    <More label={`Why · ${plural(imp.claims.length, "point")} with evidence`}>
                      <Claims claims={imp.claims} rejected={imp.rejected} />
                    </More>
                  )}
                </div>
              </div>
            ))}
            {room.personaIds
              .filter((p) => room.personaState[p] === "error" && !room.impressions.some((i) => i.persona_id === p))
              .map((p) => (
                <div key={p} className="turn" style={accentStyle(p)}>
                  <Avatar id={p} />
                  <div className="bubble">
                    <span className="name">{name(p)}</span>
                    <div className="msg muted">Could not answer, so they sit out the rest of this review.</div>
                  </div>
                </div>
              ))}
          </div>
        </section>
      )}

      {room.answered.length > 0 && (
        <details className="section answered-list">
          <summary className="label" style={{ cursor: "pointer" }}>
            Your answers · {room.answered.length} question{room.answered.length > 1 ? "s" : ""} asked,{" "}
            {room.answered.filter((a) => a.answer).length} answered
          </summary>
          {/* as a conversation: the reviewer asks, you answer */}
          <div className="qa-chat">
            {room.answered.map(({ question, answer }) => {
              const who = question.asked_by?.[0];
              return (
                <div key={question.id} className="qa-pair">
                  <div className="turn" style={who ? accentStyle(who) : undefined}>
                    {who && <Avatar id={who} />}
                    <div className="bubble">
                      <span className="name">{question.asked_by?.map(name).join(", ") || "The room"}</span>
                      <div className="msg">{question.text}</div>
                    </div>
                  </div>
                  <div className="turn mine">
                    <div className="bubble">
                      <span className="name">You</span>
                      <div className="msg">{answer ? <Gist text={answer} /> : <em className="muted">Skipped</em>}</div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </details>
      )}

      {room.round < 2 && questionCard}

      {room.round >= 2 && (
        <section className="section" aria-labelledby="r2">
          <div id="r2" className="label">Round 2 · Debate</div>
          <div className="feed" role="log" aria-label="Debate" aria-live="polite">
          {room.feed.map((item, i) =>
            item.kind === "user" ? (
              <div key={i} className="turn mine">
                <div className="bubble">
                  <span className="name">You, to {item.to === "everyone" ? "the room" : name(item.to)}</span>
                  <div className="msg">{item.text}</div>
                </div>
              </div>
            ) : item.kind === "missed" ? (
              <div key={i} className="note">
                Moderator: the debate ended before the room could answer your last
                {item.count > 1 ? ` ${item.count} messages` : " message"}. Ask a reviewer directly below.
              </div>
            ) : item.kind === "note" ? (
              <div key={i} className="note">
                {item.note.action === "speak"
                  ? `Moderator: ${name(item.note.speaker!)} next — ${item.note.reason}`
                  : `Moderator: debate over — ${item.note.reason}`}
              </div>
            ) : (
              <div key={i} className="turn" style={accentStyle(item.turn.speaker)}>
                <Avatar id={item.turn.speaker} />
                <div className="bubble">
                  <div className="row" style={{ gap: 8 }}>
                    <span className="name">{name(item.turn.speaker)}</span>
                    {!item.turn.error && item.turn.stance && <StanceBadge stance={item.turn.stance} />}
                  </div>
                  {item.turn.contrarian && !item.turn.error && <span className="devil">arguing the other side</span>}
                  {item.turn.addressed_by_user && !item.turn.error && <span className="devil">answering you</span>}
                  {item.turn.error ? (
                    <div className="msg muted">Could not respond this turn.</div>
                  ) : (
                    <>
                      {compact ? <div className="msg">{short(item.turn.message)}</div>
                        : <ReadMore text={item.turn.message} animate={room.status === "running" && i === room.feed.length - 1} />}
                      {item.turn.stance_changed && (
                        <div className="change">
                          Changed stance to {item.turn.stance}: {item.turn.stance_change_reason}
                        </div>
                      )}
                      {!compact && item.turn.claims.length + item.turn.rejected.length > 0 && (
                        <More label={evidenceLabel(item.turn.claims.length, item.turn.rejected.length)}>
                          <Claims claims={item.turn.claims} rejected={item.turn.rejected} />
                        </More>
                      )}
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
          </div>
          {questionCard /* a debate question belongs under the turn that asked it */}
        </section>
      )}

      {room.round >= 3 && (
        <section className="section" aria-labelledby="r3">
          <div id="r3" className="label">Round 3 · Final verdicts</div>
          <div className="feed room-chat">
            {room.verdicts.map((v) => (
              <div key={v.persona_id} className="turn" style={accentStyle(v.persona_id)}>
                <Avatar id={v.persona_id} />
                <div className="bubble">
                  <div className="row" style={{ gap: 8 }}>
                    <span className="name">{name(v.persona_id)}</span>
                    <StanceBadge stance={v.verdict} />
                  </div>
                  <div className="msg"><strong>{v.headline}</strong></div>
                  {(
                    <>
                      {v.reasons.length + v.rejected.length > 0 && (
                        <More label={`Why · ${plural(v.reasons.length, "reason")} with evidence`}>
                          <Claims claims={v.reasons} rejected={v.rejected} />
                        </More>
                      )}
                      {v.what_would_change_my_mind.length > 0 && (
                        <More label="What would change my mind">
                          <ul className="more-list">{v.what_would_change_my_mind.map((w, i) => <li key={i}>{w}</li>)}</ul>
                        </More>
                      )}
                    </>
                  )}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {canRetry && (
        <RetryCard onRetry={onRetry!} stopped={room.status === "error" ? room.error : null}
                   who={unfinished.map(name)} summaryOnly={!unfinished.length && !!room.summary?.error} />
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
              {/* what to do next is the part people want; each point shows its gist and opens on click */}
              {room.summary.top_changes.length > 0 && (
                <div>
                  <div className="label" style={{ marginBottom: 6 }}>Top changes</div>
                  <ul className="more-list">{room.summary.top_changes.map((t, i) => <li key={i}><Gist text={t} /></li>)}</ul>
                </div>
              )}
              {[["Where they agreed", room.summary.agreed], ["Where they split", room.summary.split]].map(
                ([label, items]) =>
                  (items as string[]).length ? (
                    <More key={label as string} label={`${label} · ${(items as string[]).length}`}>
                      <ul className="more-list">{(items as string[]).map((t, i) => <li key={i}><Gist text={t} /></li>)}</ul>
                    </More>
                  ) : null,
              )}
              {room.usage && !readOnly && (
                <div className="evidence">{room.usage.calls} model calls · {room.usage.tokens.toLocaleString()} tokens</div>
              )}
              {!readOnly && room.status === "done" && room.project && <ReportButtons room={room} names={names} personas={personas} />}
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

function RetryCard({ onRetry, who, stopped, summaryOnly }: {
  onRetry: () => Promise<void>;
  who: string[];
  stopped: string | null;
  summaryOnly: boolean;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      await onRetry();
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  };
  const what = stopped
    ? "The review stopped before it finished."
    : summaryOnly
      ? "The moderator could not write the summary, so only the tally is shown."
      : `${who.join(", ")} did not give a verdict.`;
  return (
    <section className="retry" aria-labelledby="retry-title">
      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        <span id="retry-title" style={{ fontSize: 16, fontWeight: 800 }}>{what}</span>
        <span className="muted" style={{ fontSize: 13 }}>
          Run again only what failed. Everything that worked is kept
          {who.length ? `, and it takes up to ${2 * who.length + 1} model requests.` : "."}
        </span>
        {error && <div className="form-error">{error}</div>}
      </div>
      <button type="button" className="btn" onClick={run} disabled={busy}>{busy ? "Starting…" : "Try again"}</button>
    </section>
  );
}

function ReportButtons({ room, names, personas }: { room: RoomState; names: Record<string, string>; personas: Persona[] }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      await downloadPdf(room, names, Object.fromEntries(personas.map((p) => [p.id, p.verdict_question])));
    } catch (e) {
      setError(`Could not make the PDF: ${(e as Error).message}`);
    }
    setBusy(false);
  };
  return (
    <div className="row report-actions">
      <button type="button" className="btn" onClick={save} disabled={busy}>{busy ? "Making the PDF…" : "Download PDF"}</button>
      {error && <span className="form-error">{error}</span>}
    </div>
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
