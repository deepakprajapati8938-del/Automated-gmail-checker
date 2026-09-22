# IMPLEMENTATION_PLAN.md

## 0. Repository state at start

Empty repository — no prior code, no dependencies, no conflicts to resolve. This
plan and the accompanying docs (`ARCHITECTURE.md`, `SECURITY.md`, `DATABASE.md`,
`TELEGRAM_AGENT.md`, `GMAIL_INTEGRATION.md`, `DEPLOYMENT.md`) were written before
any implementation, per the spec's instruction to inspect/design first.

## 1. Phase status

- [x] **Phase 1 — Telegram + Gmail MVP**: implemented in this change.
- [x] Phase 2 — Email Memory (Postgres + pgvector, hybrid search)
- [x] Phase 3 — Conversational Telegram Agent (tool-calling loop, memory)
- [x] Phase 4 — Intelligence (deadlines, digests, follow-ups, reminders)
- [x] Phase 5 — Personalization (feedback-driven ranking)
- [ ] Phase 6 — Production hardening (tests, security audit, monitoring)

Each later phase should be a separate change on top of this one; do not start a
phase until the previous one's "definition of done" slice is manually verified
end-to-end.

## 2. Phase 1 scope (what was actually built)

End-to-end flow implemented:

```
Gmail (poll) → parser/processor → idempotency check → deterministic pre-filter
   → AI triage (provider-abstracted, structured output) → notification policy
   → Telegram notification (with Why-Important / 👍 / 👎 buttons)
```

Included:
- `app/email/gmail.py` — OAuth-based Gmail client, polling via `history.list`
  with safe first-run baseline behavior (see `GMAIL_INTEGRATION.md`).
- `app/email/parser.py` — MIME walking, HTML→text, quote/signature trimming,
  metadata extraction.
- `app/email/processor.py` — orchestrates parse → normalize → idempotency →
  pre-filter → triage → notify.
- `app/ai/base.py`, `app/ai/schemas.py`, `app/ai/providers/*` — provider
  abstraction with OpenAI, Gemini, Groq, and a local/OpenAI-compatible
  implementation; selected via `AI_PROVIDER`/`AI_MODEL`.
- `app/services/triage.py` — deterministic notification-tier enforcement on top
  of the AI's recommended score (spec §12), plus the deterministic pre-filter
  (spec §25).
- `app/telegram/*` — bot bootstrap, `/start /help /inbox /important /today
  /deadlines /actions /digest /settings` command shells (several return an
  honest "not available until Phase N" message rather than fake data — see
  §3 below), free-text fallback message, inline-button callback handling for
  `Why Important` / `👍` / `👎` (feedback is recorded even though Phase 5's
  ranking use of it doesn't exist yet).
- `app/security/auth.py` — numeric Telegram ID allow-list enforced on every
  update type.
- `app/database/repositories/processed_messages.py` — SQLite-backed idempotency
  + minimal feedback storage, written to the interface Phase 2 will replace.
- `app/config.py`, `.env.example`, `requirements.txt`, `Dockerfile`,
  `app/main.py` wiring both loops together with graceful shutdown on
  SIGINT/SIGTERM.

### 2.1 Honest command behavior in Phase 1

Commands that depend on stored/searchable memory (`/inbox`, `/important`,
`/today`, `/deadlines`, `/actions`, `/digest`) are implemented against the same
lightweight SQLite feedback/notification-log store, so they show **real** data
from Phase 1's own run (recent notifications actually sent, real feedback
recorded) rather than mocked content — but they explicitly do not do semantic
search or historical backfill, since that's Phase 2/3 work. Each of these
commands' help text says so plainly instead of pretending to be complete.

## 3. Explicitly deferred (per spec §33/§35 — do not build now)

Web dashboard, Outlook/Calendar/Slack/Discord/Drive integration, task-management
sync, voice interface, local-LLM-only mode as default, mobile app, multi-user
SaaS, Postgres/pgvector, hybrid retrieval, tool-calling agent loop, deadline/
follow-up detection jobs, digest scheduler, personalization/adaptive ranking,
full test suite, rate limiting, monitoring dashboards.

## 4. How to verify Phase 1 end-to-end

1. Fill `.env` from `.env.example`.
2. Run `python scripts/gmail_oauth_setup.py` once, complete the Google consent
   screen for a Gmail account you control.
3. Message the bot `/start` from the Telegram account whose numeric ID matches
   `TELEGRAM_OWNER_ID`.
4. Run `python -m app.main`.
5. Send yourself (or receive) a new, clearly important-looking test email
   (e.g. subject "Interview Confirmation — tomorrow 10am").
6. Within `GMAIL_POLL_INTERVAL_SECONDS`, confirm a Telegram notification arrives
   with subject/summary/reason/action and working `Why Important`/👍/👎 buttons.
7. Send a low-value test email (e.g. a promo-looking message) and confirm no
   notification is sent (check logs for `notifications_suppressed`).
8. Message the bot from a *different* Telegram account and confirm the reply is
   exactly `"Unauthorized user."` with no email data.
9. Kill and restart the process; confirm the same email is not re-notified
   (idempotency) and polling resumes from the persisted `last_history_id`.

## 5. Entry point for Phase 2

Phase 2 starts by adding `app/database/models.py` (SQLAlchemy) + Alembic
migrations matching `DATABASE.md`, standing up Postgres (local docker-compose +
free-tier target), moving `ProcessedMessageStore`'s SQLite implementation to a
Postgres-backed one behind the same interface, then adding embeddings +
`app/retrieval/`. No Phase 1 module's public interface should need to change for
this — that's the point of the layering in `ARCHITECTURE.md`.
