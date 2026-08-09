import React from "react";

export default function StatsBar({ stats }) {
  const cats = stats.by_category || {};
  const skips = stats.skipped || {};
  return (
    <div className="stats">
      <div className="statgroup">
        <h4>By category</h4>
        {Object.keys(cats).length === 0 && <span className="muted">none</span>}
        {Object.entries(cats).map(([k, v]) => (
          <span key={k} className="pill">{k}: {v}</span>
        ))}
      </div>
      <div className="statgroup">
        <h4>Skipped (no task)</h4>
        {Object.keys(skips).length === 0 && <span className="muted">none</span>}
        {Object.entries(skips).map(([k, v]) => (
          <span key={k} className="pill gray">{k.replace("skipped_", "")}: {v}</span>
        ))}
      </div>
      <div className="statgroup">
        <h4>Spurious</h4>
        <span className="pill red">
          {stats.spurious_count} ({(stats.spurious_rate * 100).toFixed(1)}%)
        </span>
      </div>
    </div>
  );
}
