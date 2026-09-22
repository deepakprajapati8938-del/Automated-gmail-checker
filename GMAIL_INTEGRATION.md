# GMAIL_INTEGRATION.md

## 1. Auth

OAuth 2.0, "Desktop app" or "Web application" credentials from Google Cloud
Console, run once locally via `scripts/gmail_oauth_setup.py`, which:

1. Loads `client_secret.json` (path from `GMAIL_CLIENT_SECRET_PATH`, git-ignored).
2. Runs the installed-app flow (`InstalledAppFlow.run_local_server`) with scope
   `gmail.readonly` only.
3. Persists the resulting token (access + refresh) to `GMAIL_TOKEN_PATH`
   (default `data/gmail_token.json`, git-ignored, `chmod 600`).

`app/email/gmail.py::GmailClient` loads that token on startup and refreshes
silently via the stored refresh token; if refresh fails (revoked access), it
raises a clear error asking the owner to re-run the setup script rather than
looping forever.

## 2. Detecting new mail — polling design

Phase 1 uses polling, not Gmail Push/Pub-Sub (see `ARCHITECTURE.md` §4 for why).

- Maintain `last_history_id` (persisted alongside the token, e.g.
  `data/gmail_state.json`).
- On each poll tick (`GMAIL_POLL_INTERVAL_SECONDS`, default 60):
  1. If no `last_history_id` yet (first run), call `users.messages.list` with
     `maxResults` small, take the newest message's historyId as the baseline,
     and **do not** notify on backlog — Phase 1 should not blast the user with
     every old email on first boot.
  2. Otherwise call `users.history.list(startHistoryId=last_history_id,
     historyTypes=['messageAdded'])`, paginating until no `nextPageToken`.
  3. For each added message ID, check the idempotency store
     (`ProcessedMessageStore.has_processed`); skip if already processed.
  4. Fetch full message via `users.messages.get(id=..., format='full')`.
  5. Update `last_history_id` to the response's `historyId` after a fully
     successful batch (not partially, to avoid gaps on crash).
- `history.list` can return `404` if the historyId is too old (Gmail expires
  history after ~7 days for free accounts); on `404`, fall back to step 1's
  "reset baseline" behavior and log a warning rather than crashing.

## 3. Fetching and parsing

`app/email/parser.py`:

- Walk the MIME `payload.parts` tree; prefer `text/plain`; if only `text/html`
  exists, convert with a minimal HTML-to-text pass (`app/email/parser.py::
  html_to_text`) that strips scripts/styles/tracking pixels (`<img>` with
  1x1-style dimensions or query-string tracking patterns) before extracting
  text.
- Strip excessive quoted-reply chains ("On ... wrote:", `^>` quote markers) down
  to the last ~2 quote levels — enough context for thread continuity without
  bloating every message with the entire thread history (cost optimization,
  spec §25).
- Signature stripping is best-effort (common delimiters: `-- `, `Sent from my
  iPhone`, etc.) and is not allowed to remove content before the first such
  delimiter even if detection is uncertain — false negatives (signature kept)
  are fine, false positives (real content cut) are not.
- Extract metadata directly from Gmail's parsed headers (`From`, `To`, `Cc`,
  `Subject`, `Date`) rather than re-parsing raw RFC822 text.
- Attachments: record `filename`, `mimeType`, `size` only (`attachment_metadata`
  jsonb) — attachment **content** is never fetched or sent to the AI provider in
  Phase 1/2 (out of scope; a future phase could add explicit "summarize this PDF"
  on demand).

## 4. Deterministic pre-filter (cost optimization, spec §25)

Before any AI call, `app/services/triage.py::should_skip_ai()` short-circuits on:

- Sender in a user-maintained "always ignore" list (from `ignore_sender`
  feedback, Phase 5) or a small built-in noreply/bulk-mail heuristic
  (`List-Unsubscribe` header present **and** no direct `To:` match to the user's
  own address, e.g. bulk marketing).
- Gmail label `CATEGORY_PROMOTIONS` or `CATEGORY_SOCIAL` from Gmail's own
  classification, unless the sender has an `always_important` feedback flag.
- Empty/near-empty body with no subject signal.

Everything else goes to the AI triage call. This is intentionally conservative
(biased toward calling the AI) since false skips are worse than a slightly
higher AI bill for a personal-scale inbox.

## 5. Scopes

Phase 1: `gmail.readonly` only. Anything beyond read (sending mail, modifying
labels/marking read, watch/push) is out of scope for the MVP and would require
an explicit scope change documented here and re-consent from the owner.

## 6. Rate limits / quotas

Gmail API free quota (per-user, per-100 seconds and per-day limits) is far above
what a single personal inbox polled every 60s needs. `app/email/gmail.py` wraps
calls with exponential backoff on `429`/`5xx` and logs `gmail_errors` (metric,
spec §32) without ever logging tokens or bodies.
