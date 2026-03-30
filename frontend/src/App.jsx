import { useState, useEffect, useRef, useCallback } from "react";
import { connect, randomActors } from "./api.js";
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

// ---------------------------------------------------------------------------
// URL state serialisation
// Actor format:  "nconst|name"
// Waypoint format: one `w` param per waypoint; branches within separated by "+"
//   e.g. w=nm1234|John+nm5678|Jane  (two branches in one waypoint)
// ---------------------------------------------------------------------------

function actorToParam(actor) {
  return `${actor.nconst}|${actor.name}`;
}

function actorFromParam(s) {
  const idx = s.indexOf("|");
  if (idx === -1) return null;
  return { nconst: s.slice(0, idx), name: decodeURIComponent(s.slice(idx + 1)) };
}

function stateToUrl(actorA, actorB, waypoints, filters) {
  const p = new URLSearchParams();
  if (actorA) p.set("a", actorToParam(actorA));
  if (actorB) p.set("b", actorToParam(actorB));

  // Only encode filters that differ from defaults
  if (filters.moviesOnly !== DEFAULT_FILTERS.moviesOnly) p.set("mo", filters.moviesOnly ? "1" : "0");
  if (filters.minYear !== DEFAULT_FILTERS.minYear) p.set("yr", filters.minYear);
  if (filters.minRating !== DEFAULT_FILTERS.minRating) p.set("rt", filters.minRating);
  if (filters.minVotes !== DEFAULT_FILTERS.minVotes) p.set("vt", filters.minVotes);
  if (filters.maxDegrees !== DEFAULT_FILTERS.maxDegrees) p.set("dg", filters.maxDegrees);

  // Waypoints: each as a `w` param, branches joined by "+"
  for (const wp of waypoints) {
    const filled = wp.branches.map(b => b.actor).filter(Boolean);
    if (filled.length > 0) {
      p.append("w", filled.map(actorToParam).join("+"));
    }
  }

  return p.toString() ? `?${p.toString()}` : "";
}

let _wpIdCounter = 1;

function urlToState() {
  const p = new URLSearchParams(window.location.search);

  const actorA = p.has("a") ? actorFromParam(p.get("a")) : null;
  const actorB = p.has("b") ? actorFromParam(p.get("b")) : null;

  const filters = {
    moviesOnly: p.has("mo") ? p.get("mo") === "1" : DEFAULT_FILTERS.moviesOnly,
    minYear: p.has("yr") ? Number(p.get("yr")) : DEFAULT_FILTERS.minYear,
    minRating: p.has("rt") ? Number(p.get("rt")) : DEFAULT_FILTERS.minRating,
    minVotes: p.has("vt") ? Number(p.get("vt")) : DEFAULT_FILTERS.minVotes,
    maxDegrees: p.has("dg") ? Number(p.get("dg")) : DEFAULT_FILTERS.maxDegrees,
  };

  const waypoints = p.getAll("w").map((wStr) => {
    const branches = wStr.split("+").map((s) => {
      const actor = actorFromParam(s);
      return { id: _wpIdCounter++, actor };
    }).filter(b => b.actor !== null);
    return { id: _wpIdCounter++, branches };
  });

  return { actorA, actorB, filters, waypoints };
}

export default function App() {
  const initial = urlToState();

  const [actorA, setActorA] = useState(initial.actorA);
  const [actorB, setActorB] = useState(initial.actorB);
  const [waypoints, setWaypoints] = useState(initial.waypoints);
  const [filters, setFilters] = useState(initial.filters);

  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [resultVersion, setResultVersion] = useState(0);

  const debounceRef = useRef(null);
  const isPopState = useRef(false);

  // Pick random actors on first load if none are set via URL
  useEffect(() => {
    if (!actorA && !actorB) {
      randomActors().then((actors) => {
        if (actors.length >= 2) {
          setActorA(actors[0]);
          setActorB(actors[1]);
        }
      }).catch(() => {});
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Build the actors array for the API request, expanding waypoint branches
  const buildActorsPayload = useCallback(() => {
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
  }, [actorA, actorB, waypoints]);

  // Sync state → URL (pushState)
  useEffect(() => {
    if (isPopState.current) {
      isPopState.current = false;
      return;
    }
    const url = stateToUrl(actorA, actorB, waypoints, filters);
    const current = window.location.search || "";
    const next = url || "";
    if (next !== current) {
      window.history.pushState(null, "", next || window.location.pathname);
    }
  }, [actorA, actorB, waypoints, filters]);

  // Handle browser back/forward
  useEffect(() => {
    const handler = () => {
      isPopState.current = true;
      const s = urlToState();
      setActorA(s.actorA);
      setActorB(s.actorB);
      setWaypoints(s.waypoints);
      setFilters(s.filters);
      setResults(null);
      setError(null);
    };
    window.addEventListener("popstate", handler);
    return () => window.removeEventListener("popstate", handler);
  }, []);

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
      <div className="app-body" style={{ display: "flex", minHeight: "calc(100vh - 73px)" }}>
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
