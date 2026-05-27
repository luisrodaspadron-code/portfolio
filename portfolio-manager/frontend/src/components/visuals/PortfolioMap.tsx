import type { CSSProperties } from "react";
import { stratify, treemap, treemapBinary } from "d3";
import { motion } from "motion/react";
import type { AdvisorPacket, Portfolio } from "../../types";
import { money, pct } from "../../lib/format";

type Props = {
  portfolio: Portfolio;
  advisorPacket?: AdvisorPacket | null;
  onSelect?: (symbol: string) => void;
};

type Tile = {
  id: string;
  symbol: string;
  name: string;
  value: number;
  weight: number;
  sector: string;
  /** action / risk-derived tone */
  tone: "trim" | "watch" | "hold" | "wait" | "blocked" | "neutral";
  /** data quality (border) */
  data: "live" | "recent" | "partial" | "stale" | "missing";
  reason: string;
};

function deriveTone(action?: string): Tile["tone"] {
  switch ((action ?? "").toUpperCase()) {
    case "TRIM":
      return "trim";
    case "BLOCKED_BY_RISK":
      return "blocked";
    case "WAIT_FOR_DATA":
      return "wait";
    case "REVIEW_MANUALLY":
      return "watch";
    case "ADD":
    case "STAGGER_ENTRY":
      return "hold";
    case "HOLD":
      return "hold";
    default:
      return "neutral";
  }
}

function deriveData(freshness?: string): Tile["data"] {
  const key = (freshness ?? "missing").toLowerCase();
  if (key === "live" || key === "recent") return key as Tile["data"];
  if (key === "stale") return "stale";
  if (key === "partial" || key === "sample") return "partial";
  return "missing";
}

function buildTiles(portfolio: Portfolio, packet?: AdvisorPacket | null): Tile[] {
  const byAction = new Map<string, { action: string; reason: string; freshness: string }>();
  packet?.positions?.forEach((pos) => {
    byAction.set(pos.symbol, {
      action: pos.action,
      reason: pos.explanation,
      freshness: pos.dataQuality?.freshness ?? "missing",
    });
  });
  return portfolio.positions
    .map((pos) => {
      const decision = byAction.get(pos.symbol);
      return {
        id: pos.symbol,
        symbol: pos.symbol,
        name: pos.name || pos.symbol,
        value: Math.max(0.0001, pos.market_value),
        weight: pos.weight,
        sector: pos.sector || "Other",
        tone: deriveTone(decision?.action),
        data: deriveData(decision?.freshness ?? pos.valuation_status),
        reason: decision?.reason ?? pos.valuation_note ?? "",
      } as Tile;
    })
    .sort((a, b) => b.value - a.value);
}

/**
 * Portfolio heatmap: tile size = market value, color = action / risk state,
 * border = data quality. Click a tile to open its detail in the parent screen.
 *
 * Pure visualization — does not recompute weights or risk. All inputs come
 * from the deterministic backend.
 */
export function PortfolioMap({ portfolio, advisorPacket, onSelect }: Props) {
  const tiles = buildTiles(portfolio, advisorPacket);
  const width = 720;
  const height = 360;

  if (!tiles.length) {
    return (
      <div className="portfolio-map empty">
        <p>No holdings yet — import a portfolio to render the heatmap.</p>
      </div>
    );
  }

  const root = stratify<Tile | { id: string }>()
    .id((d) => d.id)
    .parentId((d) => (d.id === "root" ? null : "root"))(
      [{ id: "root" } as { id: string }, ...tiles]
    )
    .sum((d) => ("value" in d ? (d as Tile).value : 0))
    .sort((a, b) => (b.value ?? 0) - (a.value ?? 0));

  const layout = treemap<Tile | { id: string }>()
    .tile(treemapBinary)
    .size([width, height])
    .paddingInner(4)
    .round(true)(root);

  return (
    <div className="portfolio-map" data-testid="portfolio-map" role="figure" aria-label="Portfolio heatmap">
      <header className="portfolio-map-head">
        <strong>Portfolio map</strong>
        <span>Size = market value · Color = action · Border = data quality</span>
      </header>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" preserveAspectRatio="none">
        {layout.leaves().map((leaf, idx) => {
          const tile = leaf.data as Tile;
          if (!tile || !("value" in tile)) return null;
          const w = leaf.x1 - leaf.x0;
          const h = leaf.y1 - leaf.y0;
          const showLabel = w > 56 && h > 32;
          const showMeta = w > 88 && h > 60;
          const groupStyle: CSSProperties = { cursor: onSelect ? "pointer" : "default" };
          return (
            <motion.g
              key={tile.id}
              transform={`translate(${leaf.x0},${leaf.y0})`}
              initial={{ opacity: 0, scale: 0.92 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ delay: idx * 0.02, duration: 0.24 }}
              style={groupStyle}
              tabIndex={onSelect ? 0 : -1}
              onClick={onSelect ? () => onSelect(tile.symbol) : undefined}
              onKeyDown={
                onSelect
                  ? (event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        onSelect(tile.symbol);
                      }
                    }
                  : undefined
              }
            >
              <rect
                width={w}
                height={h}
                rx={6}
                className={`portfolio-map-tile tone-${tile.tone} data-${tile.data}`}
              >
                <title>{`${tile.symbol} · ${pct(tile.weight)} · ${money(tile.value)}\n${tile.reason}`}</title>
              </rect>
              {showLabel && (
                <text x={10} y={20} className="portfolio-map-label">
                  {tile.symbol}
                </text>
              )}
              {showMeta && (
                <>
                  <text x={10} y={h - 22} className="portfolio-map-weight">
                    {pct(tile.weight)}
                  </text>
                  <text x={10} y={h - 8} className="portfolio-map-value">
                    {money(tile.value)}
                  </text>
                </>
              )}
            </motion.g>
          );
        })}
      </svg>
      <footer className="portfolio-map-legend">
        <span><i className="tone-trim" />Trim</span>
        <span><i className="tone-watch" />Review</span>
        <span><i className="tone-hold" />Hold / add</span>
        <span><i className="tone-wait" />Wait for data</span>
        <span><i className="tone-blocked" />Risk blocked</span>
        <span className="border-legend"><i className="data-partial" />Partial border = data gap</span>
      </footer>
    </div>
  );
}
