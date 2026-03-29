"""Parse prnt.sc screenshot pages."""

import logging

from bs4 import BeautifulSoup

import config

log = logging.getLogger(__name__)


def parse_screenshot_page(html: str) -> str | None:
    """Extract the screenshot image URL from a prnt.sc page.

    Returns the image src with protocol-relative URLs fixed, or None if
    no valid image is found.
    """
    soup = BeautifulSoup(html, "html.parser")
    img = soup.find("img", id="screenshot-image")
    if img is None:
        log.debug("No <img id='screenshot-image'> found")
        return None

    src = img.get("src", "")
    if not src:
        return None

    # Fix protocol-relative URLs
    if src.startswith("//"):
        src = "https:" + src

    # Skip known placeholder images
    for placeholder in config.PRNTSCR_PLACEHOLDER_URLS:
        normalized = "https:" + placeholder if placeholder.startswith("//") else placeholder
        if src == normalized or src.endswith(placeholder):
            log.debug("Skipping placeholder URL: %s", src)
            return None

    return src
