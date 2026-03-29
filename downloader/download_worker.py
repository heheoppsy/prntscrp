"""Download worker that fetches discovered screenshot images via proxies."""

import hashlib
import logging
import threading
import time
from datetime import datetime, timezone

import requests

import config
import database
from downloader.image_validator import (
    get_extension,
    is_blocked_host,
    is_placeholder_hash,
    is_placeholder_url,
    validate_image_bytes,
)

log = logging.getLogger(__name__)

# Global shutdown event shared by all workers
running = threading.Event()
running.set()


def run_downloader(worker_id: str, proxy_manager) -> None:
    """Main loop for a downloader worker thread."""
    log.info("[dl-%s] Starting", worker_id)
    current_proxy: str | None = None
    consecutive_failures = 0

    while running.is_set():
        ids = database.claim_work("discovered", "downloading", worker_id, limit=10)
        if not ids:
            time.sleep(2)
            continue

        # Get a proxy for this batch
        if current_proxy is None or consecutive_failures >= 3:
            current_proxy = proxy_manager.get_random_proxy()
            if current_proxy is None:
                log.warning("[dl-%s] No proxies available, sleeping", worker_id)
                # Release claimed work back to discovered so other workers can try
                for sid in ids:
                    database.transition(sid, "discovered")
                time.sleep(5)
                continue
            consecutive_failures = 0

        for screenshot_id in ids:
            if not running.is_set():
                break
            success = _download_one(screenshot_id, worker_id, current_proxy)
            if not success:
                consecutive_failures += 1
                if consecutive_failures >= 3:
                    log.info("[dl-%s] Rotating proxy after %d failures", worker_id, consecutive_failures)
                    current_proxy = proxy_manager.get_random_proxy()
                    consecutive_failures = 0
            else:
                consecutive_failures = 0

    log.info("[dl-%s] Shutting down", worker_id)


def _download_one(screenshot_id: str, worker_id: str, proxy_string: str) -> bool:
    """Download and validate a single screenshot. Returns True on success."""
    # Fetch the image URL from DB
    with database.get_db() as conn:
        row = conn.execute(
            "SELECT img_src FROM screenshots WHERE id = ?", (screenshot_id,)
        ).fetchone()

    if row is None or not row["img_src"]:
        database.transition(screenshot_id, "skipped", filter_matched_pattern="no_img_src")
        return True  # Not a proxy failure

    url: str = row["img_src"]

    # Pre-download validation
    if is_blocked_host(url):
        database.transition(screenshot_id, "skipped", filter_matched_pattern="blocked_host")
        log.debug("[dl-%s] Blocked host: %s", worker_id, url)
        return True

    if is_placeholder_url(url):
        database.transition(screenshot_id, "skipped", filter_matched_pattern="placeholder_url")
        log.debug("[dl-%s] Placeholder URL: %s", worker_id, url)
        return True

    # Download via proxy
    proxies = {"http": proxy_string, "https": proxy_string}
    try:
        resp = requests.get(
            url,
            headers=config.DOWNLOAD_HEADERS,
            timeout=config.DOWNLOAD_TIMEOUT,
            proxies=proxies,
        )
        resp.raise_for_status()
    except Exception:
        log.debug("[dl-%s] Download failed for %s via %s", worker_id, screenshot_id, proxy_string)
        # Put back to discovered for retry, not permanently failed
        database.transition(screenshot_id, "discovered")
        return False  # Proxy failure

    data = resp.content

    # Validate image
    valid, reason = validate_image_bytes(data)
    if not valid:
        database.transition(screenshot_id, "skipped", filter_matched_pattern=reason)
        log.debug("[dl-%s] Invalid image %s: %s", worker_id, screenshot_id, reason)
        return True

    # Check hash against known placeholders
    image_hash = hashlib.sha256(data).hexdigest()
    source = is_placeholder_hash(image_hash)
    if source:
        database.transition(screenshot_id, "skipped", filter_matched_pattern=f"placeholder_{source}")
        log.debug("[dl-%s] Placeholder hash (%s): %s", worker_id, source, screenshot_id)
        return True

    # Save to disk
    ext = get_extension(url)
    filename = f"{screenshot_id}.{ext}"
    filepath = config.DOWNLOADS_DIR / filename

    try:
        filepath.write_bytes(data)
    except OSError:
        log.exception("[dl-%s] Failed to write %s", worker_id, filepath)
        database.transition(screenshot_id, "failed", filter_matched_pattern="write_error")
        return True

    database.transition(
        screenshot_id,
        "downloaded",
        local_filename=filename,
        file_size_bytes=len(data),
        image_hash=image_hash,
        image_format=ext,
        downloaded_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f"),
    )
    log.info("[dl-%s] Downloaded %s (%d bytes)", worker_id, screenshot_id, len(data))
    return True
