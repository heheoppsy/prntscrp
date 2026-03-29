"""CLI entry point for the downloader workers."""

import argparse
import logging
import signal
import threading

import config
import database
from downloader.download_worker import run_downloader, running
from scraper.proxy_manager import ProxyManager

log = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="Screenshot image downloader")
    parser.add_argument(
        "-t", "--threads",
        type=int,
        default=config.DOWNLOADER_WORKERS,
        help=f"Number of downloader threads (default: {config.DOWNLOADER_WORKERS})",
    )
    args = parser.parse_args()

    database.init_db()

    proxy_manager = ProxyManager()
    if proxy_manager.should_refresh:
        proxy_manager.refresh_proxies()

    log.info("Starting %d downloader threads", args.threads)

    threads: list[threading.Thread] = []
    for i in range(args.threads):
        t = threading.Thread(
            target=run_downloader,
            args=(str(i), proxy_manager),
            daemon=True,
            name=f"downloader-{i}",
        )
        t.start()
        threads.append(t)

    def _shutdown(signum, frame):
        log.info("Received signal %s, shutting down...", signum)
        running.clear()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    for t in threads:
        while t.is_alive():
            t.join(timeout=1.0)

    log.info("All downloader threads stopped.")


if __name__ == "__main__":
    main()
