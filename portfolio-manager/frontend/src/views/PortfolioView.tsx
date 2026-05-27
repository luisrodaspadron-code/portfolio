import { useDropzone } from "react-dropzone";
import { useMemo, useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { CheckCircle2, Download, Import, PieChart, ShieldAlert } from "lucide-react";
import { importHoldings } from "../api";
import type { AdvisorPacketAction, Dashboard, Position } from "../types";
import { money, number, pct, signedMoney, signedPct, titleCase } from "../lib/format";
import { DataGrid } from "../components/data/DataGrid";
import { PortfolioTrendChart } from "../components/visuals/PortfolioTrendChart";
import { PortfolioConstellation } from "../components/visuals/PortfolioConstellation";
import { PortfolioMap } from "../components/visuals/PortfolioMap";
import { portfolioConstellationNodes } from "../lib/viewModels";
import { Badge, CommandButton, EmptyState, SignalPanel } from "../components/ui/Primitives";
import { HoldingDetailDrawer } from "../components/portfolio/HoldingDetailDrawer";

type PreviewState = {
  headers: string[];
  rows: string[][];
  inferred: boolean;
  warnings: string[];
};

const previewHeaders = ["Symbol", "Shares", "Average cost"];

function splitCsvLine(line: string) {
  return line.split(",").map((cell) => cell.trim());
}

function looksLikeHeader(row: string[]) {
  const values = row.map((cell) => cell.toLowerCase().replace(/\s+/g, "_"));
  return values.some((cell) => ["symbol", "ticker", "quantity", "shares", "qty", "avg_cost", "average_cost", "cost_basis"].includes(cell));
}

function parsePreview(text: string): PreviewState {
  const rawRows = text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map(splitCsvLine);
  if (!rawRows.length) return { headers: previewHeaders, rows: [], inferred: false, warnings: [] };

  const inferred = !looksLikeHeader(rawRows[0]);
  const rows = (inferred ? rawRows : rawRows.slice(1)).slice(0, 8).map((row) => [row[0] ?? "", row[1] ?? "", row[2] ?? ""]);
  const warnings = rows
    .map((row, index) => {
      if (!row[0]) return `Row ${index + 1}: missing symbol.`;
      if (!row[1] || Number(row[1]) <= 0) return `Row ${index + 1}: shares must be greater than zero.`;
      if (!row[2] || Number(row[2]) <= 0) return `Row ${index + 1}: valuation will use market data after import.`;
      return "";
    })
    .filter(Boolean);
  return { headers: inferred ? previewHeaders : rawRows[0].slice(0, 3), rows, inferred, warnings };
}

function canonicalizeCsv(text: string) {
  const parsed = parsePreview(text);
  if (!parsed.inferred) return text;
  return ["symbol,quantity,avg_cost", ...parsed.rows.map((row) => row.join(","))].join("\n");
}

function actionTone(action?: string) {
  if (action === "TRIM" || action === "BLOCKED_BY_RISK") return "danger";
  if (action === "WAIT_FOR_DATA" || action === "REVIEW_MANUALLY") return "attention";
  if (action === "ADD" || action === "STAGGER_ENTRY") return "live";
  if (action === "HOLD") return "good";
  return "neutral";
}

function actionLabel(action?: string) {
  return action ? titleCase(action) : "Waiting";
}

function dataTone(freshness?: string) {
  if (freshness === "live" || freshness === "recent") return "live";
  if (freshness === "missing" || freshness === "stale" || freshness === "insufficient" || freshness === "partial" || freshness === "missing_price") return "watch";
  return "neutral";
}

function maxBreachOver(decision?: AdvisorPacketAction | null) {
  return Math.max(0, ...(decision?.riskBreaches ?? []).map((breach) => breach.observed - breach.limit));
}

export function PortfolioView({
  dashboard,
  onDone,
  onError,
  onAsk,
}: {
  dashboard: Dashboard;
  onDone: (message: string) => Promise<void>;
  onError: (message: string) => void;
  onAsk?: (question?: string) => void;
}) {
  const template = "symbol,quantity,avg_cost\nAAPL,12,185.40\nSPY,20,520.00\nCASH,2500,2500\n";
  const [file, setFile] = useState<File | null>(null);
  const [pastedCsv, setPastedCsv] = useState("");
  const [preview, setPreview] = useState<PreviewState>({ headers: previewHeaders, rows: [], inferred: false, warnings: [] });
  const [importWarnings, setImportWarnings] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [selectedPosition, setSelectedPosition] = useState<Position | null>(null);
  const [actionFilter, setActionFilter] = useState("all");
  const real = dashboard.real_portfolio;
  const hasHoldings = Boolean(real && real.positions.length > 0);
  const hasTrendHistory = dashboard.portfolio_trend.points.length >= 2;
  const latestTrendValue = dashboard.portfolio_trend.points.length
    ? dashboard.portfolio_trend.points[dashboard.portfolio_trend.points.length - 1].value
    : real?.total_value ?? 0;
  const missingPrices = real?.positions.filter((position) => position.valuation_status === "missing_price").length ?? 0;
  const decisionsBySymbol = useMemo(
    () => new Map((dashboard.advisor_packet.positions ?? []).map((item) => [item.symbol, item])),
    [dashboard.advisor_packet.positions]
  );
  const topPosition = real?.positions.reduce<Position | null>((largest, position) => (!largest || position.weight > largest.weight ? position : largest), null);
  const filteredPositions = useMemo(() => {
    const rows = real?.positions ?? [];
    const filtered = rows.filter((position) => {
      const decision = decisionsBySymbol.get(position.symbol);
      if (actionFilter === "all") return true;
      if (actionFilter === "breach") return Boolean(decision?.riskBreaches.length);
      if (actionFilter === "data") {
        const freshness = decision?.dataQuality.freshness ?? position.valuation_status;
        return ["missing", "stale", "insufficient", "missing_price", "partial"].includes(freshness) || position.valuation_status !== "priced";
      }
      return decision?.action === actionFilter;
    });
    return [...filtered].sort((a, b) => {
      const breachDelta = maxBreachOver(decisionsBySymbol.get(b.symbol)) - maxBreachOver(decisionsBySymbol.get(a.symbol));
      if (breachDelta !== 0) return breachDelta;
      return b.weight - a.weight;
    });
  }, [actionFilter, decisionsBySymbol, real?.positions]);
  const tableFilters = useMemo(() => {
    const rows = real?.positions ?? [];
    const count = (predicate: (position: Position) => boolean) => rows.filter(predicate).length;
    return [
      { value: "all", label: "All", count: rows.length },
      { value: "TRIM", label: "Trim", count: count((position) => decisionsBySymbol.get(position.symbol)?.action === "TRIM") },
      { value: "HOLD", label: "Hold", count: count((position) => decisionsBySymbol.get(position.symbol)?.action === "HOLD") },
      {
        value: "WAIT_FOR_DATA",
        label: "Wait",
        count: count((position) => decisionsBySymbol.get(position.symbol)?.action === "WAIT_FOR_DATA")
      },
      { value: "breach", label: "Breaches", count: count((position) => Boolean(decisionsBySymbol.get(position.symbol)?.riskBreaches.length)) },
      {
        value: "data",
        label: "Data gaps",
        count: count((position) => {
          const decision = decisionsBySymbol.get(position.symbol);
          const freshness = decision?.dataQuality.freshness ?? position.valuation_status;
          return ["missing", "stale", "insufficient", "missing_price", "partial"].includes(freshness) || position.valuation_status !== "priced";
        })
      }
    ];
  }, [decisionsBySymbol, real?.positions]);

  const onDrop = async (files: File[]) => {
    const next = files[0];
    if (!next) return;
    setFile(next);
    setPastedCsv("");
    setPreview(parsePreview(await next.text()));
  };
  const dropzone = useDropzone({ onDrop, accept: { "text/csv": [".csv"] }, multiple: false });

  const columns = useMemo<ColumnDef<Position>[]>(
    () => [
      {
        accessorKey: "symbol",
        header: "Holding",
        cell: ({ row }) => {
          const decision = decisionsBySymbol.get(row.original.symbol);
          return (
            <div className="holding-symbol-cell">
              <strong>{row.original.symbol}</strong>
              <span>{row.original.name}</span>
              {decision?.riskBreaches[0] && <em>{pct(decision.riskBreaches[0].observed - decision.riskBreaches[0].limit)} over cap</em>}
            </div>
          );
        }
      },
      {
        id: "decision",
        header: "Decision",
        cell: ({ row }) => {
          const item = decisionsBySymbol.get(row.original.symbol);
          return item ? (
            <div className="decision-cell">
              <Badge tone={actionTone(item.action)}>{actionLabel(item.action)}</Badge>
              <span>{item.reasonCode || "Policy checked"}</span>
            </div>
          ) : (
            <span>Waiting</span>
          );
        }
      },
      {
        id: "weight",
        header: "Weight / cap",
        cell: ({ row }) => (
          <div className="weight-cell">
            <strong>{pct(row.original.weight)}</strong>
            <span>
              {decisionsBySymbol.get(row.original.symbol)?.targetWeight
                ? `target ${pct(decisionsBySymbol.get(row.original.symbol)?.targetWeight ?? 0)}`
                : "target pending"}
            </span>
          </div>
        )
      },
      { accessorKey: "market_value", header: "Value", cell: (info) => money(Number(info.getValue())) },
      { accessorKey: "quantity", header: "Shares", cell: (info) => number(Number(info.getValue())) },
      {
        id: "price",
        header: "Price / data",
        cell: ({ row }) => (
          <div className="data-quality-cell">
            <strong>{money(row.original.latest_price)}</strong>
            <Badge tone={dataTone(decisionsBySymbol.get(row.original.symbol)?.dataQuality.freshness)}>
              {titleCase(decisionsBySymbol.get(row.original.symbol)?.dataQuality.freshness ?? row.original.valuation_status)}
            </Badge>
          </div>
        )
      },
      {
        id: "sector",
        header: "Sector",
        cell: ({ row }) => (
          <div>
            <strong>{row.original.sector}</strong>
            <span>{row.original.asset_class} · {row.original.theme ?? "No theme"}</span>
          </div>
        )
      }
    ],
    [decisionsBySymbol]
  );

  async function submit() {
    const source = file ?? (pastedCsv.trim() ? new File([canonicalizeCsv(pastedCsv)], "holdings.csv", { type: "text/csv" }) : null);
    if (!source) {
      onError("Choose a holdings CSV or paste holdings first.");
      return;
    }
    setBusy(true);
    setImportWarnings([]);
    try {
      const result = await importHoldings(source);
      setFile(null);
      setPastedCsv("");
      setPreview({ headers: previewHeaders, rows: [], inferred: false, warnings: [] });
      setImportWarnings([...(result.warnings ?? []), ...(result.rejected_rows ?? []).map((row) => `Row ${row.row}: ${row.reason}`)]);
      await onDone(result.status === "partial" ? "Holdings imported with warnings" : "Real holdings imported");
    } catch (error) {
      onError(error instanceof Error ? error.message : "Import failed. Check symbol and shares, then try again.");
    } finally {
      setBusy(false);
    }
  }

  const importPanel = (
    <SignalPanel className={`import-command ${hasHoldings ? "update-mode" : ""}`} testId="import-wizard">
      <div className="import-copy">
        <span>Real-money source of truth</span>
        <h1>{hasHoldings ? "Update holdings" : "Real holdings command center"}</h1>
        <p>Paste or drop holdings. Headerless rows are okay: Symbol, shares, average cost.</p>
      </div>
      <div className={`dropzone ${dropzone.isDragActive ? "active" : ""}`} {...dropzone.getRootProps()}>
        <input {...dropzone.getInputProps({ className: "visually-hidden-file-input" })} data-testid="holdings-file-input" />
        <Import size={28} />
        <strong>{file ? file.name : dropzone.isDragActive ? "Drop to preview" : "Drop CSV here"}</strong>
        <span>or click to choose a file</span>
      </div>
      <label className="paste-zone">
        <span>Paste CSV</span>
        <textarea
          value={pastedCsv}
          placeholder={template}
          onChange={(event) => {
            setPastedCsv(event.target.value);
            setFile(null);
            setPreview(parsePreview(event.target.value));
          }}
        />
      </label>
      <div className="import-footer">
        <a className="link-button" href={`data:text/csv;charset=utf-8,${encodeURIComponent(template)}`} download="holdings-template.csv">
          <Download size={17} />
          Template
        </a>
        <CommandButton icon={CheckCircle2} variant="primary" disabled={busy} data-testid="import-holdings-submit" onClick={submit}>
          {busy ? "Importing" : "Import real holdings"}
        </CommandButton>
      </div>
    </SignalPanel>
  );

  return (
    <section className="portfolio-view screen-enter">
      {hasHoldings ? (
        <details className="update-holdings-drawer">
          <summary>
            <span>Update real holdings</span>
            <Badge tone="neutral">{real?.positions.length ?? 0} current</Badge>
          </summary>
          {importPanel}
        </details>
      ) : importPanel}

      {(preview.rows.length > 0 || importWarnings.length > 0) && (
        <SignalPanel className="preview-panel">
          <div className="panel-label-row">
            <span>{preview.inferred ? "Inferred preview" : "CSV preview"}</span>
            <Badge tone="live">{preview.rows.length || importWarnings.length} rows</Badge>
          </div>
          {preview.rows.length > 0 && (
            <div className="preview-grid">
              <div className="preview-header">
                {preview.headers.map((header) => (
                  <span key={header}>{header}</span>
                ))}
              </div>
              {preview.rows.map((row, index) => (
                <div key={`${row.join("-")}-${index}`}>
                  {row.slice(0, 3).map((cell, cellIndex) => (
                    <span key={`${cell}-${cellIndex}`}>{cell || "-"}</span>
                  ))}
                </div>
              ))}
            </div>
          )}
          {[...preview.warnings, ...importWarnings].length > 0 && (
            <div className="import-warning-list">
              {[...preview.warnings, ...importWarnings].slice(0, 6).map((warning) => (
                <div key={warning}>{warning}</div>
              ))}
            </div>
          )}
        </SignalPanel>
      )}

      <SignalPanel className="holdings-grid-panel portfolio-primary-table">
        <div className="panel-label-row">
          <span>Holdings command table</span>
          <Badge tone={hasHoldings ? "live" : "watch"}>{hasHoldings && real ? `${filteredPositions.length} of ${real.positions.length}` : "empty"}</Badge>
        </div>
        {hasHoldings && real ? (
          <>
            <div className="portfolio-filter-bar">
              {tableFilters.map((filter) => (
                <button
                  aria-pressed={actionFilter === filter.value}
                  className={actionFilter === filter.value ? "active" : ""}
                  data-testid={`portfolio-filter-${filter.value.toLowerCase()}`}
                  key={filter.value}
                  onClick={() => setActionFilter(filter.value)}
                >
                  <span>{filter.label}</span>
                  <strong>{filter.count}</strong>
                </button>
              ))}
            </div>
            <DataGrid
              data={filteredPositions}
              columns={columns}
              placeholder="Search symbols, names, sectors..."
              onRowClick={setSelectedPosition}
              getRowClassName={(position) => (decisionsBySymbol.get(position.symbol)?.riskBreaches.length ? "risk-row" : "")}
            />
          </>
        ) : (
          <EmptyState title="No holdings loaded" body="Your real-money holdings will appear here after import." />
        )}
      </SignalPanel>

      <section className="portfolio-metrics">
        <SignalPanel className="metric-tile">
          <span>Total tracked</span>
          <strong>{hasHoldings && real ? money(real.total_value) : "Not connected"}</strong>
          <p>{hasHoldings && real ? `${real.positions.length} holdings · ${money(real.cash)} cash` : "Import positions required"}</p>
        </SignalPanel>
        <SignalPanel className="metric-tile">
          <span>Largest position</span>
          <strong>{topPosition ? `${topPosition.symbol} ${pct(topPosition.weight)}` : "Waiting"}</strong>
          <p>{topPosition ? `${money(topPosition.market_value)} · ${topPosition.sector}` : "No real positions yet"}</p>
        </SignalPanel>
        <SignalPanel className="metric-tile">
          <span>Risk state</span>
          <strong>{hasHoldings && real ? titleCase(dashboard.advisor_packet.portfolioRisk.severity) : "Waiting"}</strong>
          <p>
            {hasHoldings && real
              ? `${dashboard.advisor_packet.portfolioRisk.issueCount} current issue${dashboard.advisor_packet.portfolioRisk.issueCount === 1 ? "" : "s"}`
              : "No real positions yet"}
          </p>
        </SignalPanel>
        <SignalPanel className="metric-tile">
          <span>Data mode</span>
          <strong>{titleCase(dashboard.data_freshness.provider_mode)}</strong>
          <p>{missingPrices ? `${missingPrices} holdings need data refresh` : `${titleCase(dashboard.data_freshness.preferred_price_source)} source`}</p>
        </SignalPanel>
      </section>

      {hasHoldings && (
        <SignalPanel className="trend-panel">
          <div className="panel-label-row">
            <span>Portfolio worth over time</span>
            <Badge tone={dashboard.portfolio_trend.day_change >= 0 ? "live" : "fail"}>{titleCase(dashboard.portfolio_trend.granularity)}</Badge>
          </div>
          <div className="trend-headline">
            <strong className={hasTrendHistory ? (dashboard.portfolio_trend.day_change >= 0 ? "positive" : "negative") : undefined}>
              {hasTrendHistory ? signedMoney(dashboard.portfolio_trend.day_change) : money(latestTrendValue)}
            </strong>
            <span>
              {hasTrendHistory
                ? `${signedPct(dashboard.portfolio_trend.day_change_pct)} ${dashboard.portfolio_trend.latest_change_label} · ${signedPct(dashboard.portfolio_trend.week_change_pct)} week`
                : "Current value is ready. Trend needs consistent live history."}
            </span>
          </div>
          <PortfolioTrendChart trend={dashboard.portfolio_trend} />
          {hasTrendHistory ? <p className="panel-note">{dashboard.portfolio_trend.source_note}</p> : null}
        </SignalPanel>
      )}

      {hasHoldings && real && (
        <SignalPanel className="portfolio-map-panel" testId="portfolio-map-panel">
          <PortfolioMap
            portfolio={real}
            advisorPacket={dashboard.advisor_packet ?? null}
            onSelect={(symbol) => {
              const target = real.positions.find((position) => position.symbol === symbol);
              if (target) setSelectedPosition(target);
            }}
          />
        </SignalPanel>
      )}

      <section className="portfolio-detail-grid">
        {hasHoldings && (
          <SignalPanel className="allocation-panel constellation-panel">
            <div className="panel-label-row">
              <span>Risk / signal map</span>
              <Badge tone={topPosition && topPosition.weight > Number(dashboard.risk_rules.max_single_stock_weight ?? 0.08) ? "fail" : "live"}>Weighted</Badge>
            </div>
            <PortfolioConstellation nodes={portfolioConstellationNodes(dashboard)} onImport={() => window.scrollTo({ top: 0, behavior: "smooth" })} />
          </SignalPanel>
        )}
        <SignalPanel className="allocation-panel">
          <div className="panel-label-row">
            <span>Allocation</span>
            <PieChart size={16} />
          </div>
          {hasHoldings && real ? (
            <div className="allocation-stack">
              {real.positions.slice(0, 10).map((position) => (
                <div key={position.symbol}>
                  <span>{position.symbol}</span>
                  <i style={{ width: `${Math.min(100, position.weight * 100)}%` }} />
                  <strong>{pct(position.weight)}</strong>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState title="No allocation yet" body="Import holdings to see your real portfolio shape." />
          )}
        </SignalPanel>
        <SignalPanel className="allocation-panel">
          <div className="panel-label-row">
            <span>Risk notes</span>
            <ShieldAlert size={16} />
          </div>
          <div className="risk-note-stack">
            {hasHoldings && real && real.stress.warnings.length ? (
              real.stress.warnings.map((warning) => <div key={warning}>{warning}</div>)
            ) : (
              <div>{hasHoldings ? "No active hard-rule breach at this snapshot." : "Import holdings to activate risk checks."}</div>
            )}
          </div>
        </SignalPanel>
      </section>

      <HoldingDetailDrawer
        dashboard={dashboard}
        position={selectedPosition}
        open={Boolean(selectedPosition)}
        onOpenChange={(open) => !open && setSelectedPosition(null)}
        onAsk={(question) => onAsk?.(question)}
      />
    </section>
  );
}
