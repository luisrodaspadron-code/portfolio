import type { PortfolioTrend } from "../../types";
import { money } from "../../lib/format";

export function PortfolioTrendChart({ trend }: { trend: PortfolioTrend }) {
  const points = trend.points.slice(-60);
  if (points.length < 2) {
    return (
      <div className="trend-empty">
        <strong>No trend yet</strong>
        <span>{trend.source_note}</span>
      </div>
    );
  }
  const width = 640;
  const height = 180;
  const values = points.map((point) => point.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const spread = max - min || 1;
  const line = points
    .map((point, index) => {
      const x = (index / (points.length - 1)) * width;
      const y = height - ((point.value - min) / spread) * height;
      return `${index === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(" ");
  const area = `${line} L ${width} ${height} L 0 ${height} Z`;
  const positive = trend.day_change >= 0;
  return (
    <div className="trend-chart" data-testid="portfolio-trend-chart">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Portfolio value trend">
        <defs>
          <linearGradient id="trend-fill" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor={positive ? "rgba(101,255,216,0.28)" : "rgba(255,107,124,0.26)"} />
            <stop offset="100%" stopColor="rgba(101,255,216,0)" />
          </linearGradient>
        </defs>
        <path d={area} fill="url(#trend-fill)" />
        <path d={line} fill="none" stroke={positive ? "rgb(101,255,216)" : "rgb(255,107,124)"} strokeWidth="3" strokeLinecap="round" />
      </svg>
      <div className="trend-axis">
        <span>{points[0].date}</span>
        <strong>{money(points[points.length - 1].value)}</strong>
        <span>{points[points.length - 1].date}</span>
      </div>
    </div>
  );
}
