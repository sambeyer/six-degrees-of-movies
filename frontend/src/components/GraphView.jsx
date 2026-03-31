// GraphView: renders all shortest paths as a layered nodes-and-edges graph.
// Desktop: layers flow left → right.
// Mobile (≤640px): layers flow top → bottom.

import { useMemo, useRef, useState, useEffect } from "react";

const PATH_COLORS = [
  "#c8a96e", // gold
  "#7ab4d4", // steel blue
  "#7ad4b4", // teal
  "#d47a96", // rose
  "#b47ad4", // purple
];

const ACTOR_R = 20;
const MOVIE_W = 130;
const MOVIE_H = 28;

// Horizontal layout constants
const H_LAYER_PAD = 48;   // left/right padding
const H_NODE_PAD = 20;    // top/bottom padding per layer column
const H_MIN_SPACING = 68; // min vertical gap between nodes in same column

// Vertical layout constants
const V_LAYER_SPACING = 90; // px between layers top-to-bottom
const V_LAYER_PAD = 50;     // top/bottom padding
const V_MIN_SPACING = 140;  // min horizontal gap between nodes in same row

function buildGraph(allStepSets) {
  const nodeMap = new Map();
  const edgeList = [];
  const edgeSet = new Set();

  allStepSets.forEach((steps, pathIdx) => {
    steps.forEach((step, i) => {
      const actorId = step.nconst;
      const actorLayer = i * 2;
      if (!nodeMap.has(actorId)) {
        nodeMap.set(actorId, {
          id: actorId, type: "actor", label: step.actor,
          layer: actorLayer, isEndpoint: false, paths: new Set(),
        });
      }
      const actorNode = nodeMap.get(actorId);
      actorNode.paths.add(pathIdx);
      if (i === 0 || i === steps.length - 1) actorNode.isEndpoint = true;

      if (i > 0 && step.movie_tconst) {
        const movieId = step.movie_tconst;
        const movieLayer = i * 2 - 1;
        if (!nodeMap.has(movieId)) {
          nodeMap.set(movieId, {
            id: movieId, type: "movie",
            label: step.movie ? step.movie.replace(/\s*\(\d{4}\)$/, "") : "?",
            sublabel: [
              step.movie_year,
              step.movie_type === "movie" ? "🎬" : step.movie_type ? "📺" : null,
              step.movie_rating ? `★${step.movie_rating.toFixed(1)}` : null,
            ].filter(Boolean).join(" "),
            layer: movieLayer, paths: new Set(),
          });
        }
        nodeMap.get(movieId).paths.add(pathIdx);

        const prevActorId = steps[i - 1].nconst;
        const e1Key = `${prevActorId}|${movieId}|${pathIdx}`;
        if (!edgeSet.has(e1Key)) {
          edgeSet.add(e1Key);
          edgeList.push({ source: prevActorId, target: movieId, pathIndex: pathIdx });
        }
        const e2Key = `${movieId}|${actorId}|${pathIdx}`;
        if (!edgeSet.has(e2Key)) {
          edgeSet.add(e2Key);
          edgeList.push({ source: movieId, target: actorId, pathIndex: pathIdx });
        }
      }
    });
  });

  return { nodeMap, edgeList };
}

// ── Horizontal layout (desktop) ──────────────────────────────────────────────
function layoutHorizontal(nodeMap, svgW, svgH) {
  const byLayer = new Map();
  for (const node of nodeMap.values()) {
    if (!byLayer.has(node.layer)) byLayer.set(node.layer, []);
    byLayer.get(node.layer).push(node);
  }
  const numLayers = Math.max(...byLayer.keys()) + 1;
  const positions = new Map();

  for (let l = 0; l < numLayers; l++) {
    const x = numLayers === 1
      ? svgW / 2
      : H_LAYER_PAD + (l * (svgW - 2 * H_LAYER_PAD)) / (numLayers - 1);
    const nodes = byLayer.get(l) || [];
    const count = nodes.length;
    const totalH = Math.max(count * H_MIN_SPACING, svgH - 2 * H_NODE_PAD);
    const spacing = count <= 1 ? 0 : totalH / (count - 1);
    const startY = count === 1 ? svgH / 2 : (svgH - totalH) / 2 + H_NODE_PAD;
    nodes.forEach((node, i) => {
      positions.set(node.id, { x, y: count === 1 ? startY : startY + i * spacing });
    });
  }
  return positions;
}

