# DATABASE.md

> Phase 1 does **not** require Postgres — see §5. This document specifies the
> full schema introduced in Phase 2 so the Phase 1 idempotency store can be
> written against a compatible interface from day one.

## 1. Engine

PostgreSQL + `pgvector` extension (for `email_embeddings`). Free tier target:
Supabase, Neon, or Railway's Postgres free tier — see `DEPLOYMENT.md`.

Migrations via **Alembic**. The schema is never created dynamically at runtime;
`migrations/` holds the versioned DDL.

## 2. Tables

### `users`
Single-row in practice (personal system), but modeled properly for future
multi-user support.

| column | type | notes |
|---|---|---|
| id | uuid pk | |
| telegram_user_id | bigint unique | the only authorization key, never username |
| email_address | text | the Gmail address being monitored |
| timezone | text | for digest scheduling |
| created_at | timestamptz | |

### `email_messages`
Normalized raw memory.

| column | type | notes |
|---|---|---|
| id | uuid pk | |
| user_id | uuid fk → users | |
| gmail_message_id | text unique not null | **idempotency key** |
| thread_id | text | |
| sender | text | |
| recipients | text[] | |
| cc | text[] | |
| subject | text | |
| body_text | text | cleaned, HTML stripped |
| snippet | text | |
| received_at | timestamptz | |
| labels | text[] | |
| has_attachments | boolean | |
| attachment_metadata | jsonb | filenames/mime/size only, never content |
| created_at | timestamptz | ingestion time |

Index: unique on `gmail_message_id`; btree on `(user_id, received_at desc)`;
btree on `thread_id`.

### `email_analysis`
Structured memory / AI output, one row per analyzed email.

| column | type | notes |
|---|---|---|
| id | uuid pk | |
| email_id | uuid fk → email_messages | |
| importance_score | smallint | 0–10, spec §12 |
| urgency | text | low/medium/high |
| category | text | see configurable category list |
| requires_action | boolean | |
| summary | text | |
| reason | text | why it matters — shown in "Why important" button |
| deadline | timestamptz nullable | |
| action_items | text[] | |
| entities | text[] | |
| confidence | numeric(3,2) | |
| ai_provider | text | which provider/model produced this |
| notified | boolean | whether backend policy sent a Telegram notification |
| notification_tier | text | none/digest/notify/immediate, per spec §12 |
| created_at | timestamptz | |

### `email_embeddings`
Semantic memory.

| column | type | notes |
|---|---|---|
| id | uuid pk | |
| email_id | uuid fk → email_messages | |
| embedding | vector(N) | pgvector; N depends on embedding model |
| model | text | embedding model name, for cache invalidation on model change |
| created_at | timestamptz | |

Index: `ivfflat`/`hnsw` on `embedding` (pgvector).

### `feedback`
| column | type | notes |
|---|---|---|
| id | uuid pk | |
| email_id | uuid fk → email_messages | |
| feedback_type | text | important / not_important / ignore_sender / always_important |
| created_at | timestamptz | |

### `extracted_events`
Normalized deadlines/meetings/interviews pulled out of `email_analysis` for fast
range queries (avoids re-parsing text for every "what's due this week" question).

| column | type | notes |
|---|---|---|
| id | uuid pk | |
| email_id | uuid fk → email_messages | |
| event_type | text | deadline/interview/meeting/application |
| title | text | |
| event_time | timestamptz | |
| created_at | timestamptz | |

### `telegram_conversations`
Short-term conversational memory (spec §17) — summarized, not raw transcript.

| column | type | notes |
|---|---|---|
| id | uuid pk | |
| user_id | uuid fk → users | |
| summary | text | rolling summary of the conversation so far |
| last_messages | jsonb | small ring buffer (e.g. last 6 turns) used alongside the summary |
| updated_at | timestamptz | |

### `agent_messages`
Audit log of agent Q&A turns (for debugging/evaluation, not full email content).

| column | type | notes |
|---|---|---|
| id | uuid pk | |
| user_id | uuid fk → users | |
| role | text | user/agent |
| content | text | the Telegram message text itself (not retrieved email bodies) |
| tool_calls | jsonb | which tools were invoked, for evaluation |
| created_at | timestamptz | |

## 3. Retention

`RETENTION_DAYS` env var (default: unlimited/None for personal use). A scheduled
job (Phase 4/6) deletes `email_messages` (cascades to `email_analysis`,
`email_embeddings`, `extracted_events`) older than the retention window, except
rows with `feedback.feedback_type = always_important`.

## 4. Delete-my-data

`/settings` → "Delete all my data" triggers `DELETE FROM email_messages WHERE
user_id = ...` (cascades) plus revocation instructions for the Gmail OAuth grant
(the app cannot revoke it server-side without the `revoke` scope call, which is
included: `app/security/auth.py::revoke_gmail_access()` in Phase 2+).

## 5. Phase 1 substitute

Phase 1 has no Postgres dependency. Idempotency is provided by
`app/database/repositories/processed_messages.py`, a tiny repository interface
(`ProcessedMessageStore`) with one Phase-1 implementation backed by a local
SQLite file (`data/processed_messages.db`). The interface is intentionally
identical in shape to what the Phase 2 Postgres-backed repository will expose
(`has_processed(message_id)`, `mark_processed(message_id)`), so swapping the
implementation in `app/config.py` is the only change needed going into Phase 2.
