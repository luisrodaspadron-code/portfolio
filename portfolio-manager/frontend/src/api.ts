import type { AdvisorDecision, AdvisorEval, AdvisorReview, AdvisorRunResult, AdvisorRunStart, AdvisorRunStatus, AdvisorTrace, AiStatus, BacktestRun, ConnectionsStatus, Dashboard, HoldingsImportResult, QuantDiagnostics, Recommendation, ResearchMemo, UniverseStatus } from "./types";

function userSafeError(message: string) {
  if (/429|too many requests|rate.?limit/i.test(message)) {
    return "OpenAI is rate-limiting this key right now. Quant-only fallback is active.";
  }
  if (/api\.openai\.com|httpx|traceback|client error/i.test(message)) {
    return "A provider request failed. Signal PM is using local fallback data where possible.";
  }
  return message.replace(/For more information.*$/i, "").trim();
}

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    headers: options?.body instanceof FormData ? undefined : { "Content-Type": "application/json" },
    ...options
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    const detail = Array.isArray(error.detail)
      ? error.detail.map((item: { msg?: string; loc?: string[] }) => `${item.loc?.join(".") ?? "field"}: ${item.msg ?? "invalid"}`).join("; ")
      : error.detail;
    throw new Error(typeof detail === "string" ? userSafeError(detail) : "Request failed");
  }
  return response.json() as Promise<T>;
}

export function getDashboard() {
  return request<Dashboard>("/api/dashboard");
}

export function refreshData() {
  return request<{ status: string; message: string }>("/api/data/refresh", { method: "POST" });
}

export function runRecommendations() {
  return request<{ recommendations: Recommendation[] }>("/api/recommendations/run", {
    method: "POST",
    body: JSON.stringify({ max_ideas: 12 })
  });
}

export function runAdvisorNow() {
  return request<AdvisorRunResult>("/api/advisor/run", { method: "POST" });
}

export function startAdvisorRun() {
  return request<AdvisorRunStart>("/api/advisor/runs", { method: "POST" });
}

export function getAdvisorRun(runId: number) {
  return request<AdvisorRunStatus>(`/api/advisor/runs/${runId}`);
}

export function runAdvisorReview() {
  return request<{ advisor_review: AdvisorReview }>("/api/advisor/review", { method: "POST" });
}

export function refreshUniverse() {
  return request<{ universe: UniverseStatus }>("/api/universe/refresh", { method: "POST" });
}

export function getUniverseStatus() {
  return request<{ universe: UniverseStatus }>("/api/universe/status");
}

export function runAdvisorDecision() {
  return request<{ advisor_decision: AdvisorDecision }>("/api/advisor/decision", { method: "POST" });
}

export function runLiveAdvisorEval() {
  return request<{ eval: AdvisorEval }>("/api/evals/advisor-live", { method: "POST" });
}

export function getAdvisorTrace() {
  return request<{ trace: AdvisorTrace }>("/api/advisor/trace");
}

export function askCopilot(payload: { question: string; conversation_id?: string; screen_context?: string }) {
  return request<{
    answer: string;
    data_used: string[];
    limitations: string[];
    suggested_followups: string[];
    conversation_id: string;
    packet_hash: string;
    model: string;
    status: string;
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
  }>("/api/ai/copilot", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function runBacktest(symbols: string, maxPositions: number) {
  return request<BacktestRun>("/api/backtests", {
    method: "POST",
    body: JSON.stringify({
      symbols: symbols.split(",").map((symbol) => symbol.trim()).filter(Boolean),
      max_positions: maxPositions,
      rebalance_frequency: "weekly",
      transaction_cost_bps: 5
    })
  });
}

export function placePaperOrder(payload: { symbol: string; side: "buy" | "sell"; quantity: number; price?: number }) {
  return request("/api/portfolio/paper-order", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function importHoldings(file: File) {
  const form = new FormData();
  form.append("file", file);
  return request<HoldingsImportResult>("/api/import/holdings-csv", {
    method: "POST",
    body: form
  });
}

export function updatePolicy(values: { objective: string; risk: string; diversification: string }) {
  return request("/api/settings/policy", {
    method: "PUT",
    body: JSON.stringify(values)
  });
}

export function saveOpenAiKey(apiKey: string) {
  return request("/api/settings/openai-key", {
    method: "PUT",
    body: JSON.stringify({ api_key: apiKey })
  });
}

export function testAiConnection() {
  return request("/api/settings/ai/test", { method: "POST" });
}

export function updateAiModelRouter(values: Record<string, unknown>) {
  return request<{ ai_status: AiStatus }>("/api/settings/ai/model-router", {
    method: "PUT",
    body: JSON.stringify(values)
  });
}

export function getConnections() {
  return request<ConnectionsStatus>("/api/settings/connections");
}

export function saveSecrets(provider: string, values: Record<string, string>) {
  return request<{ connections: ConnectionsStatus }>("/api/settings/secrets", {
    method: "PUT",
    body: JSON.stringify({ provider, values })
  });
}

export function testConnection(provider: string) {
  return request("/api/settings/connections/test", {
    method: "POST",
    body: JSON.stringify({ provider })
  });
}

export function deleteSecrets(provider: string) {
  return request<{ connections: ConnectionsStatus }>(`/api/settings/secrets/${provider}`, { method: "DELETE" });
}

export function getResearchMemos() {
  return request<{ memos: ResearchMemo[] }>("/api/research/memos");
}

export function getQuantDiagnostics() {
  return request<QuantDiagnostics>("/api/quant/diagnostics");
}
