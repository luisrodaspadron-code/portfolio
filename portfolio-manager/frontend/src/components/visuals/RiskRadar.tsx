import { lineRadial, scaleLinear } from "d3";
import { motion } from "motion/react";
import type { RadarMetric } from "../../lib/viewModels";

export function RiskRadar({ metrics }: { metrics: RadarMetric[] }) {
  const size = 360;
  const center = size / 2;
  const radius = 128;
  const scale = scaleLinear().domain([0, 1]).range([0, radius]);
  const angleStep = (Math.PI * 2) / Math.max(metrics.length, 1);
  const radialLine = lineRadial<RadarMetric>()
    .angle((_, index) => index * angleStep)
    .radius((metric) => scale(metric.value));
  const path = radialLine(metrics) ?? "";
  const rings = [0.25, 0.5, 0.75, 1];

  return (
    <div className="risk-radar-wrap" data-testid="risk-radar">
      <svg viewBox={`0 0 ${size} ${size}`} role="img" aria-label="Risk radar">
        <g transform={`translate(${center},${center})`}>
          {rings.map((ring) => (
            <circle key={ring} r={scale(ring)} className="radar-ring" />
          ))}
          {metrics.map((metric, index) => {
            const angle = index * angleStep - Math.PI / 2;
            const x = Math.cos(angle) * radius;
            const y = Math.sin(angle) * radius;
            const labelX = Math.cos(angle) * (radius + 34);
            const labelY = Math.sin(angle) * (radius + 34);
            return (
              <g key={metric.label}>
                <line className="radar-axis" x1="0" y1="0" x2={x} y2={y} />
                <text className={`radar-label ${metric.tone}`} x={labelX} y={labelY} textAnchor="middle">
                  {metric.label}
                </text>
              </g>
            );
          })}
          <motion.path
            className="radar-area"
            d={path}
            initial={{ opacity: 0, scale: 0.88 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.42 }}
          />
          {metrics.map((metric, index) => {
            const angle = index * angleStep - Math.PI / 2;
            const pointRadius = scale(metric.value);
            const x = Math.cos(angle) * pointRadius;
            const y = Math.sin(angle) * pointRadius;
            return <circle key={`${metric.label}-point`} className={`radar-point ${metric.tone}`} cx={x} cy={y} r="5" />;
          })}
        </g>
      </svg>
      <div className="radar-legend">
        {metrics.map((metric) => (
          <div key={metric.label}>
            <span>{metric.label}</span>
            <strong>{Math.round(metric.value * 100)}</strong>
            <small>{metric.detail}</small>
          </div>
        ))}
      </div>
    </div>
  );
}