// ── Vertical layout (mobile) ─────────────────────────────────────────────────
function layoutVertical(nodeMap, svgW, svgH) {
  const byLayer = new Map();
  for (const node of nodeMap.values()) {
    if (!byLayer.has(node.layer)) byLayer.set(node.layer, []);
    byLayer.get(node.layer).push(node);
  }
  const numLayers = Math.max(...byLayer.keys()) + 1;
  const positions = new Map();

  for (let l = 0; l < numLayers; l++) {
    const y = numLayers === 1
      ? svgH / 2
      : V_LAYER_PAD + (l * (svgH - 2 * V_LAYER_PAD)) / (numLayers - 1);
    const nodes = byLayer.get(l) || [];
    const count = nodes.length;
    const totalW = svgW - 2 * H_LAYER_PAD;
    const spacing = count <= 1 ? 0 : totalW / (count - 1);
    const startX = count === 1 ? svgW / 2 : H_LAYER_PAD;
    nodes.forEach((node, i) => {
      positions.set(node.id, { x: count === 1 ? startX : startX + i * spacing, y });
    });
  }
  return positions;
}

function ActorNode({ node, pos, resultVersion, isShared, vertical }) {
  const color = node.isEndpoint ? "var(--accent)" : isShared ? "var(--text-muted)" : "var(--text-dim)";
  const glow = node.isEndpoint ? "0 0 14px rgba(200,169,110,0.5)" : "none";
  // On vertical layout, label goes below; on horizontal, same (already below circle)
  return (
    <g transform={`translate(${pos.x},${pos.y})`}>
      <circle
        r={ACTOR_R}
        fill={node.isEndpoint ? "rgba(200,169,110,0.18)" : "rgba(255,255,255,0.06)"}
        stroke={color}
        strokeWidth={node.isEndpoint ? 2 : 1.5}
        style={{ filter: node.isEndpoint ? `drop-shadow(${glow})` : "none" }}
      />
      <text
        className="actor-node"
        key={`${node.id}-${resultVersion}`}
        textAnchor="middle"
        y={ACTOR_R + 13}
        style={{
          fontSize: 9,
          fontFamily: "'Newsreader', serif",
          fill: node.isEndpoint ? "var(--text)" : "var(--text-dim)",
          fontWeight: node.isEndpoint ? 600 : 400,
          pointerEvents: "none",
          animationDelay: "0ms",
        }}
      >
        {node.label.length > 18 ? node.label.slice(0, 17) + "…" : node.label}
      </text>
    </g>
  );
}

function MovieNode({ node, pos }) {
  const hw = MOVIE_W / 2;
  const hh = MOVIE_H / 2;
  const titleMax = 18;
  const title = node.label.length > titleMax ? node.label.slice(0, titleMax - 1) + "…" : node.label;
  return (
    <g transform={`translate(${pos.x},${pos.y})`}>
      <rect
        x={-hw} y={-hh} width={MOVIE_W} height={MOVIE_H} rx={5}
        fill="var(--surface2)" stroke="var(--border)" strokeWidth={1}
      />
      <text
        textAnchor="middle"
        dy={node.sublabel ? "-0.3em" : "0.35em"}
        style={{ fontSize: 10, fontFamily: "'DM Mono', monospace", fill: "var(--text-dim)", pointerEvents: "none" }}
      >
        {title}
      </text>
      {node.sublabel && (
        <text
          textAnchor="middle" dy="0.9em"
          style={{ fontSize: 10, fontFamily: "'DM Mono', monospace", fill: "var(--text-dim)", pointerEvents: "none" }}
        >
          {node.sublabel}
        </text>
      )}
    </g>
  );
}

function Edge({ sourcePos, targetPos, color, vertical }) {
  // Bezier curves: horizontal layout curves along x-axis,
  // vertical layout curves along y-axis.
  const path = vertical
    ? `M ${sourcePos.x} ${sourcePos.y} C ${sourcePos.x} ${(sourcePos.y + targetPos.y) / 2} ${targetPos.x} ${(sourcePos.y + targetPos.y) / 2} ${targetPos.x} ${targetPos.y}`
    : `M ${sourcePos.x} ${sourcePos.y} C ${(sourcePos.x + targetPos.x) / 2} ${sourcePos.y} ${(sourcePos.x + targetPos.x) / 2} ${targetPos.y} ${targetPos.x} ${targetPos.y}`;
  return (
    <path d={path} fill="none" stroke={color} strokeWidth={1.5} strokeOpacity={0.45} />
  );
}

