# ARCHITECTURE.md

## 1. Purpose

A personal, single-user AI agent that watches one Gmail inbox, triages incoming
mail with an LLM, and exposes everything — notifications, search, Q&A — through a
single Telegram bot. No web UI in the MVP.

## 2. High-level flow

```
Gmail API (poll) --> Ingestion --> Processor (clean/normalize) --> Idempotency check
      --> Deterministic pre-filter --> AI Triage (structured output)
      --> Notification Policy (backend-enforced) --> Telegram notification
      --> Persistence (raw + structured + embeddings)  [Phase 2]
      --> Hybrid retrieval + Tool-using agent  [Phase 3]
      --> Deadlines / follow-ups / digests  [Phase 4]
      --> Feedback-driven ranking  [Phase 5]
```

## 3. Layers (clean architecture)

- **`app/email/`** — Gmail integration, parsing, normalization. Knows nothing about
  Telegram or the LLM.
- **`app/ai/`** — Provider-agnostic LLM access (`AIProvider` interface),
  structured-output schemas, embeddings. Knows nothing about Gmail or Telegram.
- **`app/agents/`** — The reasoning layer. Combines AI + tools to answer questions
  or triage emails. Never talks to Gmail or Telegram directly — only through
  tools/services.
- **`app/telegram/`** — Bot wiring, command handlers, notification formatting/
  sending, inline button callbacks. Talks to `app/agents` and `app/services`, never
  directly to `app/email` or the database.
- **`app/services/`** — Business logic that spans layers: triage orchestration,
  deadline extraction, digest generation, personalization/feedback rules. This is
  where notification-threshold policy is enforced (never in the LLM or in
  `app/telegram`).
- **`app/database/`** — Models + repositories (Phase 2+). Only repositories are
  used by services; nobody writes raw SQL outside `app/database/repositories/`.
- **`app/security/`** — Telegram user authorization, secret handling helpers.
- **`app/retrieval/`** — Hybrid (semantic + keyword + metadata) search (Phase 2/3).

Dependency direction: `telegram/agents/services` → `ai` and `email` and
`database` interfaces. Nothing depends "upward" into `telegram`.

## 4. Why polling, not Gmail push (Pub/Sub), for Phase 1

Gmail's push notifications (`users.watch` + Cloud Pub/Sub) require a public HTTPS
endpoint and a paid/verified Google Cloud project with Pub/Sub, and add a second
moving part (webhook receiver) to secure. For a free, single-user MVP,
`users.history.list` polling every N seconds/minutes is simpler, has no inbound
attack surface, needs no public URL, and is inside Gmail API's free quota. The
`GmailClient` interface is written so it can be swapped for a push-based
implementation later without touching the rest of the app (see
`GMAIL_INTEGRATION.md`).

## 5. Idempotency

Every Gmail `message_id` is checked against a processed-message store before any
AI call or Telegram send. Phase 1 uses a local JSON/SQLite-backed store
(`app/database/repositories/processed_messages.py`); Phase 2 replaces the backing
store with the Postgres `email_messages` table without changing the interface.

## 6. AI provider abstraction

All LLM access goes through `app/ai/base.py::AIProvider`. Concrete providers
(OpenAI, Gemini, Groq, Cloudflare Workers AI, a local/OpenAI-compatible server)
implement `complete()` and `complete_structured()`. Selection is via
`AI_PROVIDER` / `AI_MODEL` env vars, resolved once in `app/config.py`. No other
module imports a provider SDK directly.

## 7. Guardrails baked into the architecture (not just prompts)

- The LLM only ever *recommends* an importance score / category; `app/services/
  triage.py` enforces the notification-threshold table from the spec in code.
- The LLM never gets a "send_telegram_message" tool. Tools exposed to the
  reasoning agent (`app/agents/email_agent.py`) are all **read-only** retrieval
  tools (Section 7 of the spec); Telegram sends are always issued by
  `app/telegram/notifications.py` in response to a structured decision, never by
  the LLM directly.
- Email bodies are wrapped in explicit `<EMAIL_CONTENT>` boundaries and the system
  prompt states plainly that anything inside is data, never instructions. See
  `SECURITY.md` §Prompt Injection.
- Telegram handlers reject any update whose numeric `from.id` isn't the configured
  owner ID before any other processing happens (`app/security/auth.py`).

## 8. Phase-by-phase code footprint

| Phase | New/changed modules |
|---|---|
| 1 | `app/email/gmail.py`, `parser.py`, `processor.py`; `app/ai/*`; `app/services/triage.py`; `app/telegram/*`; `app/security/auth.py`; local idempotency store |
| 2 | `app/database/*` (Postgres + pgvector), embeddings, hybrid search skeleton |
| 3 | `app/agents/*`, `app/retrieval/*`, tool-calling loop, conversation memory |
| 4 | `app/services/deadlines.py`, `digest.py`, follow-up detection, scheduler jobs |
| 5 | `app/services/personalization.py`, feedback table, adaptive thresholds |
| 6 | tests/, monitoring, rate limiting, deployment hardening |

## 9. Deployment shape

Single process for Phase 1: one Python service running (a) an async Gmail poller
loop and (b) the Telegram bot's long-polling loop, in the same event loop
(`app/main.py`). No inbound webhook, no public port required, so it runs equally
well on a free VM, a container platform's free tier, or a laptop. See
`DEPLOYMENT.md`.
