"""
Gmail integration: OAuth-authenticated client + polling-based new-mail
detection via users.history.list. See GMAIL_INTEGRATION.md for the design
rationale (why polling, first-run baseline behavior, 404 handling).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterator

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

READONLY_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


class GmailAuthError(RuntimeError):
    """Raised when the stored OAuth token is missing/invalid and needs re-consent."""


class GmailClient:
    def __init__(self, token_path: Path, state_path: Path):
        self._token_path = token_path
        self._state_path = state_path
        self._service = self._build_service()

    def _build_service(self):
        if not self._token_path.exists():
            raise GmailAuthError(
                f"No Gmail token found at {self._token_path}. "
                "Run scripts/gmail_oauth_setup.py first."
            )
        creds = Credentials.from_authorized_user_file(str(self._token_path), READONLY_SCOPES)
        if not creds.valid:
            if creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    self._token_path.write_text(creds.to_json())
                except RefreshError as exc:
                    raise GmailAuthError(
                        "Gmail token refresh failed (likely revoked). "
                        "Re-run scripts/gmail_oauth_setup.py."
                    ) from exc
            else:
                raise GmailAuthError("Gmail credentials invalid. Re-run OAuth setup.")
        return build("gmail", "v1", credentials=creds, cache_discovery=False)

    # --- polling state -------------------------------------------------

    def _load_state(self) -> dict:
        if self._state_path.exists():
            return json.loads(self._state_path.read_text())
        return {}

    def _save_state(self, state: dict) -> None:
        self._state_path.write_text(json.dumps(state))

    # --- API calls -------------------------------------------------------

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type(HttpError),
    )
    def _get_latest_history_id(self) -> str:
        profile = self._service.users().getProfile(userId="me").execute()
        return profile["historyId"]

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type(HttpError),
    )
    def get_message(self, message_id: str) -> dict:
        return (
            self._service.users()
            .messages()
            .get(userId="me", id=message_id, format="full")
            .execute()
        )

    def poll_new_message_ids(self) -> Iterator[str]:
        """
        Yields new Gmail message IDs since the last poll. On first run, just
        records a baseline historyId and yields nothing (no backlog blast).
        On a 404 (historyId too old / expired), resets the baseline the same way.
        """
        state = self._load_state()
        last_history_id = state.get("last_history_id")

        if not last_history_id:
            baseline = self._get_latest_history_id()
            self._save_state({"last_history_id": baseline})
            logger.info("Gmail poller: first run, baseline historyId=%s (no backlog notified)", baseline)
            return

        try:
            new_ids: list[str] = []
            page_token = None
            newest_history_id = last_history_id
            while True:
                resp = (
                    self._service.users()
                    .history()
                    .list(
                        userId="me",
                        startHistoryId=last_history_id,
                        historyTypes=["messageAdded"],
                        pageToken=page_token,
                    )
                    .execute()
                )
                for record in resp.get("history", []):
                    for added in record.get("messagesAdded", []):
                        new_ids.append(added["message"]["id"])
                newest_history_id = resp.get("historyId", newest_history_id)
                page_token = resp.get("nextPageToken")
                if not page_token:
                    break

            for mid in new_ids:
                yield mid

            # Only advance the baseline after a fully successful pass.
            self._save_state({"last_history_id": newest_history_id})

        except HttpError as exc:
            if exc.resp.status == 404:
                logger.warning("Gmail historyId expired; resetting baseline.")
                baseline = self._get_latest_history_id()
                self._save_state({"last_history_id": baseline})
                return
            from app.services import metrics
            metrics.increment("gmail_errors")
            raise
