// All backend calls go through here. The browser NEVER talks to Gemini or the
// Task API directly — only to our own backend (§7.2).

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";
export const CANDIDATE_ID =
  import.meta.env.VITE_CANDIDATE_ID || "shebafernandes5@gmail.com";

async function req(path, opts = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status}: ${text}`);
  }
  return res.json();
}

export const api = {
  base: API_BASE,

  ingest: (emails, runId) =>
    req("/ingest", {
      method: "POST",
      body: JSON.stringify({ candidate_id: CANDIDATE_ID, emails, run_id: runId }),
    }),

  stats: () => req(`/api/stats?candidate_id=${encodeURIComponent(CANDIDATE_ID)}`),

  emails: () => req(`/api/emails?candidate_id=${encodeURIComponent(CANDIDATE_ID)}`),

  tasks: () => req(`/api/tasks?candidate_id=${encodeURIComponent(CANDIDATE_ID)}`),

  sampleEmails: (count = 250) => req(`/api/sample-emails?count=${count}`),

  chat: (query) =>
    req("/api/chat", {
      method: "POST",
      body: JSON.stringify({ candidate_id: CANDIDATE_ID, query }),
    }),
};
