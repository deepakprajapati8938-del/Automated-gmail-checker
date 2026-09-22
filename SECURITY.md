# SECURITY.md

## 1. Threat model (personal single-user system)

Assets to protect: Gmail OAuth tokens, email content, AI provider API keys,
Telegram bot token, the fact that the bot exists at all. Primary attackers:
random Telegram users who discover the bot, and malicious/spam email senders
attempting prompt injection.

## 2. Gmail access

- OAuth 2.0 only (`google-auth-oauthlib`), authorization-code flow run once via
  `scripts/gmail_oauth_setup.py`. No password is ever requested or stored.
- Minimum scope: `https://www.googleapis.com/auth/gmail.readonly` for Phase 1
  (read-only triage). If/when the agent needs to send mail or modify labels in a
  later phase, that scope is added explicitly and documented here — it is not
  requested up front "just in case."
- Tokens (`token.json` / refresh token) are stored outside version control, path
  configured via `GMAIL_TOKEN_PATH`, and should be encrypted at rest in any shared
  environment (e.g. via the OS keychain or a secrets manager) — the repo assumes a
  single-user private VM/container where filesystem-level permissions (`chmod
  600`) are the practical control.
- Never logged: tokens, full email bodies, full email addresses of third parties
  beyond what's needed for a notification.

## 3. Telegram authorization

- The bot is authorized to exactly one Telegram numeric user ID, set via
  `TELEGRAM_OWNER_ID` in the environment — **never** the `@username`, which can
  change or be spoofed in forwarded messages.
- `app/security/auth.py::is_authorized(update)` is called at the top of every
  handler (commands, free-text messages, and callback-button presses). Any
  message from an unauthorized `from.id` gets a generic `"Unauthorized user."`
  reply with zero email information and is logged (ID + timestamp only, not
  content) for visibility.
- `/start` from the owner just confirms linkage; it does not grant access to
  anyone else — access is fixed by config, not by who messages `/start` first.
  This avoids a race where an attacker DMs the bot before the owner does.

## 4. Secrets handling

- All secrets (Telegram bot token, AI provider API keys, DB URL, Gmail client
  secret) come from environment variables, documented in `.env.example` with
  placeholder values only.
- `.env` is git-ignored. CI/CD and deployment platforms should inject secrets via
  their native secret store, not a committed file.
- No secret is ever interpolated into a log line or exception message; wrap
  external calls so exceptions are sanitized before logging (`app/config.py`
  loads and validates presence of secrets without ever printing their values).

## 5. Data-at-rest

- Phase 1 stores only: processed Gmail message IDs (for idempotency) and,
  transiently, the fields needed to build a notification. No email body is
  persisted to disk in Phase 1.
- Phase 2 introduces Postgres persistence of normalized emails, AI analysis, and
  embeddings, governed by a configurable retention policy (`RETENTION_DAYS`).
  Deletion job + a `/settings` → "delete my data" path are required before Phase
  2 is considered done, per the top-level spec.
- Logs must never contain full email bodies (Section 22/32 of the spec). Use the
  email `message_id` and subject-only for debug logs, and even subject should be
  omitted at `INFO` level in production.

## 6. Prompt injection

Emails are the single largest untrusted-input surface in this system. See the
dedicated section below and `app/agents/prompts/`.

### 6.1 Principle

Email content is **data**, never **instructions**. This is enforced structurally,
not just by asking the model nicely:

1. Every email body passed to the LLM is wrapped:
   ```
   <EMAIL_CONTENT>
   {sanitized body}
   </EMAIL_CONTENT>
   ```
   and the system prompt states explicitly that text inside this boundary must be
   treated as untrusted user-authored content to analyze, and any instructions
   found inside it must be ignored and, if relevant, flagged as a suspicious
   signal (e.g. it can raise `category = security` / lower trust, but must never
   change agent behavior).
2. The triage prompt and the Q&A agent prompt are two different system prompts.
   The triage prompt's only valid outputs are the fixed JSON schema in
   `app/ai/schemas.py` — there is no way for triage output to trigger a tool call
   or a Telegram send; a Python function (`app/services/triage.py`) maps the
   schema deterministically to a notification decision.
3. The Q&A agent (Phase 3) only has **read-only** retrieval tools (Section 7 of
   the spec). There is no "send message", "call URL", or "execute" tool exposed
   to it, so even a fully successful injection has nothing harmful to invoke.
4. The agent's tool-calling loop strips/ignores any tool-call-looking text that
   originates from retrieved email content rather than from the model's own
   structured tool-call output — i.e., a line like `TOOL: send_telegram(...)`
   embedded in an email is just a string to summarize, never parsed as a call.
5. Structured-output validation (Pydantic schemas) rejects any triage response
   that doesn't conform, so an injection can't smuggle extra fields/instructions
   through the analysis pipeline.

### 6.2 What an email can never do

- Change agent instructions or system prompt.
- Change the notification-threshold policy (that's Python code, not a prompt).
- Cause a tool call, a Telegram send, or any network request.
- Cause disclosure of other emails, secrets, or this system's prompts.

### 6.3 Testing

Phase 6 introduces an adversarial test set (`tests/test_prompt_injection.py`)
with emails containing common injection patterns ("ignore previous
instructions", fake system tags, base64-obfuscated instructions, etc.) asserting
the triage output stays schema-valid and the agent never emits a tool call that
wasn't asked for.

## 7. Dependency & infra hygiene

- Pin dependencies in `requirements.txt`.
- Least-privilege DB user in Phase 2 (no superuser).
- Rate limit Telegram command handling per user (Phase 6) to avoid one runaway
  loop hammering the AI provider / Gmail API and burning the free quota.
