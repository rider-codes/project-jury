import type { Chat, ChatMessage, Persona, ReviewListItem } from "./types";

// A production build is served by the API server itself, so it talks to its own origin.
// `npm run dev` runs on :3000 next to the API on :8000.
export const API =
  process.env.NEXT_PUBLIC_API_URL ?? (process.env.NODE_ENV === "production" ? "" : "http://localhost:8000");

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
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

export const api = {
  session: () => call<{ needs_code: boolean; ok: boolean }>("/api/session"),
  login: (code: string) => post<{ ok: true }>("/api/login", { code }),
  personas: () => call<Persona[]>("/api/personas"),
  quota: () => call<{ demo_model: boolean; free_quota: { remaining: number; limit: number } | null }>("/api/quota"),
  reviews: () => call<ReviewListItem[]>("/api/reviews"),
  startReview: (body: { repo_url?: string; demo?: string; sample?: boolean; persona_ids: string[] }) =>
    post<{ id: string }>("/api/reviews", body),
  answer: (id: string, answers: Record<string, string>) => post<{ ok: true }>(`/api/reviews/${id}/answers`, { answers }),
  startChat: (body: { persona_id: string; review_id?: string; with_history?: boolean; sample?: boolean }) =>
    post<Chat>("/api/chats", body),
  chat: (id: string) => call<Chat>(`/api/chats/${id}`),
  sendChat: (id: string, text: string) => post<ChatMessage>(`/api/chats/${id}/messages`, { text }),
  eventsUrl: (id: string) => `${API}/api/reviews/${id}/events`,
};
