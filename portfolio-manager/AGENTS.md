# Signal Prime Engineering Contract

## Repo Shape
- Frontend: React + TypeScript in `frontend/src`; build commands run from `frontend`.
- Backend: FastAPI + SQLite in `backend/app`; tests run from `backend`.
- Provider adapters live in `backend/app/providers`.
- Portfolio, risk, advisor, AI, policy, and connection services live in `backend/app/services`.
- Canonical risk policy lives in `backend/app/services/policy_engine.py`.

## Commands
- Backend tests: `cd backend && .venv/bin/pytest -q`
- Frontend typecheck: `cd frontend && npm test`
- Frontend build: `cd frontend && npm run build`
- Frontend audit: `cd frontend && npm audit --audit-level=high`
- Local backend: `cd backend && .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`
- Local frontend: `cd frontend && npm run dev`

## Non-Negotiable Architecture
- LLMs may explain, summarize, challenge, and produce narrative memos.
- LLMs must not calculate portfolio weights, enforce risk caps, size actions, detect hard rule breaches, rank candidates, or produce the final executable decision object.
- Deterministic backend code is the source of truth for math, sizing, ranking, risk gates, data freshness, and eligibility.
- The frontend renders from the canonical `AdvisorPacket` / `DecisionReceipt`; it does not recompute financial decisions from scattered local state.
- The canonical `AdvisorPacket` is built **deterministic-first** from `DeterministicEngineResult`. LLM narrative is appended; it is not required for the packet to exist.
- The LLM consumes an `LLMReviewPacket` and produces only an `LLMReviewOutput` (narrative + critique). LLM output never replaces canonical action, target weight, trim shares, add plan, eligibility, or priority.
- No UI may imply real broker execution while `real_money_trading_enabled` is false.
- `autopilot_enabled` defaults to `False`. Autopilot may only be turned on by explicit user action.

## Canonical Risk Policy
- All math, gates, and UI thresholds read from a typed `RiskPolicy` produced by `policy_engine.selected_risk_policy(conn)`.
- Presets: `conservative`, `balanced`, `aggressive`, `competition`. `custom` requires explicit validation.
- Every preset defines multi-threshold position policy: `target`, `warning`, `hardBuyBlock`, `urgentReview`, `extreme`. A single magic 8% number is not acceptable.
- Sector policy includes `warning`, `hardCap`, optional benchmark-relative cap, and `maxActiveOverweight`.
- Broad ETF policy may exempt from single-stock cap but caps single broad ETF exposure.
- Thematic / leveraged ETFs are not treated like broad core ETFs; they have their own cap and require look-through or theme-risk label.
- Crypto is disabled by default. Enabling crypto requires explicit user enablement, 24/7 freshness, custody warning, and small total/single caps.
- Data quality policy expresses live / recent freshness thresholds in seconds (separate equity vs crypto) and minimum history days for restricted vs full signal.
- Liquidity policy expresses minimum dollar volume and maximum trade size as percent of ADV.
- Remediation policy controls allow-risk-reducing / block-risk-increasing during breach, tax warning requirement, and tranche bounds.

## Trim Math Compliance Modes
- `strict_below_threshold`: whole-share rounding uses `ceil` so the post-trim weight is strictly below the policy threshold. Fractional rounding uses `round_up_to_precision`.
- `reduce_only`: whole-share rounding uses `floor`. May leave the weight above the threshold and must be labeled as such.
- `tax_aware_review`: same math as `reduce_only` plus a mandatory tax-impact warning when average cost is available.
- Every trim plan must surface `sharesToSellExact`, `sharesToSellWholeCompliant`, `sharesToSellWholeReduceOnly`, `sharesToSellFractionalCompliant`, `estimatedPostWeightCompliant`, `estimatedPostWeightReduceOnly`, `complianceMode`, and `wouldRemainAboveThresholdIfRoundedDown`.
- UI never uses "whole-share floor" as the recommended compliance wording. Use "Whole-share compliant trim" (strict) or "Reduce-only trim" (and disclose if it leaves the position above policy threshold).

