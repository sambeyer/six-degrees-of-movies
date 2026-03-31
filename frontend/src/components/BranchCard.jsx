// BranchCard: renders a single path result as a vertical chain of nodes.
// Each actor node gets a unique key based on resultVersion so React remounts
// it on every new result, replaying the wobble CSS animation.

export default function BranchCard({ path, resultVersion, label }) {
  if (!path || !path.legs || path.legs.length === 0) return null;

  // Flatten legs into a single step list, merging junction actors
  const steps = [];
  path.legs.forEach((leg, li) => {
    leg.steps.forEach((step, si) => {
      if (li > 0 && si === 0) return; // skip repeated junction actor
      steps.push(step);
    });
  });

  const totalDegrees = path.total_degrees;

  return (
    <div style={{
      background: "var(--surface)",
      border: "1px solid var(--border)",
      borderRadius: 10,
      padding: "20px 20px 16px",
      flex: 1,
      minWidth: 260,
    }}>
      {label && (
        <div style={{
          fontSize: 10, fontFamily: "'DM Mono', monospace",
          textTransform: "uppercase", letterSpacing: "0.12em",
          color: "var(--accent)", marginBottom: 16,
        }}>
          {label}
        </div>
      )}

      <ol style={{ display: "flex", flexDirection: "column", listStyle: "none", padding: 0, margin: 0 }}>
        {steps.map((step, i) => {
          const isEndpoint = i === 0 || i === steps.length - 1;
          // The film connecting THIS actor to the NEXT one
          const nextStep = i < steps.length - 1 ? steps[i + 1] : null;
          const movieMeta = nextStep && [
            nextStep.movie_year,
            nextStep.movie_type === "movie" ? "film" : nextStep.movie_type === "tvSeries" ? "TV series" : nextStep.movie_type || null,
            nextStep.movie_rating ? `rated ${nextStep.movie_rating.toFixed(1)}` : null,
          ].filter(Boolean).join(", ");

          return (
            <li key={i}>
              {/* Actor node */}
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <div
                  aria-hidden="true"
                  style={{
                    width: 10, height: 10, borderRadius: "50%", flexShrink: 0,
                    backgroundColor: isEndpoint ? "var(--accent)" : "var(--text-faint)",
                    boxShadow: isEndpoint ? "0 0 10px rgba(200,169,110,0.35)" : "none",
                  }}
                />
                <span
                  className="actor-node"
                  key={`${step.nconst}-${resultVersion}`}
                  style={{
                    fontSize: 15,
                    fontFamily: "'Newsreader', serif",
                    color: "var(--text)",
                    fontWeight: isEndpoint ? 600 : 400,
                    animationDelay: `${i * 70}ms`,
                  }}
                >
                  {step.actor}
                </span>
              </div>

              {/* Connector + movie pill — shown below THIS actor, connecting to the NEXT */}
              {nextStep?.movie && (
                <div style={{ display: "flex", alignItems: "stretch", gap: 12, minHeight: 44 }}>
                  <div aria-hidden="true" style={{ width: 10, display: "flex", justifyContent: "center", flexShrink: 0 }}>
                    <div style={{ width: 1, background: "var(--border)", height: "100%" }} />
                  </div>
                  <div style={{ padding: "6px 0", display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                    <span style={{
                      fontSize: 12, fontFamily: "'DM Mono', monospace",
                      color: "var(--text-dim)", background: "var(--surface2)",
                      padding: "3px 8px", borderRadius: 4,
                    }}>
                      {nextStep.movie}
                    </span>
                    {movieMeta && (
                      <span
                        aria-label={movieMeta}
                        style={{ fontSize: 10, fontFamily: "'DM Mono', monospace", color: "var(--text-dim)" }}
                      >
                        {[
                          nextStep.movie_year,
                          nextStep.movie_type === "movie" ? "🎬" : nextStep.movie_type === "tvSeries" ? "📺" : nextStep.movie_type ? "📺" : null,
                          nextStep.movie_rating ? `★ ${nextStep.movie_rating.toFixed(1)}` : null,
                        ].filter(Boolean).join(" · ")}
                      </span>
                    )}
                  </div>
                </div>
              )}
            </li>
          );
        })}
      </ol>

      <div style={{
        marginTop: 14, paddingTop: 12,
        borderTop: "1px solid var(--border)",
        display: "flex", justifyContent: "space-between", alignItems: "center",
      }}>
        <span style={{ fontSize: 10, fontFamily: "'DM Mono', monospace", color: "var(--text-dim)", textTransform: "uppercase", letterSpacing: "0.1em" }}>
          {totalDegrees} degree{totalDegrees !== 1 ? "s" : ""}
        </span>
        {path.legs.length > 1 && (
          <span style={{ fontSize: 10, fontFamily: "'DM Mono', monospace", color: "var(--text-dim)" }}>
            {path.legs.length} legs
          </span>
        )}
      </div>
    </div>
  );
}
