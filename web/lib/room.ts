/** Fold the review's event stream into what the page shows. */
import type { Impression, Question, ReviewEvent, RouterNote, Stance, Summary, Turn, Verdict } from "./types";

export type Status = "idle" | "ingesting" | "running" | "paused" | "done" | "error";
export type PersonaState = "thinking" | "waiting" | "spoke" | "error";
export type FeedItem = { kind: "note"; note: RouterNote } | { kind: "turn"; turn: Turn }
  | { kind: "user"; to: string; text: string } | { kind: "missed"; count: number };

export type RoomState = {
  status: Status;
  capturing: boolean; // ingesting: the live site is being opened and photographed
  project: { name: string; repo_url: string; summary: string; files: number; demo_steps: number;
             site_url: string; site_views: number; site_logs: number; notes: string[] } | null;
  personaIds: string[];
  stance: Record<string, Stance>;
  personaState: Record<string, PersonaState>;
  impressions: Impression[];
  pending: Question[] | null; // questions waiting for the user
  answered: { question: Question; answer: string }[];
  feed: FeedItem[];
  speaking: string | null;
  verdicts: Verdict[];
  summary: Summary | null;
  round: 0 | 1 | 2 | 3;
  debateOver: boolean; // the moderator closed the debate: the room no longer takes messages
  error: string | null;
  usage: { calls: number; tokens: number } | null;
  usageBefore: { calls: number; tokens: number } | null; // spent before a retry, which starts a fresh count
};

export const emptyRoom: RoomState = {
  status: "idle",
  capturing: false,
  project: null,
  personaIds: [],
  stance: {},
  personaState: {},
  impressions: [],
  pending: null,
  answered: [],
  feed: [],
  speaking: null,
  verdicts: [],
  summary: null,
  round: 0,
  debateOver: false,
  error: null,
  usage: null,
  usageBefore: null,
};

export type Action = { type: "reset"; personaIds?: string[] } | { type: "event"; event: ReviewEvent };

export function roomReducer(s: RoomState, action: Action): RoomState {
  if (action.type === "reset") {
    const ids = action.personaIds ?? [];
    return { ...emptyRoom, status: ids.length ? "running" : "idle", personaIds: ids,
             personaState: Object.fromEntries(ids.map((p) => [p, "thinking" as const])) };
  }
  const e = action.event as any;
  switch (e.type) {
    case "status":
      return { ...s, status: "ingesting", capturing: e.stage === "site" };
    case "brief": {
      const ids: string[] = e.persona_ids ?? s.personaIds;
      return {
        ...s,
        status: "running",
        round: 1,
        personaIds: ids,
        personaState: Object.fromEntries(ids.map((p) => [p, "thinking" as const])),
        project: { name: e.project_name, repo_url: e.repo_url, summary: e.summary, files: e.files,
                   demo_steps: e.demo_steps, site_url: e.site_url ?? "", site_views: e.site_views ?? 0,
                   site_logs: e.site_logs ?? 0, notes: e.notes },
      };
    }
    case "impression":
      return {
        ...s,
        impressions: [...s.impressions, e as Impression],
        stance: { ...s.stance, [e.persona_id]: e.stance },
        personaState: { ...s.personaState, [e.persona_id]: "spoke" },
      };
    case "agent_error":
      return { ...s, personaState: { ...s.personaState, [e.persona_id]: "error" } };
    case "needs_answers": {
      const qs: Question[] = e.questions;
      const waiting = new Set(qs.flatMap((q) => q.asked_by));
      const ps = { ...s.personaState };
      waiting.forEach((p) => (ps[p] = "waiting"));
      return { ...s, pending: qs, personaState: ps };
    }
    case "paused":
      return { ...s, status: "paused" };
    case "resumed": {
      if (!e.retry) return { ...s, status: "running" };
      // a retry: whoever has no verdict yet is being asked again
      const done = new Set(s.verdicts.map((v) => v.persona_id));
      return { ...s, status: "running", error: null, usageBefore: s.usage,
               personaState: Object.fromEntries(s.personaIds.map((p) => [p, done.has(p) ? s.personaState[p] : "thinking" as const])) };
    }
    case "answers_received": {
      const answers: Record<string, string> = e.answers ?? {};
      const answered = (s.pending ?? []).map((q) => ({ question: q, answer: answers[q.id] ?? "" }));
      const ps = { ...s.personaState };
      for (const p of Object.keys(ps)) if (ps[p] === "waiting") ps[p] = "spoke";
      return { ...s, pending: null, answered: [...s.answered, ...answered], personaState: ps };
    }
    case "router": {
      const note = e as RouterNote;
      return {
        ...s,
        round: note.action === "end" ? 3 : Math.max(s.round, 2) as 2 | 3,
        debateOver: s.debateOver || note.action === "end",
        speaking: note.action === "speak" ? note.speaker : null,
        feed: note.action === "ask_user" ? s.feed : [...s.feed, { kind: "note", note }],
        personaState: note.action === "speak" && note.speaker
          ? { ...s.personaState, [note.speaker]: "thinking" }
          : note.action === "end"
            ? Object.fromEntries(Object.entries(s.personaState).map(([p, st]) => [p, st === "error" ? st : "thinking"]))
            : s.personaState,
      };
    }
    case "debate_turn": {
      const t = e as Turn;
      return {
        ...s,
        speaking: null,
        feed: [...s.feed, { kind: "turn", turn: t }],
        stance: t.error ? s.stance : { ...s.stance, [t.speaker]: t.stance },
        personaState: { ...s.personaState, [t.speaker]: t.error ? "error" : "spoke" },
      };
    }
    case "user_message":
      return { ...s, feed: [...s.feed, { kind: "user", to: e.to, text: e.text }] };
    case "user_message_missed":
      return { ...s, feed: [...s.feed, { kind: "missed", count: e.count }] };
    case "verdict":
      return {
        ...s,
        verdicts: [...s.verdicts, e as Verdict],
        stance: { ...s.stance, [e.persona_id]: e.verdict },
        personaState: { ...s.personaState, [e.persona_id]: "spoke" },
      };
    case "summary":
      return { ...s, summary: e as Summary };
    case "done":
      return { ...s, status: "done", round: 3, speaking: null };
    case "error":
      return { ...s, status: "error", error: e.message };
    case "usage":
      return { ...s, usage: { calls: e.calls + (s.usageBefore?.calls ?? 0), tokens: e.tokens + (s.usageBefore?.tokens ?? 0) } };
    default:
      return s;
  }
}

export const ROUND_LABEL: Record<number, string> = {
  0: "Not started",
  1: "Round 1 of 3 · First impressions",
  2: "Round 2 of 3 · Debate",
  3: "Round 3 of 3 · Verdicts",
};
