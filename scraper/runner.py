"""CLI entry point for the scraper workers."""

import argparse
import logging
import signal
import sys
import threading

import config
import database
from scraper.proxy_manager import ProxyManager
from scraper.scraper_worker import run_scraper, running

log = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="prnt.sc scraper")
    parser.add_argument(
        "-t", "--threads",
        type=int,
        default=config.SCRAPER_THREADS,
        help=f"Number of scraper threads (default: {config.SCRAPER_THREADS})",
    )
    args = parser.parse_args()

    database.init_db()

    proxy_manager = ProxyManager()
    count = proxy_manager.refresh_proxies()
    if count == 0:
        log.error("No proxies available. Exiting.")
        sys.exit(1)

    log.info("Starting %d scraper threads", args.threads)

    threads: list[threading.Thread] = []
    for i in range(args.threads):
        t = threading.Thread(
            target=run_scraper,
            args=(i, proxy_manager),
            daemon=True,
            name=f"scraper-{i}",
        )
        t.start()
        threads.append(t)

    def _shutdown(signum, frame):
        log.info("Received signal %s, shutting down...", signum)
        running.clear()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    # Wait for all threads
    for t in threads:
        while t.is_alive():
            t.join(timeout=1.0)

    log.info("All scraper threads stopped.")


if __name__ == "__main__":
    main()
