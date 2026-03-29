"""Blacklist filter for OCR text."""

import logging
import re

log = logging.getLogger(__name__)

# Matches most email-like patterns
_EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")


def _normalize(text: str) -> str:
    """Normalize text for matching: lowercase, fix spaced separators."""
    text = text.lower()
    # Fix spaced dots: "g m a i l . c o m" -> "gmail.com"
    text = re.sub(r"(?<=\w)\s*\.\s*(?=\w)", ".", text)
    # Fix spaced @: "user @ domain" -> "user@domain"
    text = re.sub(r"\s*@\s*", "@", text)
    # Fix spaced hyphens
    text = re.sub(r"\s*-\s*", "-", text)
    return text


def check_blacklist(text: str, patterns: list[str]) -> str | None:
    """Check text against blacklist patterns.

    Returns the first matched pattern, or None if clean.
    """
    normalized = _normalize(text)

    for pattern in patterns:
        p = pattern.lower()
        if p in normalized:
            return pattern

    # Also extract emails and check those against patterns
    emails = _EMAIL_RE.findall(normalized)
    for email in emails:
        for pattern in patterns:
            p = pattern.lower()
            if p in email.lower():
                return pattern

    return None
