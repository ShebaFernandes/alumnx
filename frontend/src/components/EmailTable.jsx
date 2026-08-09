import React from "react";

// Plain data table: one row per email, exactly as received (§7.3 step 2).
export default function EmailTable({ emails }) {
  return (
    <div className="tablewrap">
      <table>
        <thead>
          <tr>
            <th>from_name</th>
            <th>from_email</th>
            <th>subject</th>
            <th>received_at</th>
            <th>thread_id</th>
            <th>body (preview)</th>
          </tr>
        </thead>
        <tbody>
          {emails.map((e, i) => (
            <tr key={e.email_id || i}>
              <td>{e.from_name || "—"}</td>
              <td className="mono">{e.from_email || "—"}</td>
              <td>{e.subject || "—"}</td>
              <td className="mono">{fmtDate(e.received_at)}</td>
              <td className="mono">{e.thread_id || "—"}</td>
              <td className="preview">{truncate(e.body, 90)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function truncate(s, n) {
  if (!s) return "—";
  const clean = String(s).replace(/\s+/g, " ").trim();
  return clean.length > n ? clean.slice(0, n) + "…" : clean;
}

function fmtDate(s) {
  if (!s) return "—";
  return String(s).replace("T", " ").slice(0, 16);
}
