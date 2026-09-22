# DEPLOYMENT.md

## 1. Local (recommended for Phase 1 while testing)

```bash
cp .env.example .env      # fill in values
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scripts/gmail_oauth_setup.py     # one-time Gmail consent
python -m app.main
```

Runs the Gmail poller and the Telegram bot's long-polling loop in one process.
No inbound port needed, so no firewall/router configuration required.

## 2. Free-tier cloud target

| Component | Free target | Notes |
|---|---|---|
| Compute | Fly.io free allowance / Railway free tier / Render free web-less "background worker" / a home machine or Raspberry Pi | Needs to run a long-lived process (Telegram long polling + Gmail poll loop), not a request/response function — avoid classic "serverless function" platforms with execution-time limits for Phase 1. |
| Database (Phase 2+) | Supabase free Postgres (has pgvector) or Neon free tier | Both give pgvector support at no cost tier. Note: Free tier Postgres databases often sleep; the agent handles this by retrying connection at startup. |
| Telegram Bot API | Free, no limits relevant here | |
| Gmail API | Free quota, far above single-inbox polling needs | |
| AI inference | Provider free tier (e.g. Gemini free tier) | `AI_PROVIDER`/`AI_MODEL` env vars select this. **Warning**: Free tiers often have rate limits (e.g. 15 RPM). The agent may drop evaluation or get rate limited on bulk polling; backoffs are implemented. |
| Secrets | Platform's built-in secret/env store | Never commit `.env`. |

**Anything that can become paid must be called out explicitly:**
- Gmail/Telegram APIs: free at this scale, no action needed.
- AI provider: free tiers usually have daily/rate caps; exceeding them means
  either waiting or paying — the cost-optimization pipeline (spec §25, deterministic
  pre-filter, caching) is what keeps a personal inbox inside free-tier caps.
- Postgres free tiers (Supabase/Neon) have storage/row caps; the retention policy
  (`DATABASE.md` §3) exists specifically to keep it under those caps indefinitely.
- Compute free tiers may sleep idle workers or cap monthly hours — a background
  worker that's not receiving HTTP requests should not "sleep" the way a web
  free-tier dyno might; pick the platform's "worker"/"background job" product,
  not its "web service" product, or self-host on a VM.

## 3. Docker

`Dockerfile` builds a single image running `python -m app.main`.
`docker-compose.yml` (Phase 2+) adds a `postgres` service with the `pgvector`
image for local development that mirrors the cloud DB. Compose is optional for
Phase 1 (no DB dependency yet).

## 4. Config / secrets

All configuration is environment variables, loaded and validated once at
startup in `app/config.py` (fails fast with a clear message if a required
variable is missing, rather than failing deep in some handler later).

## 5. Zero-downtime-ish updates

Single-process, single-user: acceptable to do a simple stop/redeploy/start for
the MVP. The Gmail poller re-derives `last_history_id` from persisted state, and
Telegram long-polling resumes cleanly — no message loss beyond normal restart
downtime. Phase 6 can add a graceful-shutdown handler.

## 6. What NOT to deploy (per spec)

No web dashboard, no public HTTP endpoint required for Phase 1–3. If Phase 2's
Postgres provider requires an admin UI, use the provider's own dashboard — don't
build one.
