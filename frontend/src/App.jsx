import { useState, useEffect, useRef } from "react";
import { connect } from "./api.js";
import LeftPanel from "./components/LeftPanel.jsx";
import RightPanel from "./components/RightPanel.jsx";
import "./styles/globals.css";

const DEFAULT_FILTERS = {
  moviesOnly: true,
  minYear: 1920,
  minRating: 0,
  minVotes: 50000,
  maxDegrees: 6,
};

export default function App() {
  const [actorA, setActorA] = useState(null);
  const [actorB, setActorB] = useState(null);
  const [waypoints, setWaypoints] = useState([]);
  const [filters, setFilters] = useState(DEFAULT_FILTERS);

  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [resultVersion, setResultVersion] = useState(0);

  const debounceRef = useRef(null);

  // Build the actors array for the API request, expanding waypoint branches
  function buildActorsPayload() {
    const slots = [];
    slots.push({ nconst: actorA.nconst, name: actorA.name });
    for (const wp of waypoints) {
      const filled = wp.branches.map(b => b.actor).filter(Boolean);
      if (filled.length === 0) continue;
      if (filled.length === 1) {
        slots.push({ nconst: filled[0].nconst, name: filled[0].name });
      } else {
        slots.push(filled.map(a => ({ nconst: a.nconst, name: a.name })));
      }
    }
    slots.push({ nconst: actorB.nconst, name: actorB.name });
    return slots;
  }

  // Auto-search whenever inputs or filters change
  useEffect(() => {
    if (!actorA || !actorB) {
      setResults(null);
      setError(null);
      return;
    }

    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      setLoading(true);
      setError(null);
      try {
        const actors = buildActorsPayload();
        const apiFilters = {
          movies_only: filters.moviesOnly,
          min_year: filters.minYear > 1920 ? filters.minYear : null,
          min_rating: filters.minRating > 0 ? filters.minRating : null,
          min_votes: filters.minVotes > 0 ? filters.minVotes : null,
          max_degrees: filters.maxDegrees,
        };
        const data = await connect({ actors, filters: apiFilters });
        setResults(data);
        setResultVersion(v => v + 1);
      } catch (e) {
        if (e.name === "AbortError") return;
        setError(e.message || "Search failed");
      } finally {
        setLoading(false);
      }
    }, 500);

    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [actorA, actorB, waypoints, filters]);

  return (
    <div style={{ minHeight: "100vh", backgroundColor: "var(--bg)", color: "var(--text)", fontFamily: "'Newsreader', serif" }}>
      {/* Header */}
      <div style={{ borderBottom: "1px solid var(--border2)", padding: "24px 32px" }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 12 }}>
          <h1 style={{ fontSize: 22, fontWeight: 300, margin: 0, letterSpacing: "-0.02em", color: "var(--text)" }}>
            Six Degrees
          </h1>
          <span style={{ fontSize: 10, fontFamily: "'DM Mono', monospace", textTransform: "uppercase", letterSpacing: "0.15em", color: "var(--text-faint)" }}>
            Actor Connection Finder
          </span>
        </div>
      </div>

      {/* Body */}
      <div style={{ display: "flex", minHeight: "calc(100vh - 73px)" }}>
        <LeftPanel
          actorA={actorA} setActorA={setActorA}
          actorB={actorB} setActorB={setActorB}
          waypoints={waypoints} setWaypoints={setWaypoints}
          filters={filters} setFilters={setFilters}
          loading={loading}
        />
        <RightPanel
          results={results}
          loading={loading}
          error={error}
          resultVersion={resultVersion}
          onClear={() => { setResults(null); setError(null); }}
        />
      </div>
    </div>
  );
}
