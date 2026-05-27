# Local Robo Portfolio Manager

A local-first real-portfolio research command center for aggressive, risk-managed long-term investing. The app tracks your imported real holdings and produces decision support only: it does not place brokerage trades.

## What is included

- React + TypeScript frontend for dashboards, opportunities, risk, backtests, recommendations, research memos, imports, and settings.
- FastAPI backend with SQLite persistence.
- Real holdings import from brokerage CSV or pasted CSV rows.
- Deterministic sample market, macro, and fundamental data so the analytics work immediately offline.
- Optional adapters for Alpaca, FRED, SEC EDGAR, and Alpha Vantage configured through `.env`.
- Source-ranked data refresh: Alpaca latest bars are preferred for live/recent prices, Alpha Vantage is fallback daily coverage, FRED refreshes macro regime inputs, and SEC EDGAR enriches fundamentals only when a real contact User-Agent is configured.
- Quant-led recommendation engine with risk gates. Research memos are rules-based unless `OPENAI_API_KEY` is configured, in which case the app calls the OpenAI Responses API and logs model/token usage.
- Portfolio-level Advisor Intelligence Packet with tool inventory, holdings, risk rules, provider freshness, macro regime, quant diagnostics, strategy sleeves, backtests, and action items.
- Senior-PM advisor review that can use OpenAI for strict JSON portfolio critique, while backend risk gates block any AI-approved idea that fails quant constraints.
- Local Connections workflow for OpenAI, Alpaca, FRED, Alpha Vantage, and SEC identity. Secrets are stored in ignored local app data and only masked metadata is returned to the UI.
- Quant diagnostics that show data coverage, feature generation health, risk-gate logging, and backtest readiness.
- Unit, integration, smoke, and acceptance-oriented tests.

## Quick start

Backend:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Frontend:

```bash
cd frontend
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

Open `http://127.0.0.1:5173`.

## Environment

Copy `.env.example` to `.env` inside `backend/` to configure optional providers.

Without keys, the app uses deterministic local sample data and labels the dashboard as `Sample fallback`. With keys, refresh jobs prefer live/recent provider records before analytics run and the dashboard shows provider state, source counts, and data-source diagnostics.

Provider priority:

1. Alpaca: preferred live/recent latest-minute equity bars.
2. FRED: macro series for rates, inflation, unemployment, and Treasury yields.
3. SEC EDGAR: company facts and fundamentals when `SEC_USER_AGENT` contains real contact info.
4. Alpha Vantage: fallback daily adjusted prices, capped by `ALPHA_VANTAGE_REFRESH_LIMIT` to avoid budget/rate surprises.

## AI Advisor

No memo is labeled as AI-generated unless a real model call succeeds.

- `OPENAI_API_KEY` enables real model-generated memos through the OpenAI Responses API.
- You can also connect the key from Settings with `Connections`; the key is stored locally for this app and never returned by the API.
- The app uses a fixed cost-conscious Competition Advisor profile: `gpt-5-mini`, medium reasoning, quant-gated competition instructions, an 800 token memo cap, and a 1,200 token portfolio-review cap.
- The Connections tab shows connection state, run/test actions, token usage, and a collapsed read-only technical audit. Model, reasoning, personality, custom instructions, and token caps are not user-editable in the normal UI.
- Legacy saved AI tuning values and compatibility env fields are ignored by the advisor runtime so old choices cannot silently weaken the optimized profile.
- Every successful model call records input, output, and total tokens in SQLite.
- If no key is configured, or if a model call fails, the app uses an explicitly labeled rules-based quant memo.

## Advisor Review

The portfolio-level advisor review is built from `/api/advisor/packet` and run through `/api/advisor/review` or the normal advisor cycle. The model sees the quant packet and tool inventory, but the backend post-processes the response so failed risk-gate ideas cannot appear as approved actions.

## Real Holdings Import

The holdings CSV importer accepts headers such as:

```csv
symbol,quantity,avg_cost
AAPL,12,185.40
SPY,20,520.00
CASH,2500,2500
```

It also recognizes common brokerage-style columns such as `ticker`, `shares`, `cost_basis`, `market_value`, and `current_value`.

## Safety boundary

This project is research and decision-support software for your own review. Recommendations are not financial advice, and v1 never sends orders to a brokerage.