## Risk Gates and Trade Impact
- Block trades that worsen a breached exposure (`trade_worsens_breach`).
- Allow trades that reduce portfolio risk (`trade_reduces_portfolio_risk`), even if a breach exists elsewhere.
- A blanket "do not add anything new" copy is forbidden. Use: "Risk-increasing trades are blocked. Risk-reducing diversification may remain eligible if it improves concentration and passes data/risk gates."
- Required block conditions: buying more of an overweight symbol; buying more of an overweight sector; adding single-stock risk during extreme concentration; any action that depends on missing or stale prices; candidates that fail liquidity, volatility, drawdown, or history gates.

## Data Quality Taxonomy
- `freshness` values: `live`, `recent`, `stale`, `partial`, `missing`. `provider_mode` and UI labels follow timestamp + policy threshold logic, never "non-sample exists therefore live".
- `coverage` values: `complete`, `partial`, `insufficient`, `missing`.
- A `DataSourceMatrix` summarizes prices, liquidity, fundamentals, filings, macro, factors, events, IPO calendar, crypto metadata, portfolio state, and telemetry. Each entry shows provider, fallback, latest timestamp, record count, coverage, confidence, warnings, and whether it was used in the current advisor run.
- Limited-history playbook applies to IPOs, new ETFs, and crypto tokens: `<20d` watch-only, `20–63d` speculative watch, `63–252d` restricted signal with smaller size, `≥252d` full signal.
- SEC fundamentals coverage gaps mark fundamentals as `partial`, not automatic `WAIT_FOR_DATA`. Analysis only blocks when the data required for the proposed action is actually missing.

## LLM Boundary
- Model router config supports `provider`, `model`, `reasoningEffort` (`none`/`minimal`/`low`/`medium`/`high`/`xhigh`), `maxOutputTokens`, `timeoutMs`, `stream`, `purpose`, `requiresManualRun`.
- Default models: fast/specialist = `gpt-5.4-mini`, leadPM = `gpt-5.5` medium, deepCompetition = `gpt-5.5` high (manual only, never daily autopilot).
- LLM output schema is `LLMReviewOutput` (headline, executiveSummary, userExplanation, keyRisks, whyNow, whyNotAlternatives, dataLimitations, followUpQuestions, confidenceNarrative, deterministicDecisionConfirmed, conflictWithDeterministicEngine, advisoryOnlyDisclosure).
- LLM disagreement is logged as a conflict, never merged into canonical decisions.
- Streamed run events are operational lifecycle only. Streaming hidden chain-of-thought is forbidden.

## UI Copy Rules
- Always allowed: "Advisory-only · no order placed", "Risk-increasing trades are blocked", "Risk-reducing diversification may remain eligible…", "Data partial", "Limited history".
- Forbidden unless the exact verified state is true: "AI decided", "execute trade", "best predictor", "guaranteed", "will outperform", "risk-free", "Live", "Quant Checked", "AI Live", "whole-share floor".
- Provider/API errors shown in the main UI are user-safe; raw secrets and raw stack traces are never exposed.
- Local/cloud disclosure must be truthful. When AI is enabled, disclose that a compact advisor packet is sent to the configured provider.

## Verification Gates
Before completing substantive work:
- Run backend tests.
- Run frontend typecheck/build when frontend files changed.
- Run audit after dependency changes.
- For UI changes, use browser QA for the current in-app width and at least one mobile/desktop breakpoint when practical.
- Report any failing command and fix it unless blocked by missing local setup.

## Test Coverage Requirements
Substantive changes must keep or add coverage in these areas:
- Policy: preset thresholds, custom validation, crypto-disabled default, broad-ETF exemption, thematic-ETF cap.
- Trim math: exact, whole-share strict (ceil), reduce-only (floor), fractional strict, would-remain-above flag, tax warning.
- Risk gates: warning/hard buy-block/urgent review/extreme states; risk-increasing blocked vs risk-reducing allowed; stale data blocks sizing; missing price blocks action; partial fundamentals do not automatically block.
- Candidate scoring: liquidity/volatility/drawdown blockers, limited-history states, broad-ETF risk-reducing allowed, sector-worsening adds blocked.
- LLM boundary: cannot override canonical action, cannot set target weight, conflict logged, schema rejects extra canonical fields, advisory-only disclosure required.
- Sample portfolio: META extreme, NEE/RTX urgent or hard-buy-block, VST warning, CCJ fundamentals partial when SEC facts missing, no order placed, receipt contains exact trim math.
