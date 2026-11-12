export type Stance = "useful" | "unsure" | "not useful";

export type Persona = {
  id: string;
  name: string;
  tagline: string;
  tier: string;
  verdict_question: string;
  cares_about: string[];
  default: boolean;
};

export type Claim = {
  text: string;
  evidence: { kind: "file" | "demo" | "tree"; ref: string; quote: string };
};

export type Rejected = { text: string; problem: string };

export type Question = { id: string; text: string; asked_by: string[] };

export type Impression = {
  persona_id: string;
  stance: Stance;
  headline: string;
  claims: Claim[];
  questions: string[];
  rejected: Rejected[];
};

export type Turn = {
  speaker: string;
  message: string;
  claims: Claim[];
  rejected: Rejected[];
  stance: Stance;
  stance_changed: boolean;
  stance_change_reason: string | null;
  new_point: boolean;
  challenges: string[];
  open_question: string | null;
  error?: string;
};

export type RouterNote = { action: "speak" | "ask_user" | "end"; speaker: string | null; reason: string };

export type Verdict = {
  persona_id: string;
  verdict: Stance;
  headline: string;
  reasons: Claim[];
  what_would_change_my_mind: string[];
  rejected: Rejected[];
};

export type Summary = {
  headline: string;
  agreed: string[];
  split: string[];
  top_changes: string[];
  tally: Record<Stance, number>;
  generated_by: "model" | "code";
};

export type ReviewEvent = { type: string; [key: string]: unknown };

export type ReviewListItem = {
  id: string;
  project_name: string;
  repo_url: string;
  persona_ids: string[];
  created_at: string;
  status: string;
};

export type ChatMessage = {
  role: "user" | "agent";
  text: string;
  claims?: Claim[];
  rejected?: Rejected[];
  stance?: Stance;
  stance_changed?: boolean;
  question?: string | null;
};

export type Chat = {
  id: string;
  persona_id: string;
  project_name: string;
  room_thread: string | null;
  with_history: boolean;
  messages: ChatMessage[];
};
