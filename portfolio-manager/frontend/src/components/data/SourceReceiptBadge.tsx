import { Database } from "lucide-react";
import { shortDateTime } from "../../lib/format";
import { DataQualityPill } from "./DataQualityPill";

type Props = {
  source: string;
  freshness?: string;
  timestamp?: string | null;
  /** e.g. "Alpaca · IEX feed" */
  detail?: string;
  compact?: boolean;
};

/**
 * Visible provenance badge for a single piece of data on screen. Used inside
 * advisory tickets, candidate cards, holding drawers — anywhere we display a
 * number that came from a specific provider so the user can audit it.
 */
export function SourceReceiptBadge({ source, freshness, timestamp, detail, compact = false }: Props) {
  return (
    <span className={`source-receipt-badge ${compact ? "compact" : ""}`.trim()} aria-label={`Source: ${source}`}>
      <Database size={compact ? 12 : 14} aria-hidden="true" />
      <strong>{source}</strong>
      {freshness && <DataQualityPill freshness={freshness} compact />}
      {timestamp && <em>{shortDateTime(timestamp)}</em>}
      {detail && !compact && <span>{detail}</span>}
    </span>
  );
}
