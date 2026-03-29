"""Central configuration for prntscrp."""

import os
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "screenshots.db"
DOWNLOADS_DIR = BASE_DIR / "downloads"
LOG_DIR = BASE_DIR / "log"

# Ensure directories exist
DOWNLOADS_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)

# Scraper
SCRAPER_THREADS = int(os.environ.get("SCRAPER_THREADS", 5))
SCRAPER_ID_MIN_LENGTH = 2
SCRAPER_ID_MAX_LENGTH = 7
SCRAPER_MAX_CONSECUTIVE_FAILURES = 50

# Proxy
PROXY_API_URL = os.environ.get(
    "PROXY_API_URL",
    "https://api.proxyscrape.com/v4/free-proxy-list/get"
    "?request=display_proxies&protocol=socks5,socks4"
    "&proxy_format=protocolipport&format=json&timeout=20000",
)
PROXY_REFRESH_INTERVAL = 3600  # seconds

# Downloader
DOWNLOADER_WORKERS = int(os.environ.get("DOWNLOADER_WORKERS", 5))
DOWNLOAD_TIMEOUT = 10  # seconds
MIN_IMAGE_SIZE = 1024  # bytes

PLACEHOLDER_HASHES = {
    "127c1f7c365337c0566cc4193ff9315ab36f5d92f268f4fb9f7cd6816ffdc998": "imgur",
    "6e1844b0af2a8d02d18b1ef73bd63fc063c63f4a30f9430217f1d2e07347913d": "imageshack",
}

BLOCKED_HOSTS = ["imgur.com", "imageshack"]

PRNTSCR_PLACEHOLDER_URLS = [
    "//st.prntscr.com/2023/07/24/0635/img/0_173a7b_211be8ff.png",
    "//st.prntscr.com/2025/12/17/0541/img/0_173a7b_211be8ff.png",
]

DOWNLOAD_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Referer": "https://prnt.sc/",
    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
}

# OCR
OCR_LANGUAGES = ["en"]
OCR_GPU = os.environ.get("OCR_GPU", "false").lower() == "true"
OCR_CONFIDENCE_THRESHOLD = 0.7

# Web / API
SECRET_KEY = os.environ.get("SECRET_KEY", "change-me-in-production")
API_HOST = os.environ.get("API_HOST", "127.0.0.1")
API_PORT = int(os.environ.get("API_PORT", 8888))

# SvelteKit dev server (for CORS during development)
FRONTEND_DEV_URL = os.environ.get("FRONTEND_DEV_URL", "http://localhost:5173")
