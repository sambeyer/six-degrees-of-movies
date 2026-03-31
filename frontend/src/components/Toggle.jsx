export default function Toggle({ label, checked, onChange }) {
  const handleKeyDown = (e) => {
    if (e.key === " " || e.key === "Enter") {
      e.preventDefault();
      onChange(!checked);
    }
  };

  return (
    <label style={{ display: "flex", alignItems: "center", gap: 10, cursor: "pointer", userSelect: "none" }}>
      <div
        role="switch"
        aria-checked={checked}
        tabIndex={0}
        onClick={() => onChange(!checked)}
        onKeyDown={handleKeyDown}
        style={{
          width: 36, height: 20, borderRadius: 10,
          backgroundColor: checked ? "var(--accent)" : "var(--surface2)",
          border: `1px solid ${checked ? "var(--accent)" : "var(--border)"}`,
          position: "relative",
          transition: "background-color 0.2s, border-color 0.2s",
          flexShrink: 0,
        }}
      >
        <div style={{
          width: 14, height: 14, borderRadius: "50%",
          backgroundColor: checked ? "var(--bg)" : "var(--text-dim)",
          position: "absolute",
          top: 2, left: checked ? 19 : 2,
          transition: "left 0.2s, background-color 0.2s",
        }} />
      </div>
      <span style={{ fontSize: 11, fontFamily: "'DM Mono', monospace", textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--text-muted)" }}>
        {label}
      </span>
    </label>
  );
}
