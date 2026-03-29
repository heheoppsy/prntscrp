"""Search API blueprint using FTS5 and regex."""

import math
import re

from flask import Blueprint, request, jsonify
from flask_login import login_required

import database

search_bp = Blueprint("search", __name__, url_prefix="/api/search")


def _regexp(pattern, value):
    """SQLite REGEXP implementation."""
    if value is None:
        return False
    try:
        return bool(re.search(pattern, value, re.IGNORECASE))
    except re.error:
        return False


@search_bp.route("", methods=["GET"])
@login_required
def search():
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"error": "Query parameter 'q' is required"}), 400

    mode = request.args.get("mode", "text")  # "text" or "regex"
    page = max(1, request.args.get("page", 1, type=int))
    per_page = min(100, max(1, request.args.get("per_page", 20, type=int)))

    if mode == "regex":
        # Validate regex before querying
        try:
            re.compile(query)
        except re.error as e:
            return jsonify({"error": f"Invalid regex: {e}"}), 400

        return _regex_search(query, page, per_page)
    else:
        return _fts_search(query, page, per_page)


def _fts_search(query: str, page: int, per_page: int):
    """Full-text search using FTS5."""
    fts_query = '"' + query.replace('"', '""') + '"'

    with database.get_db() as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM screenshots_fts WHERE screenshots_fts MATCH ?",
            (fts_query,),
        ).fetchone()[0]

        pages = max(1, math.ceil(total / per_page))
        offset = (page - 1) * per_page

        rows = conn.execute(
            """SELECT s.id, s.prnt_url, s.img_src, s.state, s.local_filename,
                      s.image_format, s.discovered_at, s.downloaded_at,
                      highlight(screenshots_fts, 1, '<mark>', '</mark>') AS ocr_text_highlighted
               FROM screenshots_fts
               JOIN screenshots s ON s.id = screenshots_fts.id
               WHERE screenshots_fts MATCH ?
               ORDER BY rank
               LIMIT ? OFFSET ?""",
            (fts_query, per_page, offset),
        ).fetchall()

    items = [
        {
            "id": r["id"],
            "prnt_url": r["prnt_url"],
            "img_src": r["img_src"],
            "local_filename": r["local_filename"],
            "image_format": r["image_format"],
            "discovered_at": r["discovered_at"],
            "downloaded_at": r["downloaded_at"],
            "ocr_text": r["ocr_text_highlighted"],
        }
        for r in rows
    ]

    return jsonify({"items": items, "total": total, "page": page, "pages": pages}), 200


def _regex_search(pattern: str, page: int, per_page: int):
    """Regex search on OCR text."""
    with database.get_db() as conn:
        # Register the regexp function for this connection
        conn.create_function("REGEXP", 2, _regexp)

        total = conn.execute(
            """SELECT COUNT(*) FROM screenshots
               WHERE state IN ('ocr_complete', 'downloaded', 'removed')
               AND ocr_text IS NOT NULL
               AND ocr_text REGEXP ?""",
            (pattern,),
        ).fetchone()[0]

        pages = max(1, math.ceil(total / per_page))
        offset = (page - 1) * per_page

        rows = conn.execute(
            """SELECT id, prnt_url, img_src, state, local_filename,
                      image_format, ocr_text, discovered_at, downloaded_at
               FROM screenshots
               WHERE state IN ('ocr_complete', 'downloaded', 'removed')
               AND ocr_text IS NOT NULL
               AND ocr_text REGEXP ?
               ORDER BY discovered_at ASC
               LIMIT ? OFFSET ?""",
            (pattern, per_page, offset),
        ).fetchall()

    # Highlight matches in the text
    compiled = re.compile(f"({pattern})", re.IGNORECASE)
    items = []
    for r in rows:
        ocr = r["ocr_text"] or ""
        # Truncate and highlight
        highlighted = compiled.sub(r"<mark>\1</mark>", ocr[:300])
        items.append({
            "id": r["id"],
            "prnt_url": r["prnt_url"],
            "img_src": r["img_src"],
            "local_filename": r["local_filename"],
            "image_format": r["image_format"],
            "discovered_at": r["discovered_at"],
            "downloaded_at": r["downloaded_at"],
            "ocr_text": highlighted,
        })

    return jsonify({"items": items, "total": total, "page": page, "pages": pages}), 200
