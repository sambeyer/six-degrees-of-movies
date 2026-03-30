import BranchCard from "./BranchCard.jsx";
import GraphView from "./GraphView.jsx";

function EmptyState() {
  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 16, color: "var(--border)" }}>
      <svg width="64" height="64" viewBox="0 0 64 64" fill="none">
        <circle cx="20" cy="32" r="8" stroke="var(--border)" strokeWidth="1.5" />
        <circle cx="44" cy="32" r="8" stroke="var(--border)" strokeWidth="1.5" />
        <path d="M28 32 L36 32" stroke="var(--border)" strokeWidth="1.5" strokeDasharray="3 3" />
      </svg>
      <div style={{ fontSize: 13, fontFamily: "'DM Mono', monospace", color: "var(--text-ghost)", textAlign: "center", lineHeight: 1.8 }}>
        Enter two actors to find<br />their shortest connection
      </div>
    </div>
  );
}

function LoadingState() {
  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 20 }}>
      <div style={{ display: "flex", gap: 6 }}>
        {[0, 1, 2].map((i) => (
          <div key={i} style={{ width: 6, height: 6, borderRadius: "50%", backgroundColor: "var(--accent)", animation: `pulse 1.2s ease-in-out ${i * 0.2}s infinite` }} />
        ))}
      </div>
      <div style={{ fontSize: 12, fontFamily: "'DM Mono', monospace", color: "var(--text-faint)" }}>
        Traversing filmographies…
      </div>
    </div>
  );
}

export default function RightPanel({ results, loading, error, resultVersion, onClear }) {
  if (loading) return (
    <div style={{ flex: 1, padding: "24px 32px", overflowY: "auto" }}>
      <LoadingState />
    </div>
  );

  if (!results) return (
    <div style={{ flex: 1, padding: "24px 32px", overflowY: "auto" }}>
      {error
        ? <div style={{ fontFamily: "'DM Mono', monospace", fontSize: 12, color: "#c87070", padding: 16, background: "var(--surface)", borderRadius: 8 }}>{error}</div>
        : <EmptyState />}
    </div>
  );

  const paths = results.paths ?? [];
  const hasBranches = paths.length > 1;

  return (
    <div style={{ flex: 1, padding: "24px 32px", overflowY: "auto" }}>
      <div className="fade-in-up">
        {/* Header */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 24 }}>
          <span style={{ fontSize: 10, fontFamily: "'DM Mono', monospace", textTransform: "uppercase", letterSpacing: "0.12em", color: "var(--text-faint)" }}>
            {paths.length} path{paths.length !== 1 ? "s" : ""} found
            {results.elapsed_ms != null && (
              <span style={{ marginLeft: 8, color: "var(--text-ghost)" }}>· {results.elapsed_ms}ms</span>
            )}
          </span>
          <button
            onClick={onClear}
            style={{ background: "transparent", border: "1px solid var(--border)", borderRadius: 4, color: "var(--text-dim)", fontSize: 10, fontFamily: "'DM Mono', monospace", padding: "4px 10px", cursor: "pointer", textTransform: "uppercase", letterSpacing: "0.08em" }}
          >
            Clear
          </button>
        </div>

        {paths.length === 0 && (
          <div style={{ fontFamily: "'DM Mono', monospace", fontSize: 12, color: "var(--text-dim)" }}>
            No connection found within the current filters.
          </div>
        )}

        {/* Single path: full-width card. Multiple paths: side-by-side */}
        {paths.length === 1 ? (
          <BranchCard path={paths[0]} resultVersion={resultVersion} />
        ) : paths.length > 1 ? (
          <div style={{ display: "flex", gap: 16, overflowX: "auto" }}>
            {paths.map((path, i) => (
              <BranchCard
                key={i}
                path={path}
                resultVersion={resultVersion}
                label={`Branch ${String.fromCharCode(65 + i)}`}
              />
            ))}
          </div>
        ) : null}

        {/* Graph view — shows all shortest paths as a node/edge diagram */}
        {paths.length > 0 && (
          <div style={{ paddingBottom: 48 }}>
            <GraphView
              paths={paths}
              resultVersion={resultVersion}
            />
          </div>
        )}
      </div>
    </div>
  );
}