export default function GraphView({ paths, resultVersion }) {
  const containerRef = useRef(null);
  const [containerW, setContainerW] = useState(700);

  useEffect(() => {
    if (!containerRef.current) return;
    const obs = new ResizeObserver(([entry]) => {
      setContainerW(entry.contentRect.width || 700);
    });
    obs.observe(containerRef.current);
    return () => obs.disconnect();
  }, []);

  const vertical = containerW <= 640;

  const { nodeMap, edgeList, svgW, svgH } = useMemo(() => {
    if (!paths || paths.length === 0) return { nodeMap: new Map(), edgeList: [], svgW: 300, svgH: 200 };

    const allStepSets = [];
    paths.forEach((path) => {
      if (path.legs.length === 1) {
        const leg = path.legs[0];
        const alts = leg.all_steps && leg.all_steps.length > 0 ? leg.all_steps : [leg.steps];
        alts.forEach((steps) => allStepSets.push(steps));
      } else {
        const fullSteps = [];
        path.legs.forEach((leg, li) => {
          const steps = leg.steps;
          fullSteps.push(...(li === 0 ? steps : steps.slice(1)));
        });
        allStepSets.push(fullSteps);
      }
    });

    const { nodeMap, edgeList } = buildGraph(allStepSets);

    const byLayer = new Map();
    for (const node of nodeMap.values()) {
      byLayer.set(node.layer, (byLayer.get(node.layer) || 0) + 1);
    }
    const numLayers = Math.max(...byLayer.keys()) + 1;
    const maxPerLayer = Math.max(1, ...byLayer.values());

    let svgW, svgH;
    if (vertical) {
      // In vertical mode, width is exactly the container width — never exceed it.
      // Height is driven by the number of layers.
      svgW = containerW;
      svgH = V_LAYER_PAD * 2 + (numLayers - 1) * V_LAYER_SPACING;
    } else {
      // Horizontal mode: width is container width, height driven by nodes per layer.
      svgW = containerW;
      svgH = Math.max(220, maxPerLayer * H_MIN_SPACING + H_NODE_PAD * 2 + 40);
    }

    return { nodeMap, edgeList, svgW, svgH };
  }, [paths, vertical, containerW]);

  const positions = useMemo(() => {
    if (nodeMap.size === 0) return new Map();
    return vertical
      ? layoutVertical(nodeMap, svgW, svgH)
      : layoutHorizontal(nodeMap, svgW, svgH);
  }, [nodeMap, svgW, svgH, vertical]);

  if (nodeMap.size === 0) return null;

  return (
    <div
      ref={containerRef}
      style={{ marginTop: 28, paddingTop: 24, borderTop: "1px solid var(--border2)" }}
    >
      <div style={{
        fontSize: 10, fontFamily: "'DM Mono', monospace",
        textTransform: "uppercase", letterSpacing: "0.12em",
        color: "var(--text-dim)", marginBottom: 12,
      }}>
        Connection graph
      </div>
      <svg
        aria-hidden="true"
        viewBox={`0 0 ${svgW} ${svgH}`}
        width={svgW}
        height={svgH}
        style={{ display: "block", overflow: "visible" }}
      >
        <g>
          {edgeList.map((edge, i) => {
            const sp = positions.get(edge.source);
            const tp = positions.get(edge.target);
            if (!sp || !tp) return null;
            return (
              <Edge key={i} sourcePos={sp} targetPos={tp}
                color={PATH_COLORS[edge.pathIndex % PATH_COLORS.length]}
                vertical={vertical}
              />
            );
          })}
        </g>
        <g>
          {[...nodeMap.values()].map((node) => {
            const pos = positions.get(node.id);
            if (!pos) return null;
            const isShared = node.paths.size > 1;
            if (node.type === "actor") {
              return (
                <ActorNode key={node.id} node={node} pos={pos}
                  resultVersion={resultVersion} isShared={isShared}
                  vertical={vertical}
                />
              );
            }
            return <MovieNode key={node.id} node={node} pos={pos} />;
          })}
        </g>
      </svg>
    </div>
  );
}
