import type { CSSProperties } from "react";

export type ScoreComponent = {
  label: string;
  value: number;
  /** Optional 0..1 weight for the component. Used only for sorting. */
  weight?: number;
  /** Optional plain-language detail rendered as a tooltip / aria-label. */
  detail?: string;
  /** Force a tone (defaults to derived from value). */
  tone?: "good" | "watch" | "fail" | "neutral";
};

type Props = {
  total?: number;
  components: ScoreComponent[];
  compact?: boolean;
};

function toneFor(value: number): "good" | "watch" | "fail" | "neutral" {
  if (value >= 0.7) return "good";
  if (value >= 0.4) return "neutral";
  if (value >= 0.2) return "watch";
  return "fail";
}

/**
 * Mini horizontal score breakdown used in candidate cards / opportunity lab.
 * Renders one row per component with a coloured progress fill.
 */
export function ScoreBreakdownBars({ total, components, compact = false }: Props) {
  const sorted = [...components].sort((a, b) => (b.weight ?? 1) - (a.weight ?? 1));

  return (
    <div className={`score-breakdown ${compact ? "compact" : ""}`.trim()}>
      {total !== undefined && (
        <div className="score-breakdown-total">
          <span>Total score</span>
          <strong>{Math.round(total * 100)}</strong>
        </div>
      )}
      <ul>
        {sorted.map((component) => {
          const clamped = Math.max(0, Math.min(1, component.value));
          const tone = component.tone ?? toneFor(clamped);
          return (
            <li key={component.label} className={tone} title={component.detail ?? component.label}>
              <span className="score-label">{component.label}</span>
              <i className="score-track" aria-hidden="true">
                <b style={{ "--score-fill": `${clamped * 100}%` } as CSSProperties} />
              </i>
              <strong className="score-value">{Math.round(clamped * 100)}</strong>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
