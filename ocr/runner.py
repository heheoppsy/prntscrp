"""CLI entry point for the OCR processor."""

import logging
import signal

import database
from ocr.ocr_processor import run_ocr_processor, running

log = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )

    database.init_db()

    def _shutdown(signum, frame):
        log.info("Received signal %s, shutting down...", signum)
        running.clear()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    log.info("Starting OCR processor")
    run_ocr_processor(worker_id="0")
    log.info("OCR processor stopped.")


if __name__ == "__main__":
    main()
