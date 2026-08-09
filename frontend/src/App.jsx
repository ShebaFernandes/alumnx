import React, { useState } from "react";
import { api, CANDIDATE_ID } from "./api";
import EmailTable from "./components/EmailTable.jsx";
import ChatPanel from "./components/ChatPanel.jsx";
import StatsBar from "./components/StatsBar.jsx";

const PLACEHOLDER = `Paste a JSON array of emails here, e.g.:
[
  {
    "email_id": "em_00142",
    "thread_id": "th_0091",
    "from_name": "Suresh Kulkarni",
    "from_email": "s.kulkarni@meridiansteel.co.in",
    "subject": "RFP - Enterprise Document Management System",
    "body": "Dear Team, please find attached our RFP...",
    "received_at": "2026-08-01T09:14:22+05:30",
    "is_reply": false
  }
]`;

export default function App() {
  const [raw, setRaw] = useState("");
  const [emails, setEmails] = useState([]); // raw pasted batch (table view)
  const [ingestResult, setIngestResult] = useState(null);
  const [stats, setStats] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  function parseEmails(text) {
    const data = JSON.parse(text);
    const arr = Array.isArray(data) ? data : data.emails;
    if (!Array.isArray(arr)) throw new Error("Expected a JSON array of emails.");
    return arr;
  }

  // Step 2: render the pasted batch as a table BEFORE routing anything.
  function handleShowTable() {
    setError("");
    try {
      const arr = parseEmails(raw);
      setEmails(arr);
      setIngestResult(null);
    } catch (e) {
      setError("Could not parse JSON: " + e.message);
    }
  }

  async function handleLoadSample() {
    setError("");
    setBusy(true);
    try {
      const { emails: sample } = await api.sampleEmails(250);
      setRaw(JSON.stringify(sample, null, 2));
      setEmails(sample);
      setIngestResult(null);
    } catch (e) {
      setError("Failed to load sample emails: " + e.message);
    } finally {
      setBusy(false);
    }
  }

  function handleFile(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => setRaw(String(reader.result));
    reader.readAsText(file);
  }

  // Route the batch: send to /ingest, then refresh stats.
  async function handleRoute() {
    setError("");
    setBusy(true);
    try {
      const arr = emails.length ? emails : parseEmails(raw);
      setEmails(arr);
      const runId = "run_" + Date.now();
      const result = await api.ingest(arr, runId);
      setIngestResult(result);
      const s = await api.stats();
      setStats(s);
    } catch (e) {
      setError("Routing failed: " + e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="app">
      <header>
        <h1>Sales Inbox → Task Router</h1>
        <div className="cand">
          candidate_id: <code>{CANDIDATE_ID}</code>
          <span className="api">· API: <code>{api.base}</code></span>
        </div>
      </header>

      {/* Step 1: JSON input */}
      <section className="card">
        <h2>1 · Paste a batch of emails</h2>
        <textarea
          value={raw}
          onChange={(e) => setRaw(e.target.value)}
          placeholder={PLACEHOLDER}
          rows={10}
        />
        <div className="row">
          <button onClick={handleShowTable} disabled={busy}>Show as table</button>
          <button onClick={handleRoute} disabled={busy} className="primary">
            {busy ? "Working…" : "Route this batch"}
          </button>
          <label className="filebtn">
            Upload .json
            <input type="file" accept="application/json,.json" onChange={handleFile} hidden />
          </label>
          <button onClick={handleLoadSample} disabled={busy} className="ghost">
            Generate 250 sample emails
          </button>
        </div>
        {error && <p className="error">{error}</p>}
      </section>

      {/* Step 2: raw table */}
      {emails.length > 0 && (
        <section className="card">
          <h2>2 · Raw batch ({emails.length} emails)</h2>
          <p className="muted">
            This is the input exactly as received, before any routing.
          </p>
          <EmailTable emails={emails} />
        </section>
      )}

      {ingestResult && (
        <section className="card">
          <h2>Routing result</h2>
          <div className="pills">
            <span className="pill">processed {ingestResult.processed}</span>
            <span className="pill green">created {ingestResult.tasks_created}</span>
            <span className="pill blue">updated {ingestResult.tasks_updated}</span>
            <span className="pill gray">skipped {ingestResult.skipped}</span>
            {ingestResult.errors?.length > 0 && (
              <span className="pill red">errors {ingestResult.errors.length}</span>
            )}
          </div>
          {stats && <StatsBar stats={stats} />}
        </section>
      )}

      {/* Step 3: chat */}
      <section className="card">
        <h2>3 · Ask questions about this batch</h2>
        <p className="muted">
          Answers are grounded in the backend's stored classification data — not
          re-inferred from raw text. Try a zero-count or out-of-scope question.
        </p>
        <ChatPanel disabled={!ingestResult} />
      </section>

      <footer>
        Route the batch first, then ask the chat about it. Numbers come from{" "}
        <code>/api/chat</code> · <code>supporting_data</code>.
      </footer>
    </div>
  );
}
