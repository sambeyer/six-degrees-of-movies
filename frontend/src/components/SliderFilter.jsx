import { useState, useRef } from "react";

export default function SliderFilter({ label, value, onChange, min, max, step = 1, format }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const inputRef = useRef(null);

  function startEdit() {
    setDraft(String(value));
    setEditing(true);
    setTimeout(() => inputRef.current?.select(), 0);
  }

  function commitEdit() {
    const raw = parseFloat(draft);
    if (!isNaN(raw)) {
      const clamped = Math.min(max, Math.max(min, Math.round(raw / step) * step));
      onChange(clamped);
    }
    setEditing(false);
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <span style={{
          fontSize: 11, fontFamily: "'DM Mono', monospace",
          textTransform: "uppercase", letterSpacing: "0.08em",
          color: "var(--text-muted)",
        }}>
          {label}
        </span>
        {editing ? (
          <input
            ref={inputRef}
            type="number"
            value={draft}
            min={min}
            max={max}
            step={step}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={commitEdit}
            onKeyDown={(e) => {
              if (e.key === "Enter") { e.preventDefault(); commitEdit(); }
              if (e.key === "Escape") setEditing(false);
            }}
            style={{
              width: 90, fontSize: 13, fontFamily: "'DM Mono', monospace",
              background: "var(--surface2)", border: "1px solid var(--accent)",
              borderRadius: 3, color: "var(--text)", padding: "1px 6px",
              textAlign: "right", outline: "none",
            }}
          />
        ) : (
          <span
            onClick={startEdit}
            title="Click to type a value"
            style={{
              fontSize: 13, fontFamily: "'DM Mono', monospace",
              color: "var(--text)", cursor: "text",
              textDecoration: "underline dotted var(--border2)",
              textUnderlineOffset: 3,
            }}
          >
            {format ? format(value) : value}
          </span>
        )}
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
      />
    </div>
  );
}
