"""Image validation utilities for the downloader."""

import io
import logging
from urllib.parse import urlparse

from PIL import Image

import config

log = logging.getLogger(__name__)


def is_blocked_host(url: str) -> bool:
    """Check if the URL's host matches any blocked host."""
    hostname = urlparse(url).hostname or ""
    return any(blocked in hostname for blocked in config.BLOCKED_HOSTS)


def is_placeholder_url(url: str) -> bool:
    """Check if the URL matches a known prnt.sc placeholder."""
    for placeholder in config.PRNTSCR_PLACEHOLDER_URLS:
        normalized = "https:" + placeholder if placeholder.startswith("//") else placeholder
        if url == normalized or url.endswith(placeholder):
            return True
    return False


def is_placeholder_hash(hash: str) -> str | None:
    """Return the source name if the hash matches a known placeholder, else None."""
    return config.PLACEHOLDER_HASHES.get(hash)


def validate_image_bytes(data: bytes) -> tuple[bool, str]:
    """Validate that data contains a valid image of sufficient size.

    Returns (is_valid, reason).
    """
    if len(data) < config.MIN_IMAGE_SIZE:
        return False, f"Too small ({len(data)} bytes)"

    try:
        img = Image.open(io.BytesIO(data))
        img.verify()
    except Exception as exc:
        return False, f"PIL verify failed: {exc}"

    return True, "ok"


def get_extension(url: str) -> str:
    """Determine file extension from URL path, defaulting to 'png'."""
    path = urlparse(url).path
    if "." in path:
        ext = path.rsplit(".", 1)[-1].lower().split("?")[0]
        if ext in ("jpg", "jpeg", "png", "gif", "webp", "avif", "bmp", "svg"):
            return ext
    return "png"
