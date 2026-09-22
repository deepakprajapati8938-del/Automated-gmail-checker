# TELEGRAM_AGENT.md

## 1. Role of Telegram in this system

Telegram is the entire user interface. It carries three kinds of traffic:

1. **Outbound notifications** — agent → user, pushed proactively.
2. **Commands** — `/inbox`, `/important`, `/today`, `/deadlines`, `/actions`,
   `/digest`, `/settings`, `/start`, `/help`. Thin wrappers that call the same
   services natural language uses.
2. **Free-text natural language** — routed to the conversational agent
   (Phase 3+; Phase 1 replies to free text with a short "not wired up yet, try
   /help" message so the bot is never silent).
3. **Inline button callbacks** — feedback (`👍/👎/🔕/⭐`) and notification
   drill-down (`Read Summary` / `Open Email` / `Why Important`).

## 2. Message flow (Phase 1)

```
Telegram update
   → app/security/auth.is_authorized()   (reject unknown user IDs immediately)
   → app/telegram/handlers.py            (route: command vs text vs callback)
   → command → app/telegram/commands.py  → app/services/*  → format → send
   → text    → Phase 1: static help reply; Phase 3+: app/agents/email_agent.py
   → callback→ app/telegram/handlers.py::on_callback → app/services/personalization (feedback) / notifications (drill-down)
```

Commands **never** contain their own business logic — they call the exact same
service functions the natural-language agent will call in Phase 3
(`app/services/*`), so behavior can't drift between the two entry points.

## 3. Notification format (Phase 1)

```
🔴 IMPORTANT EMAIL

📩 <subject>

<summary>

Why this matters:
<reason>

Action:
<action items, or "No action needed">
```

Emoji severity: 🔴 = 9–10, 🟠 = 7–8, 🟡 = 5–6 (digest-only, not sent immediately).
Buttons (Phase 1 minimal set): `Why Important`, `👍`, `👎`. `Open Email` links to
`https://mail.google.com/mail/u/0/#inbox/<thread_id>`. `Read Summary` / full
thread retrieval buttons arrive with Phase 3 once thread retrieval tools exist.

## 4. Conversation memory (Phase 3, designed now)

Per spec §17, the bot must not replay full Telegram history to the LLM. Design:

- `telegram_conversations.last_messages`: ring buffer of the last ~6 turns
  (verbatim), enough for pronoun resolution ("what about XYZ" / "what do I need
  to prepare").
- `telegram_conversations.summary`: a rolling LLM-generated summary of everything
  older than the ring buffer, regenerated periodically (e.g. every 6 new turns)
  rather than on every message, to save tokens/cost.
- Each agent call receives: `[system prompt] + [rolling summary] + [ring buffer]
  + [new user message]` — never the raw full history.
- Memory is per-user (trivial here, single user) and can be reset with
  `/settings` → "Clear conversation memory".

## 5. Tool-calling loop (Phase 3, designed now)

The agent (`app/agents/email_agent.py`) is a bounded loop:

1. Build prompt: system instructions + conversation memory + user message.
2. Call `AIProvider.complete_structured()` asking for either a direct answer or
   a tool call from the fixed tool list (spec §7), never free-form Telegram
   sends or writes.
3. If a tool call is returned, execute it against `app/retrieval` /
   `app/database/repositories` (never the raw DB from inside the agent), append
   the tool result to the prompt, and loop — capped at `MAX_TOOL_HOPS` (default
   4) to bound cost/latency.
4. If the model returns "no evidence found", the agent replies verbatim with the
   spec's fallback: *"I couldn't find a reliable answer in your emails."* — it
   is never allowed to answer from parametric knowledge for factual mailbox
   questions.
5. Final answers that cite an email always include the subject + received date
   as the "Source:" line (spec §16), pulled from the tool result, not invented
   by the model.

## 6. Digest and reminder jobs (Phase 4, designed now)

A scheduler (APScheduler, in-process — no extra infra) runs:

- Daily digest at a user-configurable time (`/settings`), calling the same
  `app/services/digest.py::build_digest()` that `/digest` calls on demand.
- Deadline reminder sweep (e.g. hourly) via `app/services/deadlines.py`.
- Follow-up-detection sweep (e.g. daily) checking sent mail with no reply after
  N days (requires `gmail.readonly` on the Sent folder — no new scope needed).

## 7. Failure behavior

- Gmail unavailable → poller logs + backs off exponentially; bot still answers
  from stored memory (Phase 2+) and tells the user ingestion is delayed if asked.
- AI provider unavailable → triage falls back to a deterministic rule (e.g. flag
  as "needs review", never silently drop) and the Q&A agent replies with a
  graceful "AI is temporarily unavailable" rather than crashing the bot process.
- Telegram unavailable → notifications queue and retry with backoff; never
  silently dropped (surfaced via `notifications_sent` / `telegram_errors`
  metrics, §32 of the spec).
