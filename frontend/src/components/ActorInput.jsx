import { useState, useEffect, useRef, useCallback } from "react";
import { searchActors } from "../api.js";

export default function ActorInput({
  value,          // display string
  onSelect,       // ({nconst, name}) => void  — called when a suggestion is confirmed
  onClear,        // () => void               — called when input is cleared
  placeholder,
  label,          // left-hand label (index circle or letter)
  showRemove,
  onRemove,
  style,
  inputStyle,
}) {
  const [text, setText] = useState(value || "");
  const [suggestions, setSuggestions] = useState([]);
  const [open, setOpen] = useState(false);
  const [highlighted, setHighlighted] = useState(0);
  const debounceRef = useRef(null);
  const containerRef = useRef(null);

  // Sync display text when value prop changes (e.g. cleared from parent)
  useEffect(() => {
    setText(value || "");
  }, [value]);

  const fetchSuggestions = useCallback((q) => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (!q || q.length < 2) { setSuggestions([]); setOpen(false); return; }
    debounceRef.current = setTimeout(async () => {
      const results = await searchActors(q);
      setSuggestions(results);
      setOpen(results.length > 0);
      setHighlighted(0);
    }, 220);
  }, []);

  const handleChange = (e) => {
    const v = e.target.value;
    setText(v);
    if (!v) { onClear?.(); setSuggestions([]); setOpen(false); return; }
    fetchSuggestions(v);
  };

  const confirm = (actor) => {
    setText(actor.name);
    setSuggestions([]);
    setOpen(false);
    onSelect(actor);
  };

  const handleKeyDown = (e) => {
    if (!open) return;
    if (e.key === "ArrowDown") { e.preventDefault(); setHighlighted(h => Math.min(h + 1, suggestions.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setHighlighted(h => Math.max(h - 1, 0)); }
    else if (e.key === "Enter") { e.preventDefault(); if (suggestions[highlighted]) confirm(suggestions[highlighted]); }
    else if (e.key === "Escape") { setOpen(false); }
  };

  // Close dropdown on outside click
  useEffect(() => {
    const handler = (e) => {
      if (containerRef.current && !containerRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  return (
    <div ref={containerRef} style={{ display: "flex", alignItems: "center", gap: 8, position: "relative", ...style }}>
      {/* Label circle */}
      {label !== undefined && (
        <div style={{
          width: 28, height: 28, borderRadius: "50%",
          border: "1px solid var(--border)", display: "flex",
          alignItems: "center", justifyContent: "center",
          fontSize: 11, fontFamily: "'DM Mono', monospace",
          color: "var(--text-dim)", flexShrink: 0,
        }}>
          {label}
        </div>
      )}

      {/* Input */}
      <input
        type="text"
        value={text}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        onFocus={() => suggestions.length > 0 && setOpen(true)}
        placeholder={placeholder}
        autoComplete="off"
        style={{
          flex: 1,
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: 6,
          padding: "10px 14px",
          color: "var(--text)",
          fontSize: 14,
          fontFamily: "'Newsreader', serif",
          outline: "none",
          transition: "border-color 0.15s",
          ...inputStyle,
        }}
        onFocus={(e) => { e.target.style.borderColor = "var(--accent)"; suggestions.length > 0 && setOpen(true); }}
        onBlur={(e) => { e.target.style.borderColor = "var(--border)"; }}
      />

      {/* Remove button */}
      {showRemove && (
        <button
          onClick={onRemove}
          style={{
            width: 28, height: 28, borderRadius: "50%",
            border: "1px solid var(--border)", background: "transparent",
            color: "var(--text-dim)", cursor: "pointer",
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 16, flexShrink: 0, transition: "all 0.15s",
          }}
          onMouseEnter={(e) => { e.currentTarget.style.borderColor = "var(--accent)"; e.currentTarget.style.color = "var(--accent)"; }}
          onMouseLeave={(e) => { e.currentTarget.style.borderColor = "var(--border)"; e.currentTarget.style.color = "var(--text-dim)"; }}
        >
          ×
        </button>
      )}

      {/* Dropdown */}
      {open && suggestions.length > 0 && (
        <div style={{
          position: "absolute",
          top: "100%",
          left: label !== undefined ? 36 : 0,
          right: showRemove ? 36 : 0,
          zIndex: 100,
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: 6,
          marginTop: 4,
          overflow: "hidden",
          boxShadow: "0 8px 24px rgba(0,0,0,0.5)",
        }}>
          {suggestions.map((s, i) => (
            <div
              key={s.nconst}
              onMouseDown={() => confirm(s)}
              onMouseEnter={() => setHighlighted(i)}
              style={{
                padding: "9px 14px",
                fontSize: 13,
                fontFamily: "'Newsreader', serif",
                color: i === highlighted ? "var(--text)" : "var(--text-muted)",
                background: i === highlighted ? "var(--surface2)" : "transparent",
                cursor: "pointer",
                borderBottom: i < suggestions.length - 1 ? "1px solid var(--border2)" : "none",
              }}
            >
              <div>{s.name}</div>
              {s.known_for && (
                <div style={{
                  fontSize: 10, fontFamily: "'DM Mono', monospace",
                  color: i === highlighted ? "var(--text-dim)" : "var(--text-faint)",
                  marginTop: 2,
                }}>
                  {s.known_for}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
