// GraphView: renders all shortest paths as a layered nodes-and-edges graph.
// Actor nodes are circles, movie nodes are rounded rectangles.
// Up to 5 paths are shown simultaneously; shared nodes appear once with
// multiple coloured edges converging on them.

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
const LAYER_PAD_X = 48;
const NODE_PAD_Y = 20;
const MIN_NODE_SPACING = 68;

function buildGraph(allStepSets) {
  // allStepSets: array of paths, each path = array of step objects
  // Each step: {actor, nconst, movie, movie_year, movie_type, movie_rating, movie_tconst}
  // movie info on step[i] is the film connecting step[i-1] → step[i]

  const nodeMap = new Map(); // id -> node object
  const edgeList = []; // {source, target, pathIndex}
  const edgeSet = new Set(); // deduplicate

  allStepSets.forEach((steps, pathIdx) => {
    steps.forEach((step, i) => {
      // Actor node at layer i*2
      const actorId = step.nconst;
      const actorLayer = i * 2;
      if (!nodeMap.has(actorId)) {
        nodeMap.set(actorId, {
          id: actorId,
          type: "actor",
          label: step.actor,
          layer: actorLayer,
          isEndpoint: false,
          paths: new Set(),
        });
      }
      const actorNode = nodeMap.get(actorId);
      actorNode.paths.add(pathIdx);
      if (i === 0 || i === steps.length - 1) actorNode.isEndpoint = true;

      // Movie node and edges: movie lives at layer i*2-1
      if (i > 0 && step.movie_tconst) {
        const movieId = step.movie_tconst;
        const movieLayer = i * 2 - 1;
        if (!nodeMap.has(movieId)) {
          nodeMap.set(movieId, {
            id: movieId,
            type: "movie",
            label: step.movie ? step.movie.replace(/\s*\(\d{4}\)$/, "") : "?",
            sublabel: [
              step.movie_year,
              step.movie_type === "movie" ? "🎬" : step.movie_type ? "📺" : null,
              step.movie_rating ? `★${step.movie_rating.toFixed(1)}` : null,
            ].filter(Boolean).join(" "),
            layer: movieLayer,
            paths: new Set(),
          });
        }
        nodeMap.get(movieId).paths.add(pathIdx);

        // prev actor → movie edge
        const prevActorId = steps[i - 1].nconst;
        const e1Key = `${prevActorId}|${movieId}|${pathIdx}`;
        if (!edgeSet.has(e1Key)) {
          edgeSet.add(e1Key);
          edgeList.push({ source: prevActorId, target: movieId, pathIndex: pathIdx });
        }
        // movie → this actor edge
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

function layoutGraph(nodeMap, svgW, svgH) {
  // Group nodes by layer
  const byLayer = new Map();
  for (const node of nodeMap.values()) {
    if (!byLayer.has(node.layer)) byLayer.set(node.layer, []);
    byLayer.get(node.layer).push(node);
  }

  const numLayers = Math.max(...byLayer.keys()) + 1;
  const positions = new Map(); // id -> {x, y}

  // x positions for each layer
  const layerXs = [];
  for (let l = 0; l < numLayers; l++) {
    layerXs.push(
      numLayers === 1
        ? svgW / 2
        : LAYER_PAD_X + (l * (svgW - 2 * LAYER_PAD_X)) / (numLayers - 1)
    );
  }

  for (const [layerIdx, nodes] of byLayer.entries()) {
    const x = layerXs[layerIdx];
    const count = nodes.length;
    const totalH = Math.max(count * MIN_NODE_SPACING, svgH - 2 * NODE_PAD_Y);
    const spacing = count === 1 ? 0 : totalH / (count - 1);
    const startY = count === 1 ? svgH / 2 : (svgH - totalH) / 2 + NODE_PAD_Y;

    nodes.forEach((node, i) => {
      positions.set(node.id, {
        x,
        y: count === 1 ? startY : startY + i * spacing,
      });
    });
  }

  return { positions, layerXs, numLayers };
}

function ActorNode({ node, pos, resultVersion, isShared }) {
  const color = node.isEndpoint ? "var(--accent)" : isShared ? "#c8c8a9" : "var(--text-muted)";
  const glow = node.isEndpoint ? "0 0 14px rgba(200,169,110,0.5)" : "none";
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
        x={-hw} y={-hh}
        width={MOVIE_W} height={MOVIE_H}
        rx={5}
        fill="var(--surface2)"
        stroke="var(--border)"
        strokeWidth={1}
      />
      <text
        textAnchor="middle"
        dy={node.sublabel ? "-0.3em" : "0.35em"}
        style={{
          fontSize: 10,
          fontFamily: "'DM Mono', monospace",
          fill: "var(--text-dim)",
          pointerEvents: "none",
        }}
      >
        {title}
      </text>
      {node.sublabel && (
        <text
          textAnchor="middle"
          dy="0.9em"
          style={{
            fontSize: 8,
            fontFamily: "'DM Mono', monospace",
            fill: "var(--text-faint)",
            pointerEvents: "none",
          }}
        >
          {node.sublabel}
        </text>
      )}
    </g>
  );
}

function Edge({ sourcePos, targetPos, color }) {
  const mx = (sourcePos.x + targetPos.x) / 2;
  return (
    <path
      d={`M ${sourcePos.x} ${sourcePos.y} C ${mx} ${sourcePos.y} ${mx} ${targetPos.y} ${targetPos.x} ${targetPos.y}`}
      fill="none"
      stroke={color}
      strokeWidth={1.5}
      strokeOpacity={0.45}
    />
  );
}

export default function GraphView({ paths, resultVersion }) {
  const containerRef = useRef(null);
  const [svgW, setSvgW] = useState(700);

  useEffect(() => {
    if (!containerRef.current) return;
    const obs = new ResizeObserver(([entry]) => {
      setSvgW(entry.contentRect.width || 700);
    });
    obs.observe(containerRef.current);
    return () => obs.disconnect();
  }, []);

  const { nodeMap, edgeList, svgH } = useMemo(() => {
    if (!paths || paths.length === 0) return { nodeMap: new Map(), edgeList: [], svgH: 200 };

    // Build complete end-to-end step-sets suitable for layer assignment.
    //
    // For single-leg results: show all alternative paths from all_steps.
    // For multi-leg results (waypoints): concatenate each leg's primary steps
    //   into one full path. Multiple PathResults (branch combos) each get their
    //   own full-path entry so they appear as distinct coloured lines.
    const allStepSets = [];

    paths.forEach((path) => {
      if (path.legs.length === 1) {
        // Single leg — show all alternative paths
        const leg = path.legs[0];
        const alts = leg.all_steps && leg.all_steps.length > 0 ? leg.all_steps : [leg.steps];
        alts.forEach((steps) => allStepSets.push(steps));
      } else {
        // Multi-leg — build one complete path by concatenating primary leg steps
        const fullSteps = [];
        path.legs.forEach((leg, li) => {
          const steps = leg.steps;
          if (li === 0) {
            fullSteps.push(...steps);
          } else {
            fullSteps.push(...steps.slice(1)); // skip repeated junction actor
          }
        });
        allStepSets.push(fullSteps);
      }
    });

    const { nodeMap, edgeList } = buildGraph(allStepSets);

    // Compute SVG height from max nodes per layer
    const byLayer = new Map();
    for (const node of nodeMap.values()) {
      byLayer.set(node.layer, (byLayer.get(node.layer) || 0) + 1);
    }
    const maxPerLayer = Math.max(1, ...byLayer.values());
    const svgH = Math.max(220, maxPerLayer * MIN_NODE_SPACING + NODE_PAD_Y * 2 + 40);

    return { nodeMap, edgeList, svgH };
  }, [paths]);

  const { positions } = useMemo(
    () => layoutGraph(nodeMap, svgW, svgH),
    [nodeMap, svgW, svgH]
  );

  if (nodeMap.size === 0) return null;

  return (
    <div
      ref={containerRef}
      style={{
        marginTop: 28,
        paddingTop: 24,
        borderTop: "1px solid var(--border2)",
      }}
    >
      <div style={{
        fontSize: 10, fontFamily: "'DM Mono', monospace",
        textTransform: "uppercase", letterSpacing: "0.12em",
        color: "var(--text-faint)", marginBottom: 12,
      }}>
        Connection graph
      </div>
      <svg
        viewBox={`0 0 ${svgW} ${svgH}`}
        width={svgW}
        height={svgH}
        style={{ display: "block", overflow: "visible" }}
      >
        {/* Edges — drawn behind nodes */}
        <g>
          {edgeList.map((edge, i) => {
            const sp = positions.get(edge.source);
            const tp = positions.get(edge.target);
            if (!sp || !tp) return null;
            return (
              <Edge
                key={i}
                sourcePos={sp}
                targetPos={tp}
                color={PATH_COLORS[edge.pathIndex % PATH_COLORS.length]}
              />
            );
          })}
        </g>

        {/* Nodes */}
        <g>
          {[...nodeMap.values()].map((node) => {
            const pos = positions.get(node.id);
            if (!pos) return null;
            const isShared = node.paths.size > 1;
            if (node.type === "actor") {
              return (
                <ActorNode
                  key={node.id}
                  node={node}
                  pos={pos}
                  resultVersion={resultVersion}
                  isShared={isShared}
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
