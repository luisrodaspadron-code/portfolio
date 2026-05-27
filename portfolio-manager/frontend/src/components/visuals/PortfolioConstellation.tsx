import * as Tooltip from "@radix-ui/react-tooltip";
import { scaleLinear } from "d3";
import { motion } from "motion/react";
import { CommandButton } from "../ui/Primitives";
import type { ConstellationNode } from "../../lib/viewModels";

export function PortfolioConstellation({
  nodes,
  onImport
}: {
  nodes: ConstellationNode[];
  onImport: () => void;
}) {
  const width = 720;
  const height = 420;
  const xScale = scaleLinear()
    .domain([0, Math.max(0.8, ...nodes.map((node) => node.risk))])
    .range([78, width - 70]);
  const yScale = scaleLinear()
    .domain([
      Math.min(-0.18, ...nodes.map((node) => node.returnSignal)),
      Math.max(0.26, ...nodes.map((node) => node.returnSignal))
    ])
    .range([height - 64, 70]);
  const maxWeight = Math.max(0.08, ...nodes.map((node) => node.weight));
  const radius = scaleLinear().domain([0, maxWeight]).range([7, 26]);

  if (!nodes.length) {
    return (
      <div className="constellation-empty">
        <div className="orbital-ring" />
        <strong>No portfolio signal yet</strong>
        <p>Import holdings and connect data to turn this into a live risk/opportunity map.</p>
        <CommandButton variant="primary" onClick={onImport}>
          Import holdings
        </CommandButton>
      </div>
    );
  }

  return (
    <Tooltip.Provider delayDuration={100}>
      <div className="constellation-wrap" data-testid="portfolio-constellation">
        <div className="constellation-legend" aria-hidden="true">
          <span><i className="legend-dot good" />Fit</span>
          <span><i className="legend-dot watch" />Watch</span>
          <span><i className="legend-dot danger" />Reduce</span>
          <span>Size = portfolio weight</span>
        </div>
        <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Portfolio constellation">
          <defs>
            <radialGradient id="nodeGlow">
              <stop offset="0%" stopColor="rgba(99,255,214,0.92)" />
              <stop offset="100%" stopColor="rgba(99,255,214,0)" />
            </radialGradient>
          </defs>
          <g className="constellation-grid">
            {[0, 1, 2, 3, 4].map((line) => (
              <line key={`h-${line}`} x1="48" x2={width - 42} y1={70 + line * 70} y2={70 + line * 70} />
            ))}
            {[0, 1, 2, 3, 4].map((line) => (
              <line key={`v-${line}`} y1="48" y2={height - 44} x1={82 + line * 132} x2={82 + line * 132} />
            ))}
          </g>
          <text className="axis-label" x="48" y="40">
            lower risk
          </text>
          <text className="axis-label" x={width - 150} y={height - 20}>
            higher risk
          </text>
          <text className="axis-label" x="48" y={height - 20}>
            lower signal
          </text>
          <text className="axis-label" x={width - 150} y="40">
            higher signal
          </text>
          {nodes.map((node, index) => {
            const x = xScale(node.risk);
            const y = yScale(node.returnSignal);
            const r = radius(node.weight);
            return (
              <Tooltip.Root key={node.id}>
                <Tooltip.Trigger asChild>
                  <motion.g
                    className={`constellation-node ${node.tone}`}
                    tabIndex={0}
                    initial={{ opacity: 0, scale: 0.75 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ delay: index * 0.025, duration: 0.3 }}
                    style={{ transformOrigin: `${x}px ${y}px` }}
                  >
                    <circle className="node-halo" cx={x} cy={y} r={r * 2.2} />
                    <circle cx={x} cy={y} r={r} />
                    <text x={x} y={y + 4}>
                      {node.label.slice(0, 4)}
                    </text>
                  </motion.g>
                </Tooltip.Trigger>
                <Tooltip.Portal>
                  <Tooltip.Content className="signal-tooltip" sideOffset={10}>
                    <strong>{node.label}</strong>
                    <span>{node.name}</span>
                    <span>{node.detail}</span>
                    <Tooltip.Arrow className="signal-tooltip-arrow" />
                  </Tooltip.Content>
                </Tooltip.Portal>
              </Tooltip.Root>
            );
          })}
        </svg>
      </div>
    </Tooltip.Provider>
  );
}
