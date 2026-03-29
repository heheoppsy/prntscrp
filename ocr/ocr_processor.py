"""OCR processor worker with multi-engine support (docTR, EasyOCR)."""

import json
import logging
import threading
import time
import warnings
from datetime import datetime, timezone

# Suppress PyTorch MPS warnings
warnings.filterwarnings("ignore", message=".*pin_memory.*MPS.*")
warnings.filterwarnings("ignore", category=UserWarning, module="torch")

import config
import database
from ocr.blacklist_filter import check_blacklist

log = logging.getLogger(__name__)

# Global shutdown event
running = threading.Event()
running.set()

# Engine instances (lazy-loaded)
_engine_lock = threading.Lock()
_engine = None
_engine_name = None


def _get_engine():
    """Get or initialize the OCR engine based on settings."""
    global _engine, _engine_name

    wanted = database.get_setting("ocr_engine") or "doctr"

    if _engine is not None and _engine_name == wanted:
        return _engine, _engine_name

    with _engine_lock:
        # Double-check after acquiring lock
        if _engine is not None and _engine_name == wanted:
            return _engine, _engine_name

        if wanted == "doctr":
            _engine = _init_doctr()
            _engine_name = "doctr"
        else:
            _engine = _init_easyocr()
            _engine_name = "easyocr"

        log.info("OCR engine initialized: %s", _engine_name)
        return _engine, _engine_name


def _init_doctr():
    """Initialize docTR OCR model."""
    from doctr.io import DocumentFile
    from doctr.models import ocr_predictor
    log.info("Loading docTR model...")
    use_gpu = database.get_setting_bool("ocr_gpu", False)
    predictor = ocr_predictor(
        det_arch="db_resnet50",
        reco_arch="crnn_vgg16_bn",
        pretrained=True,
    )
    if use_gpu:
        try:
            import torch
            if torch.cuda.is_available():
                predictor = predictor.cuda()
            elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                predictor = predictor.to("mps")
        except Exception:
            log.warning("GPU requested but not available, using CPU")
    return predictor


def _init_easyocr():
    """Initialize EasyOCR reader."""
    import easyocr
    use_gpu = database.get_setting_bool("ocr_gpu", False)
    languages = (database.get_setting("ocr_languages") or "en").split(",")
    log.info("Loading EasyOCR (gpu=%s, langs=%s)", use_gpu, languages)
    return easyocr.Reader([l.strip() for l in languages], gpu=use_gpu)


def _run_doctr(engine, filepath: str, confidence_threshold: float):
    """Run OCR with docTR. Returns (segments, full_text)."""
    from doctr.io import DocumentFile
    doc = DocumentFile.from_images(filepath)
    result = engine(doc)

    segments = []
    text_parts = []
    for page in result.pages:
        for block in page.blocks:
            for line in block.lines:
                for word in line.words:
                    if word.confidence >= confidence_threshold:
                        geo = word.geometry  # ((x_min, y_min), (x_max, y_max)) as 0-1 ratios
                        segments.append({
                            "text": word.value,
                            "confidence": round(word.confidence, 3),
                            "bbox": [
                                [round(geo[0][0], 4), round(geo[0][1], 4)],
                                [round(geo[1][0], 4), round(geo[1][1], 4)],
                            ],
                        })
                        text_parts.append(word.value)

    return segments, " ".join(text_parts).strip()


def _run_easyocr(engine, filepath: str, confidence_threshold: float):
    """Run OCR with EasyOCR. Returns (segments, full_text)."""
    results = engine.readtext(filepath)

    segments = []
    text_parts = []
    for bbox, text, confidence in results:
        if confidence >= confidence_threshold:
            segments.append({
                "text": text,
                "confidence": round(confidence, 3),
                "bbox": [[int(p) for p in point] for point in bbox],
            })
            text_parts.append(text)

    return segments, " ".join(text_parts).strip()


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

    confidence_threshold = database.get_setting_float("ocr_confidence_threshold", 0.7)

    # Run OCR with selected engine
    try:
        engine, engine_name = _get_engine()
        if engine_name == "doctr":
            segments, full_text = _run_doctr(engine, str(filepath), confidence_threshold)
        else:
            segments, full_text = _run_easyocr(engine, str(filepath), confidence_threshold)
    except Exception:
        log.exception("[ocr-%s] OCR failed for %s", worker_id, screenshot_id)
        database.transition(screenshot_id, "failed", filter_matched_pattern="ocr_error")
        return

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")

    if not full_text:
        database.transition(
            screenshot_id, "ocr_complete",
            ocr_text="",
            ocr_segments="[]",
            ocr_processed_at=now,
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
            ocr_processed_at=now,
        )
        log.info("[ocr-%s] Filtered %s (pattern: %s)", worker_id, screenshot_id, matched)

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
            ocr_processed_at=now,
        )
        log.info("[ocr-%s] Completed %s (%d chars, engine=%s)", worker_id, screenshot_id, len(full_text), _engine_name)
