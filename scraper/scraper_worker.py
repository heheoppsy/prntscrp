"""Scraper worker that discovers screenshot URLs on prnt.sc."""

import logging
import random
import string
import threading
import time

import requests

import config
import database
from scraper.page_parser import parse_screenshot_page

log = logging.getLogger(__name__)

# Global shutdown event shared by all workers
running = threading.Event()
running.set()

CHARSET = string.ascii_lowercase + string.digits


def _random_id() -> str:
    length = random.randint(config.SCRAPER_ID_MIN_LENGTH, config.SCRAPER_ID_MAX_LENGTH)
    return "".join(random.choices(CHARSET, k=length))


def run_scraper(worker_id: int, proxy_manager) -> None:
    """Main loop for a scraper worker thread."""
    log.info("[scraper-%d] Starting", worker_id)
    consecutive_failures = 0
    current_proxy: str | None = None

    while running.is_set():
        # Rotate proxy when needed
        if current_proxy is None or consecutive_failures >= 3:
            current_proxy = proxy_manager.get_random_proxy()
            if current_proxy is None:
                log.warning("[scraper-%d] No proxies available, sleeping", worker_id)
                time.sleep(5)
                continue
            consecutive_failures = 0

        screenshot_id = _random_id()

        # Skip if already in DB
        if database.screenshot_exists(screenshot_id):
            continue

        url = f"https://prnt.sc/{screenshot_id}"
        proxies = {"http": current_proxy, "https": current_proxy}

        try:
            resp = requests.get(
                url,
                proxies=proxies,
                timeout=config.DOWNLOAD_TIMEOUT,
                headers={"User-Agent": config.DOWNLOAD_HEADERS["User-Agent"]},
            )
            resp.raise_for_status()
            html = resp.text
            resp.close()
        except Exception:
            log.debug("[scraper-%d] Fetch failed for %s via %s", worker_id, url, current_proxy)
            proxy_manager.mark_failure(current_proxy)
            consecutive_failures += 1
            if consecutive_failures >= config.SCRAPER_MAX_CONSECUTIVE_FAILURES:
                log.error("[scraper-%d] Too many consecutive failures, rotating proxy", worker_id)
                current_proxy = None
                consecutive_failures = 0
            continue

        proxy_manager.mark_success(current_proxy)
        consecutive_failures = 0

        img_src = parse_screenshot_page(html)
        if img_src:
            inserted = database.insert_screenshot(screenshot_id, url, img_src, state="discovered")
            if inserted:
                log.info("[scraper-%d] Discovered %s -> %s", worker_id, screenshot_id, img_src)
        else:
            log.debug("[scraper-%d] No valid image on %s", worker_id, url)

        # Small delay to be polite
        time.sleep(0.2)

    log.info("[scraper-%d] Shutting down", worker_id)
