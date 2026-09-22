# Telegram AI Email Agent — Project Spec

This file is the source-of-truth product specification for the project, as provided
by the project owner. All architecture and implementation decisions in this repo
trace back to this document. See `IMPLEMENTATION_PLAN.md` for how the phases map to
actual code, and `ARCHITECTURE.md` for the system design derived from it.

Key non-negotiables extracted from this spec:

- Telegram is the ONLY user interface for the MVP. No web dashboard.
- Gmail is connected via OAuth 2.0 only. Never passwords.
- The LLM never directly triggers side effects (Telegram sends, tool execution) —
  the backend enforces all policy decisions (notification thresholds, tool access).
- Email content is untrusted data and must never be treated as instructions
  (prompt-injection resistant by construction).
- The AI provider is abstracted; no hard dependency on one vendor.
- The system should run for free for a single personal user.
- Development proceeds strictly phase by phase; Phase 1 = Gmail + AI triage +
  Telegram notification, end to end, before anything else is built.

The full original spec (sections 1–35) was provided by the project owner in chat
and is mirrored in this repository's `/docs` history / commit message for this file.
Refer to the conversation / issue tracker for the verbatim original text if needed.
