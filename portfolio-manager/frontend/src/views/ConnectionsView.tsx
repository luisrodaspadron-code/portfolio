import { useEffect, useState } from "react";
import { BrainCircuit, CheckCircle2, Database, FileText, KeyRound, Landmark, RadioTower, Trash2 } from "lucide-react";
import { deleteSecrets, saveSecrets, testConnection, updateAiModelRouter } from "../api";
import type { AiStatus, ConnectionProvider, Dashboard } from "../types";
import { getConnectionGroups } from "../lib/viewModels";
import { number, shortDateTime, titleCase } from "../lib/format";
import { Badge, CommandButton, DetailDrawer, IconSlot, SignalPanel, type UiIcon } from "../components/ui/Primitives";

const providerIcons: Record<string, UiIcon> = {
  openai: BrainCircuit,
  alpaca: RadioTower,
  fred: Landmark,
  alpha_vantage: Database,
  sec_edgar: FileText
};

function stateTone(state?: string) {
  if (["tested", "used", "live", "success", "ready", "saved"].includes(state ?? "")) return "live";
  if (["missing", "not_configured", "not_used_yet", "partial", "rate_limited", "format_error"].includes(state ?? "")) return "watch";
  if (["failed", "error"].includes(state ?? "")) return "fail";
  return "neutral";
}

function connectionTone(provider: ConnectionProvider) {
  if (!provider.configured) return "attention";
  if (provider.connection_state) return stateTone(provider.connection_state);
  if (provider.last_test?.status === "failed" || provider.state === "error") return "danger";
  if (provider.state === "live" || provider.last_test?.status === "success") return "live";
  return "good";
}

function connectionLabel(provider: ConnectionProvider) {
  if (provider.connection_state) return titleCase(provider.connection_state);
  if (!provider.configured) return "Missing";
  if (provider.last_test?.status === "failed" || provider.state === "error") return "Failed";
  if (provider.last_test?.status === "success") return "Tested";
  return "Saved";
}

function useLabel(provider: ConnectionProvider) {
  if (!provider.configured) return "Not used";
  if (provider.latest_use_state === "used") return "Used latest run";
  if (provider.latest_use_state) return titleCase(provider.latest_use_state);
  return provider.last_refresh ? "Used" : "Not used yet";
}

