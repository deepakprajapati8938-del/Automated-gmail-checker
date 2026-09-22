#!/usr/bin/env python3
"""
Run this ONCE to grant this app read-only access to your Gmail inbox.

Prerequisites:
  1. Create a Google Cloud project, enable the Gmail API.
  2. Create OAuth client credentials of type "Desktop app".
  3. Download the JSON and point GMAIL_CLIENT_SECRET_PATH at it (see .env.example).

This never asks for or sees your Gmail password — it's the standard OAuth
consent screen in your browser. Only the `gmail.readonly` scope is requested.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from google_auth_oauthlib.flow import InstalledAppFlow

from app.config import settings
from app.email.gmail import READONLY_SCOPES


def main() -> None:
    if not settings.gmail_client_secret_path.exists():
        print(
            f"Client secret file not found at {settings.gmail_client_secret_path}.\n"
            "Download it from Google Cloud Console (OAuth client type: Desktop app) "
            "and set GMAIL_CLIENT_SECRET_PATH accordingly.",
            file=sys.stderr,
        )
        sys.exit(1)

    flow = InstalledAppFlow.from_client_secrets_file(
        str(settings.gmail_client_secret_path), READONLY_SCOPES
    )
    creds = flow.run_local_server(port=0)

    settings.gmail_token_path.parent.mkdir(parents=True, exist_ok=True)
    settings.gmail_token_path.write_text(creds.to_json())
    settings.gmail_token_path.chmod(0o600)

    print(f"Gmail OAuth complete. Token saved to {settings.gmail_token_path}")
    print("You can now run: python -m app.main")


if __name__ == "__main__":
    main()
