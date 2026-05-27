import { CircleDashed, RadioTower, Clock, Snowflake, AlertOctagon } from "lucide-react";

type Freshness = "live" | "recent" | "stale" | "partial" | "missing" | "sample" | string;

type Props = {
  freshness: Freshness;
  detail?: string;
  compact?: boolean;
};

const ICONS: Record<string, typeof RadioTower> = {
  live: RadioTower,
  recent: RadioTower,
  partial: CircleDashed,
  stale: Clock,
  sample: Snowflake,
  missing: AlertOctagon,
};

const LABELS: Record<string, string> = {
  live: "Live",
  recent: "Recent",
  partial: "Partial",
  stale: "Stale",
  sample: "Sample",
  missing: "Missing",
};

const TONE: Record<string, string> = {
  live: "live",
  recent: "live",
  partial: "watch",
  stale: "watch",
  sample: "neutral",
  missing: "fail",
};

/**
 * Truthful data-quality pill: maps the V8 freshness taxonomy to a compact
 * indicator. Never lies — `partial` and `stale` are visibly distinct from
 * `live`, and `missing` is treated as a failure tone.
 */
export function DataQualityPill({ freshness, detail, compact = false }: Props) {
  const key = (freshness || "missing").toLowerCase();
  const Icon = ICONS[key] ?? CircleDashed;
  const label = LABELS[key] ?? freshness;
  const tone = TONE[key] ?? "neutral";

  return (
    <span className={`data-quality-pill ${tone} ${compact ? "compact" : ""}`.trim()} title={detail || label}>
      <Icon size={compact ? 12 : 14} aria-hidden="true" />
      <strong>{label}</strong>
      {!compact && detail && <span>{detail}</span>}
    </span>
  );
}
