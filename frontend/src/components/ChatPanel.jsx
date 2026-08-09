import React, { useState } from "react";
import { api } from "../api";

const SUGGESTIONS = [
  "How many emails this batch were proposal or RFP related?",
  "How many were marketing versus actual spam we correctly ignored?",
  "Show me everything sitting in triage and why.",
  "What's our spurious rate so far?",
  "Which tasks are high priority but low confidence?",
  "How many emails were about GST refunds?",
  "Send Aarti an email about the Meridian Steel RFP.",
];

export default function ChatPanel({ disabled, runId }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);

  async function send(text) {
    const q = (text ?? input).trim();
    if (!q) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", text: q }]);
    setBusy(true);
    try {
      const res = await api.chat(q, runId);
      setMessages((m) => [
        ...m,
        { role: "bot", text: res.answer, data: res.supporting_data },
      ]);
    } catch (e) {
      setMessages((m) => [...m, { role: "bot", text: "Error: " + e.message }]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="chat">
      <div className="suggestions">
        {SUGGESTIONS.map((s) => (
          <button key={s} className="chip" onClick={() => send(s)} disabled={busy}>
            {s}
          </button>
        ))}
      </div>

      <div className="messages">
        {messages.length === 0 && (
          <p className="muted">
            {disabled
              ? "Route a batch above, then ask about it here."
              : "Ask a question, or tap a suggestion."}
          </p>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>
            <div className="bubble">{m.text}</div>
            {m.data && Object.keys(m.data).length > 0 && (
              <pre className="supporting">
                supporting_data: {JSON.stringify(m.data, null, 2)}
              </pre>
            )}
          </div>
        ))}
      </div>

      <form
        className="chatinput"
        onSubmit={(e) => {
          e.preventDefault();
          send();
        }}
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about the batch…"
          disabled={busy}
        />
        <button type="submit" className="primary" disabled={busy}>
          {busy ? "…" : "Ask"}
        </button>
      </form>
    </div>
  );
}
