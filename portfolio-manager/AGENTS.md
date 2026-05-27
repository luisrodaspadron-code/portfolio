# Signal Prime Engineering Contract

## Repo Shape
- Frontend: React + TypeScript in `frontend/src`; build commands run from `frontend`.
- Backend: FastAPI + SQLite in `backend/app`; tests run from `backend`.
- Provider adapters live in `backend/app/providers`.
- Portfolio, risk, advisor, AI, and connection services live in `backend/app/services`.

## Commands
- Backend tests: `cd backend && .venv/bin/pytest -q`
- Frontend typecheck: `cd frontend && npm test`
- Frontend build: `cd frontend && npm run build`
- Frontend audit: `cd frontend && npm audit --audit-level=high`
- Local backend: `cd backend && .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`
- Local frontend: `cd frontend && npm run dev`

## Non-Negotiable Architecture
- LLMs may explain, summarize, challenge, and produce narrative memos.
- LLMs must not calculate portfolio weights, enforce risk caps, size actions, detect hard rule breaches, or produce the final executable decision object.
- Deterministic backend code is the source of truth for math, sizing, ranking, risk gates, data freshness, and eligibility.
- The frontend should render from canonical backend decision/receipt state rather than recomputing financial decisions from scattered local state.
- No UI may imply real broker execution while `real_money_trading_enabled` is false.

## Product Rules
- Every action is advisory-only unless a future broker execution module is explicitly implemented and enabled.
- Use precise labels: `eligible`, `blocked`, `wait for data`, `suggested trim plan`, `estimated`, `no order placed`.
- Avoid claims like guaranteed returns, certain outperformance, risk-free, or execute trade.
- Provider/API errors shown in the main UI must be user-safe and must not expose raw secrets or scary raw stack traces.

## Verification Gates
Before completing substantive work:
- Run backend tests.
- Run frontend typecheck/build when frontend files changed.
- Run audit after dependency changes.
- For UI changes, use browser QA for the current in-app width and at least one mobile/desktop breakpoint when practical.
- Report any failing command and fix it unless blocked by missing local setup.

