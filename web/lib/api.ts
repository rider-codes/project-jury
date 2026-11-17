import { getKey } from "./key";
import type { Chat, ChatListItem, ChatMessage, Persona, ReviewListItem } from "./types";

// A production build is served by the API server itself, so it talks to its own origin.
// `npm run dev` runs on :3000 next to the API on :8000.
export const API =
  process.env.NEXT_PUBLIC_API_URL ?? (process.env.NODE_ENV === "production" ? "" : "http://localhost:8000");

/** The start of the server's message when the shared free quota is gone (see POOL_EMPTY in app.py). */
export const POOL_EMPTY = "The free quota for today is used up";

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const key = getKey();
  const res = await fetch(`${API}${path}`, {
    ...init,
    // `npm run dev` is on another port than the API, so the access cookie must be sent explicitly
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      // the visitor's own key, when they gave one: it pays for their runs instead of the shared quota
      ...(key ? { "X-Jury-Key": key } : {}),
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) {
    let detail = `${res.status}`;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {}
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

const post = <T,>(path: string, body: unknown) => call<T>(path, { method: "POST", body: JSON.stringify(body) });

export type Quota = {
  demo_model: boolean;
  free_quota: { remaining: number; limit: number } | null;
  site_calls?: number; // vision calls a live site adds
  byok?: boolean; // this deployment accepts a visitor's own key
  own_key?: boolean; // the request carried one
  exhausted?: boolean; // the shared free quota is gone, so ask for a key
};

export const api = {
  session: () => call<{ needs_code: boolean; ok: boolean }>("/api/session"),
  login: (code: string) => post<{ ok: true }>("/api/login", { code }),
  personas: () => call<Persona[]>("/api/personas"),
  quota: () => call<Quota>("/api/quota"),
  reviews: () => call<ReviewListItem[]>("/api/reviews"),
  startReview: (body: { repo_url?: string; site_url?: string; demo?: string; sample?: boolean; persona_ids: string[] }) =>
    post<{ id: string }>("/api/reviews", body),
  answer: (id: string, answers: Record<string, string>) => post<{ ok: true }>(`/api/reviews/${id}/answers`, { answers }),
  say: (id: string, to: string, text: string) => post<{ ok: true }>(`/api/reviews/${id}/messages`, { to, text }),
  retry: (id: string) => post<{ impressions: string[]; verdicts: string[]; summary: boolean }>(`/api/reviews/${id}/retry`, {}),
  startChat: (body: { persona_id: string; review_id?: string; with_history?: boolean; sample?: boolean; repo_url?: string; site_url?: string; demo?: string }) =>
    post<Chat>("/api/chats", body),
  chats: () => call<ChatListItem[]>("/api/chats"),
  chat: (id: string) => call<Chat>(`/api/chats/${id}`),
  sendChat: (id: string, text: string) => post<ChatMessage>(`/api/chats/${id}/messages`, { text }),
  chatVerdict: (id: string) => post<ChatMessage>(`/api/chats/${id}/verdict`, {}),
  eventsUrl: (id: string) => `${API}/api/reviews/${id}/events`,
};
