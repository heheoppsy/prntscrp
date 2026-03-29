"""Database-backed proxy management."""

import logging
import random
import time

import requests

import config
import database

log = logging.getLogger(__name__)


class ProxyManager:
    """Manages a pool of proxies stored in the database."""

    def __init__(self):
        self._last_refresh: float = 0

    def refresh_proxies(self) -> int:
        """Fetch proxies from the API and upsert into the database.

        Returns the number of proxies upserted.
        """
        log.info("Refreshing proxies from %s", config.PROXY_API_URL)
        try:
            resp = requests.get(config.PROXY_API_URL, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            log.exception("Failed to fetch proxy list")
            return 0

        proxies = data.get("proxies", [])
        if not proxies:
            log.warning("No proxies returned from API")
            return 0

        count = 0
        with database.get_db() as conn:
            for p in proxies:
                ip = p.get("ip")
                port = p.get("port")
                protocol = p.get("protocol", "socks5")
                ssl_support = 1 if p.get("ssl") else 0

                if not ip or not port:
                    continue

                proxy_string = f"{protocol}://{ip}:{port}"

                conn.execute(
                    """
                    INSERT INTO proxies (protocol, ip, port, proxy_string, is_alive, ssl_support, source)
                    VALUES (?, ?, ?, ?, 1, ?, 'proxyscrape')
                    ON CONFLICT(ip, port) DO UPDATE SET
                        protocol = excluded.protocol,
                        proxy_string = excluded.proxy_string,
                        is_alive = 1,
                        ssl_support = excluded.ssl_support,
                        fetched_at = strftime('%Y-%m-%dT%H:%M:%f', 'now')
                    """,
                    (protocol, ip, int(port), proxy_string, ssl_support),
                )
                count += 1

        self._last_refresh = time.time()
        log.info("Upserted %d proxies", count)
        return count

    def get_random_proxy(self) -> str | None:
        """Return a random alive proxy string, or None if none available."""
        with database.get_db() as conn:
            rows = conn.execute(
                "SELECT proxy_string FROM proxies WHERE is_alive = 1"
            ).fetchall()

        if not rows:
            return None
        return random.choice(rows)["proxy_string"]

    def mark_success(self, proxy_string: str) -> None:
        """Record a successful request through this proxy."""
        with database.get_db() as conn:
            conn.execute(
                """
                UPDATE proxies
                SET success_count = success_count + 1,
                    last_success_at = strftime('%Y-%m-%dT%H:%M:%f', 'now')
                WHERE proxy_string = ?
                """,
                (proxy_string,),
            )

    def mark_failure(self, proxy_string: str) -> None:
        """Record a failed request through this proxy."""
        with database.get_db() as conn:
            conn.execute(
                """
                UPDATE proxies
                SET failure_count = failure_count + 1,
                    last_failure_at = strftime('%Y-%m-%dT%H:%M:%f', 'now'),
                    is_alive = CASE WHEN failure_count + 1 >= 5 THEN 0 ELSE is_alive END
                WHERE proxy_string = ?
                """,
                (proxy_string,),
            )

    @property
    def should_refresh(self) -> bool:
        return time.time() - self._last_refresh > config.PROXY_REFRESH_INTERVAL
