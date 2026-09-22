"""
Turns a raw Gmail API message resource into clean, normalized text + metadata.
No network calls here — pure parsing, easy to unit test.
"""
from __future__ import annotations

import base64
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from bs4 import BeautifulSoup

_QUOTE_HEADER_RE = re.compile(
    r"^(On .{0,80} wrote:)|(-----Original Message-----)|(From:.{0,120}\nSent:)",
    re.IGNORECASE | re.MULTILINE,
)
_SIGNATURE_DELIMS = ["\n-- \n", "\n--\n", "\nSent from my iPhone", "\nSent from my Android"]
_TRACKING_IMG_RE = re.compile(r"width=[\"']?1[\"']?|height=[\"']?1[\"']?", re.IGNORECASE)


@dataclass
class NormalizedEmail:
    message_id: str
    thread_id: str
    sender: str
    recipients: list[str]
    cc: list[str]
    subject: str
    body_text: str
    snippet: str
    received_at: datetime
    labels: list[str]
    has_attachments: bool
    attachment_metadata: list[dict] = field(default_factory=list)


def html_to_text(html: str) -> str:
    """Strip scripts/styles/tracking pixels and return readable plain text."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    for img in soup.find_all("img"):
        style = (img.get("style") or "") + " " + str(img.get("width", "")) + str(img.get("height", ""))
        if _TRACKING_IMG_RE.search(style):
            img.decompose()
    text = soup.get_text(separator="\n")
    # collapse excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def trim_quoted_replies(text: str, max_quote_levels: int = 2) -> str:
    """Cut off long quoted-reply chains, keeping only the first N quote blocks."""
    match = _QUOTE_HEADER_RE.search(text)
    if not match:
        return text
    # Keep everything before the first quote marker, plus a shortened note.
    head = text[: match.start()].rstrip()
    remainder = text[match.start():]
    # Count how many quote headers exist; keep up to max_quote_levels worth.
    parts = _QUOTE_HEADER_RE.split(remainder)
    if len(parts) <= 1:
        return text
    kept = remainder
    headers = list(_QUOTE_HEADER_RE.finditer(remainder))
    if len(headers) > max_quote_levels:
        cutoff = headers[max_quote_levels].start()
        kept = remainder[:cutoff].rstrip() + "\n[older quoted messages truncated]"
    return f"{head}\n\n{kept}".strip()


def strip_signature(text: str) -> str:
    """Best-effort signature removal. Never trims before a real delimiter is found."""
    for delim in _SIGNATURE_DELIMS:
        idx = text.find(delim)
        if idx != -1:
            return text[:idx].rstrip()
    return text


def clean_body(raw_text: str | None, raw_html: str | None) -> str:
    if raw_text and raw_text.strip():
        text = raw_text
    elif raw_html and raw_html.strip():
        text = html_to_text(raw_html)
    else:
        text = ""
    text = trim_quoted_replies(text)
    text = strip_signature(text)
    return text.strip()


def _decode_part_data(data: str) -> str:
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8", errors="replace")


def _walk_parts(payload: dict) -> tuple[str | None, str | None, list[dict]]:
    """Return (text_plain, text_html, attachment_metadata) from a Gmail payload tree."""
    text_plain, text_html = None, None
    attachments: list[dict] = []

    def _walk(part: dict) -> None:
        nonlocal text_plain, text_html
        mime_type = part.get("mimeType", "")
        filename = part.get("filename") or ""
        body = part.get("body", {})

        if filename:
            attachments.append(
                {
                    "filename": filename,
                    "mime_type": mime_type,
                    "size": body.get("size", 0),
                }
            )
        elif mime_type == "text/plain" and "data" in body and text_plain is None:
            text_plain = _decode_part_data(body["data"])
        elif mime_type == "text/html" and "data" in body and text_html is None:
            text_html = _decode_part_data(body["data"])

        for sub in part.get("parts", []) or []:
            _walk(sub)

    _walk(payload)
    return text_plain, text_html, attachments


def _header(headers: list[dict], name: str) -> str:
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def _split_addresses(value: str) -> list[str]:
    if not value:
        return []
    return [addr.strip() for addr in value.split(",") if addr.strip()]


def extract_email_address(sender_header: str) -> str:
    """'Alice Smith <alice@example.com>' -> 'alice@example.com'."""
    if "<" in sender_header and ">" in sender_header:
        return sender_header.split("<", 1)[1].split(">", 1)[0].strip().lower()
    return sender_header.strip().lower()


def normalize_gmail_message(message: dict) -> NormalizedEmail:
    """Convert a raw `users.messages.get(format='full')` response into a NormalizedEmail."""
    payload = message.get("payload", {})
    headers = payload.get("headers", [])

    text_plain, text_html, attachments = _walk_parts(payload)
    body_text = clean_body(text_plain, text_html)

    internal_date_ms = int(message.get("internalDate", "0"))
    received_at = datetime.fromtimestamp(internal_date_ms / 1000, tz=timezone.utc)

    return NormalizedEmail(
        message_id=message["id"],
        thread_id=message.get("threadId", message["id"]),
        sender=_header(headers, "From"),
        recipients=_split_addresses(_header(headers, "To")),
        cc=_split_addresses(_header(headers, "Cc")),
        subject=_header(headers, "Subject") or "(no subject)",
        body_text=body_text,
        snippet=message.get("snippet", ""),
        received_at=received_at,
        labels=message.get("labelIds", []) or [],
        has_attachments=bool(attachments),
        attachment_metadata=attachments,
    )
