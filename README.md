# Telegram AI Email Agent

A personal AI email intelligence agent that watches one Gmail inbox, triages
new mail with an LLM, and talks to you entirely through Telegram — no web
dashboard. See `PROJECT_SPEC.md` for the full product spec and
`IMPLEMENTATION_PLAN.md` for what's built vs. deferred.

**Status: Phase 1 (Telegram + Gmail MVP) is implemented and tested.**
Phases 2–6 (email memory, conversational agent, deadlines/digests,
personalization, production hardening) are documented but intentionally not
yet built — see `IMPLEMENTATION_PLAN.md`.

## Docs

| File | Covers |
|---|---|
| `ARCHITECTURE.md` | Layering, data flow, guardrails baked into the code |
| `SECURITY.md` | OAuth, secrets, Telegram authorization, prompt-injection defenses |
| `DATABASE.md` | Full Phase 2 schema + what Phase 1 uses instead |
| `TELEGRAM_AGENT.md` | Bot message flow, notification format, future conversational design |
| `GMAIL_INTEGRATION.md` | OAuth setup, polling design, parsing rules, cost pre-filter |
| `DEPLOYMENT.md` | Local run, free-tier cloud targets, Docker |
| `IMPLEMENTATION_PLAN.md` | Phase-by-phase status and how to verify Phase 1 end-to-end |

## Quickstart (Phase 1)

```bash
cp .env.example .env                 # fill in values, see comments in the file
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# One-time Gmail consent (opens a browser, asks for read-only access only)
python scripts/gmail_oauth_setup.py

python -m app.main
```

Then message your bot on Telegram with `/start` from the account whose
numeric ID you set as `TELEGRAM_OWNER_ID` (get it from @userinfobot — never
use your @username).

## What you need before running it

1. A Telegram bot token from [@BotFather](https://t.me/BotFather).
2. Your own numeric Telegram user ID (from [@userinfobot](https://t.me/userinfobot)).
3. A Google Cloud project with the Gmail API enabled and an OAuth **Desktop
   app** client (`client_secret.json`), per `GMAIL_INTEGRATION.md` §1.
4. An API key for whichever `AI_PROVIDER` you set in `.env` (OpenAI, Gemini,
   or Groq — or point `AI_PROVIDER=local` at a local OpenAI-compatible server
   like Ollama and skip the key).

## Running the tests

```bash
pip install pytest
python -m pytest tests/ -v
```

## Project layout

See `ARCHITECTURE.md` §3 for the reasoning behind the layering; the directory
tree itself is in `IMPLEMENTATION_PLAN.md` / the original spec. Modules for
Phases 2–5 exist as stubs (`raise NotImplementedError(...)`) with a docstring
pointing at which phase implements them, so the intended shape of the whole
system is visible without pretending unbuilt features work.

## Security notes

Read `SECURITY.md` before deploying anywhere multi-tenant or internet-facing.
Highlights: Gmail access is OAuth-only and read-only; only one Telegram
numeric user ID is ever authorized; email content is always treated as
untrusted data behind an explicit `<EMAIL_CONTENT>` boundary and never as
instructions, so a malicious email can't hijack the agent, exfiltrate other
emails, or trigger a Telegram send on its own.