export function ConnectionsView({
  dashboard,
  onSaved,
  onError
}: {
  dashboard: Dashboard;
  onSaved: (message: string) => Promise<void>;
  onError: (message: string) => void;
}) {
  const [openProvider, setOpenProvider] = useState<ConnectionProvider | null>(null);
  const [values, setValues] = useState<Record<string, Record<string, string>>>({});
  const [busyProvider, setBusyProvider] = useState<string | null>(null);
  const [routerDraft, setRouterDraft] = useState<AiStatus["model_router"]>(dashboard.ai_status.model_router);
  const groups = getConnectionGroups(dashboard.connections.providers);
  const openai = dashboard.connections.providers.find((provider) => provider.provider === "openai");
  const openAiSummary = openai?.configured ? `OpenAI ${connectionLabel(openai)}` : "OpenAI missing";
  const openAiTone = openai ? connectionTone(openai) : "watch";
  const workflowAttention = dashboard.connections.providers.filter((provider) => ["failed", "format_error", "rate_limited"].includes(provider.latest_use_state ?? "")).length;
  const needsAttention = dashboard.connections.summary.missing + workflowAttention;

  useEffect(() => {
    setRouterDraft(dashboard.ai_status.model_router);
  }, [dashboard.ai_status.model_router]);

  function setField(provider: string, key: string, value: string) {
    setValues((current) => ({ ...current, [provider]: { ...(current[provider] ?? {}), [key]: value } }));
  }

  async function runTest(provider: ConnectionProvider) {
    setBusyProvider(provider.provider);
    try {
      const result = await testConnection(provider.provider) as { status?: string };
      await onSaved(
        result.status === "rate_limited"
          ? `${provider.label} key saved. Provider is rate-limiting requests; quant-only fallback is active.`
          : `${provider.label} test complete`
      );
    } catch (error) {
      onError(error instanceof Error ? error.message : `${provider.label} test failed`);
    } finally {
      setBusyProvider(null);
    }
  }

  async function save(provider: ConnectionProvider, shouldTest: boolean) {
    setBusyProvider(provider.provider);
    try {
      await saveSecrets(provider.provider, values[provider.provider] ?? {});
      setValues((current) => ({ ...current, [provider.provider]: {} }));
      let testStatus = "";
      if (shouldTest) {
        const result = await testConnection(provider.provider) as { status?: string };
        testStatus = result.status ?? "";
      }
      setOpenProvider(null);
      await onSaved(
        testStatus === "rate_limited"
          ? `${provider.label} saved. Provider is rate-limiting requests; quant-only fallback is active.`
          : shouldTest
            ? `${provider.label} saved and tested`
            : `${provider.label} saved`
      );
    } catch (error) {
      onError(error instanceof Error ? error.message : `Unable to save ${provider.label}`);
    } finally {
      setBusyProvider(null);
    }
  }

  async function remove(provider: ConnectionProvider) {
    setBusyProvider(provider.provider);
    try {
      await deleteSecrets(provider.provider);
      await onSaved(`${provider.label} removed`);
    } catch (error) {
      onError(error instanceof Error ? error.message : `Unable to remove ${provider.label}`);
    } finally {
      setBusyProvider(null);
    }
  }

  function setRouteField(route: "fast" | "specialist" | "leadPM" | "deepCompetition", key: "model" | "reasoningEffort" | "maxOutputTokens", value: string) {
    setRouterDraft((current) => ({
      ...current,
      [route]: {
        ...current[route],
        [key]: key === "maxOutputTokens" ? Number(value) : value
      }
    }));
  }

  async function saveRouter() {
    setBusyProvider("ai-router");
    try {
      await updateAiModelRouter(routerDraft as unknown as Record<string, unknown>);
      await onSaved("AI model router saved");
    } catch (error) {
      onError(error instanceof Error ? error.message : "Unable to save AI model router");
    } finally {
      setBusyProvider(null);
    }
  }

  return (
    <section className="connections-view screen-enter">
      <SignalPanel className="connections-command">
        <span>Secure local setup</span>
        <h1>Connect AI and market data</h1>
        <p>Keys stay encrypted in local app data and are never returned to the browser after save. OpenAI powers the senior-PM review and Ask Signal follow-ups.</p>
        <div className="connection-summary">
          <Badge tone={openAiTone}>
            {openAiSummary}
          </Badge>
          <Badge tone={needsAttention ? "watch" : "live"}>
            {needsAttention ? `${needsAttention} need attention` : "Ready"}
          </Badge>
        </div>
      </SignalPanel>

      <div className="connection-groups">
        {groups.map((group) => {
          const content = (
            <>
              <div className="panel-label-row">
                <span>{group.label}</span>
                <Badge tone={group.label === "Required" ? "live" : "neutral"}>{group.providers.length}</Badge>
              </div>
              <p className="group-description">{group.description}</p>
              <div className="provider-list">
                {group.providers.map((provider) => {
                const IconComponent = providerIcons[provider.provider] ?? Database;
                const busy = busyProvider === provider.provider;
                const isSec = provider.provider === "sec_edgar";
                const recordLabel =
                  provider.provider === "openai"
                    ? dashboard.ai_status.usage_totals.calls
                      ? `${number(dashboard.ai_status.usage_totals.calls)} AI calls logged`
                      : "No model runs yet"
                      : provider.records
                        ? `${number(provider.records)} records`
                        : "No local records yet";
                const latestTestLine = provider.last_test ? `${titleCase(provider.last_test.status)} · ${shortDateTime(provider.last_test.tested_at)}` : "Not tested yet";
                const recoveryMessage =
                  provider.next_fix && provider.next_fix !== "No action needed."
                    ? provider.next_fix
                    : provider.user_message ?? provider.note;
                return (
                  <article
                    className={`provider-row ${provider.provider === "openai" ? "primary-provider" : ""}`}
                    data-testid={`provider-row-${provider.provider}`}
                    key={provider.provider}
                  >
                    <div className="provider-main">
                      <IconSlot icon={IconComponent} />
                      <div>
                        <strong>{provider.label}</strong>
                        <p>
                          {isSec
                            ? "SEC EDGAR adds filing-derived fundamentals: revenue growth, gross margin, and debt-to-equity for covered stocks."
                            : provider.description}
                        </p>
                        <small>
                          {provider.fields.map((field) => (
                            <span key={field.key}>{field.configured ? field.masked_value : `${field.label} missing`}</span>
                          ))}
                        </small>
                      </div>
                    </div>
                    <div className="provider-state">
                      <div>
                        <span>Connection test</span>
                        <Badge tone={connectionTone(provider)}>{connectionLabel(provider)}</Badge>
                      </div>
                      <div>
                        <span>Latest use</span>
                        <Badge tone={stateTone(provider.latest_use_state)}>{useLabel(provider)}</Badge>
                      </div>
                      <small>{recoveryMessage}</small>
                      <span>{recordLabel} · {latestTestLine}</span>
                    </div>
                    <div className="provider-actions">
                      <CommandButton
                        icon={KeyRound}
                        variant={provider.provider === "openai" && !provider.configured ? "primary" : "secondary"}
                        data-testid={`provider-add-${provider.provider}`}
                        onClick={() => setOpenProvider(provider)}
                      >
                        {provider.provider === "openai"
                          ? provider.configured
                            ? "Review OpenAI Key"
                            : "Add OpenAI Key"
                          : isSec
                            ? provider.configured
                              ? "Review SEC Identity"
                              : "Add SEC Identity"
                          : provider.configured
                            ? "Update"
                            : "Add Key"}
                      </CommandButton>
                      <CommandButton icon={CheckCircle2} variant="secondary" disabled={!provider.configured || busy} onClick={() => runTest(provider)}>
                        Test
                      </CommandButton>
                      <CommandButton icon={Trash2} variant="danger" disabled={!provider.configured || busy} onClick={() => remove(provider)}>
                        Remove
                      </CommandButton>
                    </div>
                  </article>
                );
                })}
              </div>
            </>
          );
          return group.label === "Optional" ? (
            <SignalPanel className="connection-group" key={group.label}>
              <details className="optional-provider-disclosure">
                <summary>
                  <span>Optional providers</span>
                  <Badge tone="neutral">{group.providers.length}</Badge>
                </summary>
                {content}
              </details>
            </SignalPanel>
          ) : (
            <SignalPanel className="connection-group" key={group.label}>
              {content}
            </SignalPanel>
          );
        })}
      </div>

      <SignalPanel className="ai-audit">
        <details className="optional-provider-disclosure">
          <summary>
            <span>AI advisor audit</span>
            <Badge tone={dashboard.ai_status.state === "rate_limited" ? "watch" : dashboard.ai_status.configured ? "live" : "watch"}>
              {dashboard.ai_status.state === "rate_limited" ? "Rate limited" : dashboard.ai_status.configured ? "Connected" : "Needs key"}
            </Badge>
          </summary>
          <div className="audit-grid">
            <div>
              <span>Fast route</span>
              <strong>{dashboard.ai_status.model_router.fast.model}</strong>
            </div>
            <div>
              <span>Lead PM</span>
              <strong>{dashboard.ai_status.model_router.leadPM.model}</strong>
            </div>
            <div>
              <span>Tokens</span>
              <strong>{number(dashboard.ai_status.usage_totals.total_tokens)}</strong>
            </div>
            <div>
              <span>Last run</span>
              <strong>{dashboard.ai_status.last_run?.status ?? "none"}</strong>
            </div>
          </div>
          <div className="ai-router-editor">
            {(["fast", "specialist", "leadPM", "deepCompetition"] as const).map((route) => (
              <article key={route}>
                <div>
                  <strong>{route === "leadPM" ? "Lead PM" : route === "deepCompetition" ? "Deep competition" : titleCase(route)}</strong>
                  <span>{routerDraft[route].role}</span>
                </div>
                <label>
                  <span>Model</span>
                  <input value={routerDraft[route].model} onChange={(event) => setRouteField(route, "model", event.target.value)} />
                </label>
                <label>
                  <span>Reasoning</span>
                  <select value={routerDraft[route].reasoningEffort} onChange={(event) => setRouteField(route, "reasoningEffort", event.target.value)}>
                    <option value="low">Low</option>
                    <option value="medium">Medium</option>
                    <option value="high">High</option>
                    <option value="xhigh">Xhigh</option>
                  </select>
                </label>
                <label>
                  <span>Tokens</span>
                  <input
                    type="number"
                    min={200}
                    max={8000}
                    step={100}
                    value={routerDraft[route].maxOutputTokens}
                    onChange={(event) => setRouteField(route, "maxOutputTokens", event.target.value)}
                  />
                </label>
              </article>
            ))}
            <CommandButton icon={CheckCircle2} variant="secondary" disabled={busyProvider === "ai-router"} onClick={saveRouter}>
              Save model router
            </CommandButton>
          </div>
        </details>
      </SignalPanel>

      <DetailDrawer
        open={Boolean(openProvider)}
        onOpenChange={(open) => !open && setOpenProvider(null)}
        title={openProvider ? `${openProvider.configured ? "Update" : "Add"} ${openProvider.label}` : "Add connection"}
        eyebrow="Local encrypted secret"
      >
        {openProvider && (
          <form
            className="connection-secret-form"
            data-testid="connection-secret-form"
            onSubmit={(event) => {
              event.preventDefault();
              save(openProvider, true);
            }}
          >
            <p>Paste the key here once. Signal PM stores it locally, masks it in the UI, and never commits it to source.</p>
            {openProvider.fields.map((field) => (
              <label key={field.key}>
                <span>{field.label}</span>
                <input
                  type={field.secret ? "password" : "text"}
                  autoComplete="off"
                  placeholder={field.placeholder}
                  value={values[openProvider.provider]?.[field.key] ?? ""}
                  onChange={(event) => setField(openProvider.provider, field.key, event.target.value)}
                />
              </label>
            ))}
            <div className="drawer-actions">
              <CommandButton icon={CheckCircle2} variant="primary" disabled={busyProvider === openProvider.provider} type="submit">
                Save & Test
              </CommandButton>
              <CommandButton icon={CheckCircle2} variant="secondary" disabled={busyProvider === openProvider.provider} type="button" onClick={() => save(openProvider, false)}>
                Save without test
              </CommandButton>
            </div>
          </form>
        )}
      </DetailDrawer>
    </section>
  );
}
