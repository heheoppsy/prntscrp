"""OCR processor worker."""

import json
import logging
import threading
import time
from datetime import datetime, timezone

import config
import database
from ocr.blacklist_filter import check_blacklist

log = logging.getLogger(__name__)

# Global shutdown event
running = threading.Event()
running.set()

# Lazy-loaded EasyOCR reader (heavy initialization)
_reader_lock = threading.Lock()
_reader = None


def _get_reader():
    global _reader
    if _reader is None:
        with _reader_lock:
            if _reader is None:
                import easyocr
                log.info("Initializing EasyOCR reader (gpu=%s)", config.OCR_GPU)
                _reader = easyocr.Reader(config.OCR_LANGUAGES, gpu=config.OCR_GPU)
    return _reader


def _load_blacklist_patterns() -> list[str]:
    """Load blacklist patterns from the database."""
    with database.get_db() as conn:
        rows = conn.execute("SELECT pattern FROM blacklist_patterns").fetchall()
    return [row["pattern"] for row in rows]


def run_ocr_processor(worker_id: str) -> None:
    """Main loop for the OCR processor."""
    log.info("[ocr-%s] Starting", worker_id)

    while running.is_set():
        ids = database.claim_work("downloaded", "ocr_pending", worker_id, limit=1)
        if not ids:
            time.sleep(1)
            continue

        screenshot_id = ids[0]
        try:
            _process_one(screenshot_id, worker_id)
        except Exception:
            log.exception("[ocr-%s] Unhandled error processing %s, returning to downloaded", worker_id, screenshot_id)
            try:
                database.transition(screenshot_id, "downloaded")
            except Exception:
                log.exception("[ocr-%s] Failed to recover state for %s", worker_id, screenshot_id)

    log.info("[ocr-%s] Shutting down", worker_id)


def _process_one(screenshot_id: str, worker_id: str) -> None:
    """Run OCR on a single screenshot."""
    # Get file info from DB
    with database.get_db() as conn:
        row = conn.execute(
            "SELECT local_filename FROM screenshots WHERE id = ?",
            (screenshot_id,),
        ).fetchone()

    if row is None or not row["local_filename"]:
        database.transition(screenshot_id, "failed", filter_matched_pattern="no_file")
        return

    filepath = config.DOWNLOADS_DIR / row["local_filename"]
    if not filepath.exists():
        database.transition(screenshot_id, "failed", filter_matched_pattern="file_missing")
        return

    # Run OCR
    try:
        reader = _get_reader()
        results = reader.readtext(str(filepath))
    except Exception:
        log.exception("[ocr-%s] OCR failed for %s", worker_id, screenshot_id)
        database.transition(screenshot_id, "failed", filter_matched_pattern="ocr_error")
        return

    # Filter by confidence and build text
    segments = []
    text_parts = []
    for bbox, text, confidence in results:
        if confidence >= config.OCR_CONFIDENCE_THRESHOLD:
            segments.append({
                "text": text,
                "confidence": round(confidence, 3),
                "bbox": [[int(p) for p in point] for point in bbox],
            })
            text_parts.append(text)

    full_text = " ".join(text_parts).strip()

    if not full_text:
        database.transition(
            screenshot_id, "ocr_complete",
            ocr_text="",
            ocr_segments="[]",
            ocr_processed_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f"),
        )
        log.debug("[ocr-%s] No text found in %s", worker_id, screenshot_id)
        return

    # Blacklist check
    patterns = _load_blacklist_patterns()
    matched = check_blacklist(full_text, patterns)

    if matched:
        database.transition(
            screenshot_id, "filtered",
            filter_matched_pattern=matched,
            ocr_text=full_text,
            ocr_segments=json.dumps(segments),
            ocr_processed_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f"),
        )
        # Delete the image file
        try:
            filepath.unlink()
        except OSError:
            log.warning("[ocr-%s] Failed to delete %s", worker_id, filepath)
        log.info("[ocr-%s] Filtered %s (pattern: %s)", worker_id, screenshot_id, matched)

        # Increment hit count
        with database.get_db() as conn:
            conn.execute(
                "UPDATE blacklist_patterns SET hit_count = hit_count + 1 WHERE pattern = ?",
                (matched,),
            )
    else:
        database.transition(
            screenshot_id, "ocr_complete",
            ocr_text=full_text,
            ocr_segments=json.dumps(segments),
            ocr_processed_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f"),
        )
        log.info("[ocr-%s] Completed %s (%d chars)", worker_id, screenshot_id, len(full_text))
