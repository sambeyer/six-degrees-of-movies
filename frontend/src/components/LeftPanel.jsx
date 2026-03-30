import { useCallback, useState, useEffect } from "react";
import ActorInput from "./ActorInput.jsx";
import SliderFilter from "./SliderFilter.jsx";
import Toggle from "./Toggle.jsx";

// Small connector line between inputs
function Connector() {
  return (
    <div style={{ position: "absolute", left: 13, top: -10, width: 1, height: 10, backgroundColor: "var(--border)" }} />
  );
}

export default function LeftPanel({
  actorA, setActorA,
  actorB, setActorB,
  waypoints, setWaypoints,
  filters, setFilters,
  loading,
}) {
  // Start filters open on desktop, closed on mobile
  const [filtersOpen, setFiltersOpen] = useState(() => window.innerWidth > 640);

  useEffect(() => {
    const mq = window.matchMedia("(max-width: 640px)");
    const handler = (e) => {
      // When switching to desktop, ensure filters are open
      if (!e.matches) setFiltersOpen(true);
    };
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, []);

  const addWaypoint = useCallback(() => {
    setWaypoints(prev => [...prev, { id: Date.now(), branches: [{ id: Date.now() + 1, actor: null }] }]);
  }, [setWaypoints]);

  const removeWaypoint = useCallback((wpId) => {
    setWaypoints(prev => prev.filter(wp => wp.id !== wpId));
  }, [setWaypoints]);

  const setWaypointBranch = useCallback((wpId, branchId, actor) => {
    setWaypoints(prev => prev.map(wp =>
      wp.id !== wpId ? wp : {
        ...wp,
        branches: wp.branches.map(b => b.id === branchId ? { ...b, actor } : b),
      }
    ));
  }, [setWaypoints]);

  const addBranch = useCallback((wpId) => {
    setWaypoints(prev => prev.map(wp =>
      wp.id !== wpId ? wp : { ...wp, branches: [...wp.branches, { id: Date.now(), actor: null }] }
    ));
  }, [setWaypoints]);

  const removeBranch = useCallback((wpId, branchId) => {
    setWaypoints(prev => prev.map(wp =>
      wp.id !== wpId ? wp : { ...wp, branches: wp.branches.filter(b => b.id !== branchId) }
    ).filter(wp => wp.branches.length > 0));
  }, [setWaypoints]);

  const updateFilter = (key, val) => setFilters(f => ({ ...f, [key]: val }));

  const filterSummary = [
    filters.moviesOnly ? "Movies" : "Movies & TV",
    filters.minYear > 1920 ? `After ${filters.minYear}` : null,
    filters.minRating > 0 ? `★${filters.minRating}+` : null,
    filters.minVotes > 0 ? `${filters.minVotes >= 1000 ? (filters.minVotes / 1000).toFixed(0) + "k" : filters.minVotes}+ votes` : null,
  ].filter(Boolean).join(" · ");

  return (
    <div
      className="left-panel"
      style={{
        width: 360, minWidth: 360,
        borderRight: "1px solid var(--border2)",
        padding: "24px 28px",
        display: "flex", flexDirection: "column", gap: 28,
        overflowY: "auto",
      }}
    >
      {/* Actor chain */}
      <div>
        <div style={{ fontSize: 10, fontFamily: "'DM Mono', monospace", textTransform: "uppercase", letterSpacing: "0.12em", color: "var(--text-faint)", marginBottom: 14 }}>
          Connect
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {/* Actor A */}
          <ActorInput
            value={actorA?.name || ""}
            onSelect={setActorA}
            onClear={() => setActorA(null)}
            placeholder="Starting actor…"
            label="A"
          />

          {/* Waypoints */}
          {waypoints.map((wp, wi) => (
            <div key={wp.id} style={{ position: "relative" }}>
              <Connector />

              {/* Primary branch */}
              <ActorInput
                value={wp.branches[0].actor?.name || ""}
                onSelect={(a) => setWaypointBranch(wp.id, wp.branches[0].id, a)}
                onClear={() => setWaypointBranch(wp.id, wp.branches[0].id, null)}
                placeholder="Via actor…"
                label={wi + 1}
                showRemove
                onRemove={() => removeWaypoint(wp.id)}
              />

              {/* Extra branches */}
              {wp.branches.slice(1).map((branch) => (
                <div key={branch.id} style={{ marginTop: 6, marginLeft: 36, display: "flex", alignItems: "center", gap: 6 }}>
                  <span style={{ fontSize: 10, fontFamily: "'DM Mono', monospace", color: "var(--accent)", width: 20, textAlign: "center", flexShrink: 0 }}>
                    or
                  </span>
                  <ActorInput
                    value={branch.actor?.name || ""}
                    onSelect={(a) => setWaypointBranch(wp.id, branch.id, a)}
                    onClear={() => setWaypointBranch(wp.id, branch.id, null)}
                    placeholder="Alternative actor…"
                    showRemove
                    onRemove={() => removeBranch(wp.id, branch.id)}
                    inputStyle={{
                      borderStyle: "dashed",
                      color: "var(--accent)",
                      fontSize: 13,
                      padding: "8px 12px",
                    }}
                  />
                </div>
              ))}

              {/* Add branch */}
              <button
                onClick={() => addBranch(wp.id)}
                style={{ marginTop: 4, marginLeft: 36, background: "transparent", border: "none", color: "var(--text-faint)", fontSize: 11, fontFamily: "'DM Mono', monospace", cursor: "pointer", padding: "2px 0", transition: "color 0.15s" }}
                onMouseEnter={(e) => e.currentTarget.style.color = "var(--accent)"}
                onMouseLeave={(e) => e.currentTarget.style.color = "var(--text-faint)"}
              >
                + add alternative
              </button>
            </div>
          ))}

          {/* Actor B */}
          <div style={{ position: "relative" }}>
            {waypoints.length > 0 && <Connector />}
            <ActorInput
              value={actorB?.name || ""}
              onSelect={setActorB}
              onClear={() => setActorB(null)}
              placeholder="Ending actor…"
              label="B"
            />
          </div>
        </div>

        {/* Add waypoint */}
        <button
          onClick={addWaypoint}
          style={{
            width: "100%", marginTop: 10,
            padding: "8px 0", background: "transparent",
            border: "1px dashed var(--border)", borderRadius: 6,
            color: "var(--text-faint)", fontSize: 12,
            fontFamily: "'DM Mono', monospace", cursor: "pointer",
            transition: "all 0.15s",
          }}
          onMouseEnter={(e) => { e.currentTarget.style.borderColor = "var(--accent)"; e.currentTarget.style.color = "var(--accent)"; }}
          onMouseLeave={(e) => { e.currentTarget.style.borderColor = "var(--border)"; e.currentTarget.style.color = "var(--text-faint)"; }}
        >
          + insert waypoint
        </button>
      </div>

      <div style={{ height: 1, background: "var(--border2)" }} />

      {/* Filters — collapsible on mobile */}
      <div>
        {/* Header row: label + mobile toggle */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: filtersOpen ? 14 : 0 }}>
          <div style={{ fontSize: 10, fontFamily: "'DM Mono', monospace", textTransform: "uppercase", letterSpacing: "0.12em", color: "var(--text-faint)" }}>
            Filters
          </div>
          <button
            className="filters-toggle"
            onClick={() => setFiltersOpen(o => !o)}
            style={{
              background: "transparent", border: "1px solid var(--border)",
              borderRadius: 4, color: "var(--text-dim)", fontSize: 10,
              fontFamily: "'DM Mono', monospace", padding: "3px 8px",
              cursor: "pointer", alignItems: "center", gap: 4,
            }}
          >
            {filtersOpen ? "▲ hide" : "▼ " + filterSummary}
          </button>
        </div>

        {filtersOpen && (
          <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
            <Toggle
              label="Movies only (no TV)"
              checked={filters.moviesOnly}
              onChange={(v) => updateFilter("moviesOnly", v)}
            />
            <SliderFilter
              label="Released after"
              value={filters.minYear}
              onChange={(v) => updateFilter("minYear", v)}
              min={1920} max={2025}
              format={(v) => v === 1920 ? "Any year" : String(v)}
            />
            <SliderFilter
              label="Min rating"
              value={filters.minRating}
              onChange={(v) => updateFilter("minRating", v)}
              min={0} max={9} step={0.5}
              format={(v) => v === 0 ? "Any" : `★ ${v.toFixed(1)}+`}
            />
            <SliderFilter
              label="Min vote count"
              value={filters.minVotes}
              onChange={(v) => updateFilter("minVotes", v)}
              min={0} max={500000} step={5000}
              format={(v) => v === 0 ? "Any" : v >= 1000 ? `${(v / 1000).toFixed(0)}k+` : `${v}+`}
            />
          </div>
        )}
      </div>

      {/* Filter summary */}
      {filtersOpen && <div style={{ height: 1, background: "var(--border2)", marginTop: -14 }} />}
      <div style={{ fontSize: 10, fontFamily: "'DM Mono', monospace", color: "var(--text-ghost)", lineHeight: 1.7, marginTop: -14 }}>
        {filterSummary}
        {loading && <span style={{ color: "var(--accent)", marginLeft: 6 }}>· searching…</span>}
      </div>
    </div>
  );
}
