<p align="center">
  <img src="frontend/static/prntscrp.svg" width="80">
</p>

<h1 align="center">prntscrp</h1>

<p align="center">Self-hosted screenshot archiver for <a href="https://prnt.sc">prnt.sc</a>.<br>Scrapes, downloads, and indexes random screenshots through proxies.</p>

## Features

- **Scraper** — finds screenshot URLs by generating random IDs and hitting prnt.sc through SOCKS proxies
- **Downloader** — grabs the actual images, checks for placeholders and duplicates via SHA-256
- **OCR** — reads text from images using [docTR](https://github.com/mindee/doctr) (or EasyOCR as a fallback), with configurable blacklist filtering
- **Search** — full-text and regex search over extracted text, powered by SQLite FTS5
- **Gallery** — SvelteKit frontend with image grid, lightbox viewer, advanced filters, and sorting
- **Admin panel** — manage workers, proxies, users, blacklist, OCR engine, and all settings from the browser
- **Single-file database** — everything in one SQLite file with WAL mode for concurrent access

## Screenshots

<details>
<summary>Gallery</summary>
<img src="screenshots/gallery.png" width="100%">
</details>

<details>
<summary>Admin</summary>
<img src="screenshots/admin.png" width="100%">
</details>

## Requirements

- Python 3.10+
- Node.js 18+
- pip dependencies (see `requirements.txt`)

## Quick Start

```bash
git clone https://github.com/heheoppsy/prntscrp.git
cd prntscrp

# Install Python dependencies
pip install -r requirements.txt

# Install frontend dependencies
cd frontend && npm install && cd ..

# Start everything
./run.sh
```

Open [http://localhost:5173](http://localhost:5173). Default login is `admin` / `changeme`.

Start the scraper, downloader, and OCR workers from the admin panel (Processes tab).

## Configuration

All settings are configurable from the admin panel (Settings tab), grouped by component:

| Group | Setting | Default | Description |
|-------|---------|---------|-------------|
| Scraper | `scraper_threads` | 5 | Worker thread count |
| Scraper | `scraper_delay` | 0.2 | Seconds between requests |
| Downloader | `downloader_threads` | 5 | Worker thread count |
| Downloader | `downloader_use_proxy` | true | Route downloads through proxies |
| OCR | `ocr_engine` | doctr | `doctr` or `easyocr` |
| OCR | `ocr_enabled` | true | Toggle OCR processing |
| OCR | `ocr_confidence_threshold` | 0.7 | Minimum confidence to keep text |
| Proxy | `proxy_api_url` | proxyscrape | Proxy list API endpoint |

You can also rebuild all OCR data from the settings page after switching engines.

## OCR Engines

**[docTR](https://github.com/mindee/doctr)** (default) — transformer-based, handles mixed fonts and sizes well. Install with:
```
pip install "python-doctr[torch]"
```

**[EasyOCR](https://github.com/JaidedAI/EasyOCR)** — simpler but less accurate on screenshots. Install with:
```
pip install easyocr
```

Switch between them in the admin settings. The app checks if the engine is installed before allowing the switch.

## Notes

I suggest not hosting this on a VPS, most are pretty picky about web scraping and you'll probably get your service account banned.

The user account system is there if you'd like to host your archive for a few people or on your local network.  Some of the images you can grab from prnt.sc are quite questionable.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | `change-me-in-production` | Flask session secret |
| `API_HOST` | `127.0.0.1` | API bind address |
| `API_PORT` | `8888` | API port |
| `PYTHON` | `python3` | Python binary for `run.sh` |

Copy `.env.example` to `.env` to configure.

## License

[MIT](LICENSE)
