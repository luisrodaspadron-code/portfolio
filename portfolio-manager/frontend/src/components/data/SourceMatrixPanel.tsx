import type { SourceMatrix, SourceMatrixEntry } from "../../types";
import { number, shortDateTime, titleCase } from "../../lib/format";
import { Badge, SignalPanel } from "../ui/Primitives";
import { DataQualityPill } from "./DataQualityPill";

const FRIENDLY: Record<string, { label: string; description: string }> = {
  prices: { label: "Prices", description: "Live and recent quotes for portfolio symbols and the universe." },
  liquidity: { label: "Liquidity", description: "Average dollar volume used to enforce liquidity gates." },
  fundamentals: { label: "Fundamentals", description: "Filings-derived facts and basics from SEC EDGAR." },
  filings: { label: "Filings", description: "Raw filings index and structured XBRL when available." },
  macro: { label: "Macro", description: "FRED / OECD signals used for macro context and regime." },
  factors: { label: "Factors", description: "Style and factor model inputs (Ken French / internal)." },
  events: { label: "Events", description: "News, earnings, and event-driven inputs (optional)." },
  ipoCalendar: { label: "IPO calendar", description: "Recent IPOs used for limited-history playbooks." },
  cryptoMetadata: { label: "Crypto", description: "Crypto data (disabled by default per policy)." },
  portfolioState: { label: "Portfolio state", description: "Local holdings, cash, average cost, and import provenance." },
  ai: { label: "AI / LLM", description: "Model routes, reasoning effort, and prompt versions." },
  telemetry: { label: "Telemetry", description: "Local-only run telemetry and audit trail." },
};

type Props = {
  matrix: SourceMatrix | null | undefined;
  /** Fired when the user clicks the per-row Fix button. */
  onFix?: (key: string, entry: SourceMatrixEntry) => void;
};

function SourceRow({ k, entry, onFix }: { k: string; entry: SourceMatrixEntry; onFix?: Props["onFix"] }) {
  const meta = FRIENDLY[k] ?? { label: titleCase(k), description: "Provider entry." };
  const status = entry.usedInRun ? "Used in last run" : "Not used in last run";
  return (
    <tr>
      <th scope="row">
        <strong>{meta.label}</strong>
        <em>{meta.description}</em>
      </th>
      <td>
        <DataQualityPill freshness={entry.freshness ?? "missing"} compact detail={entry.coverage ?? undefined} />
      </td>
      <td>
        <strong>{entry.provider ?? "n/a"}</strong>
        {entry.fallback && entry.fallback !== entry.provider && (
          <em>fallback {entry.fallback}</em>
        )}
      </td>
      <td>
        <strong>{entry.coverage ?? "—"}</strong>
        {entry.symbolCount !== undefined && <em>{number(entry.symbolCount)} symbols</em>}
        {entry.recordCount !== undefined && <em>{number(entry.recordCount)} records</em>}
      </td>
      <td>{entry.latestTimestamp ? shortDateTime(entry.latestTimestamp) : "—"}</td>
      <td>{status}</td>
      <td>
        {entry.warnings?.length ? (
          <ul className="source-matrix-warnings">
            {entry.warnings.slice(0, 2).map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        ) : (
          <span className="source-matrix-ok">No warnings.</span>
        )}
      </td>
      <td>
        {onFix && (
          <button type="button" className="source-matrix-fix" onClick={() => onFix(k, entry)}>
            Fix
          </button>
        )}
      </td>
    </tr>
  );
}

/**
 * Source Matrix: the data provenance table the Connections screen lives on.
 * Renders every category from the backend `sourceMatrix` payload — provider,
 * freshness, coverage, last refresh, whether it was used in the last run,
 * warnings, and an optional Fix button.
 */
export function SourceMatrixPanel({ matrix, onFix }: Props) {
  if (!matrix) {
    return (
      <SignalPanel className="source-matrix-panel" testId="source-matrix-panel">
        <div className="panel-label-row">
          <span>Source matrix</span>
          <Badge tone="watch">Waiting</Badge>
        </div>
        <p>No source matrix yet. Run the advisor to populate provider provenance.</p>
      </SignalPanel>
    );
  }

  const entries = Object.entries(matrix.matrix);

  return (
    <SignalPanel className="source-matrix-panel" testId="source-matrix-panel">
      <div className="panel-label-row">
        <span>Source matrix</span>
        <Badge tone="live">{entries.length} sources</Badge>
      </div>
      <p className="source-matrix-eyebrow">
        Provenance and freshness for every input the deterministic engine reads. Generated{" "}
        {shortDateTime(matrix.generatedAt)} · policy {matrix.policyVersion} · preset {matrix.selectedPreset}.
      </p>

      <div className="source-matrix-table-wrap">
        <table className="source-matrix-table">
          <thead>
            <tr>
              <th>Source</th>
              <th>Freshness</th>
              <th>Provider</th>
              <th>Coverage</th>
              <th>Last refresh</th>
              <th>Status</th>
              <th>Warnings</th>
              <th aria-label="Actions" />
            </tr>
          </thead>
          <tbody>
            {entries.map(([key, entry]) => (
              <SourceRow key={key} k={key} entry={entry} onFix={onFix} />
            ))}
          </tbody>
        </table>
      </div>

      <details className="ai-disclosure">
        <summary>What data is sent to the AI?</summary>
        <p>
          The deterministic engine produces the canonical packet. Only the {" "}
          <strong>LLMReviewPacket</strong> subset (positions, decisions, risk gates, data freshness summary,
          and the selected policy summary) is sent to the model. Raw provider secrets, account credentials,
          and trade execution endpoints are never sent.
        </p>
      </details>
    </SignalPanel>
  );
}
