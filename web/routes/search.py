"""Search API blueprint using FTS5 and regex."""

import math
import re

from flask import Blueprint, request, jsonify
from flask_login import login_required

import database

search_bp = Blueprint("search", __name__, url_prefix="/api/search")

VALID_SORT_COLUMNS = {
    "discovered_at", "downloaded_at", "file_size_bytes", "id",
}


def _parse_sort():
    sort_by = request.args.get("sort", "")
    sort_dir = request.args.get("dir", "asc").lower()
    if sort_by not in VALID_SORT_COLUMNS:
        sort_by = ""  # empty = use default (rank for FTS, discovered_at for regex)
    if sort_dir not in ("asc", "desc"):
        sort_dir = "asc"
    return sort_by, sort_dir


def _sort_clause(sort_by: str, sort_dir: str, default: str) -> str:
    if not sort_by:
        return default
    if sort_by == "id":
        return f"LENGTH(s.id) {sort_dir}, s.id {sort_dir}"
    return f"s.{sort_by} {sort_dir}"


@search_bp.route("", methods=["GET"])
@login_required
def search():
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"error": "Query parameter 'q' is required"}), 400

    mode = request.args.get("mode", "text")  # "text" or "regex"
    page = max(1, request.args.get("page", 1, type=int))
    per_page = min(100, max(1, request.args.get("per_page", 20, type=int)))
    sort_by, sort_dir = _parse_sort()

    if mode == "regex":
        try:
            re.compile(query)
        except re.error as e:
            return jsonify({"error": f"Invalid regex: {e}"}), 400
        return _regex_search(query, page, per_page, sort_by, sort_dir)
    else:
        return _fts_search(query, page, per_page, sort_by, sort_dir)


def _fts_search(query: str, page: int, per_page: int, sort_by: str, sort_dir: str):
    """Full-text search using FTS5."""
    fts_query = '"' + query.replace('"', '""') + '"'
    order = _sort_clause(sort_by, sort_dir, "rank")

    with database.get_db() as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM screenshots_fts WHERE screenshots_fts MATCH ?",
            (fts_query,),
        ).fetchone()[0]

        pages = max(1, math.ceil(total / per_page))
        offset = (page - 1) * per_page

        rows = conn.execute(
            f"""SELECT s.id, s.prnt_url, s.img_src, s.state, s.local_filename,
                      s.image_format, s.file_size_bytes, s.discovered_at, s.downloaded_at,
                      highlight(screenshots_fts, 1, '<mark>', '</mark>') AS ocr_text_highlighted
               FROM screenshots_fts
               JOIN screenshots s ON s.id = screenshots_fts.id
               WHERE screenshots_fts MATCH ?
               ORDER BY {order}
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
            "file_size_bytes": r["file_size_bytes"],
            "discovered_at": r["discovered_at"],
            "downloaded_at": r["downloaded_at"],
            "ocr_text": r["ocr_text_highlighted"],
        }
        for r in rows
    ]

    return jsonify({"items": items, "total": total, "page": page, "pages": pages}), 200


def _regex_search(pattern: str, page: int, per_page: int, sort_by: str, sort_dir: str):
    """Regex search on OCR text."""
    order = _sort_clause(sort_by, sort_dir, f"s.discovered_at {sort_dir}" if sort_dir else "s.discovered_at ASC")

    with database.get_db() as conn:
        conn.create_function("REGEXP", 2, _regexp)

        total = conn.execute(
            """SELECT COUNT(*) FROM screenshots s
               WHERE s.state IN ('ocr_complete', 'downloaded', 'removed')
               AND s.ocr_text IS NOT NULL
               AND s.ocr_text REGEXP ?""",
            (pattern,),
        ).fetchone()[0]

        pages = max(1, math.ceil(total / per_page))
        offset = (page - 1) * per_page

        rows = conn.execute(
            f"""SELECT s.id, s.prnt_url, s.img_src, s.state, s.local_filename,
                      s.image_format, s.file_size_bytes, s.ocr_text,
                      s.discovered_at, s.downloaded_at
               FROM screenshots s
               WHERE s.state IN ('ocr_complete', 'downloaded', 'removed')
               AND s.ocr_text IS NOT NULL
               AND s.ocr_text REGEXP ?
               ORDER BY {order}
               LIMIT ? OFFSET ?""",
            (pattern, per_page, offset),
        ).fetchall()

    compiled = re.compile(f"({pattern})", re.IGNORECASE)
    items = []
    for r in rows:
        ocr = r["ocr_text"] or ""
        highlighted = compiled.sub(r"<mark>\1</mark>", ocr[:300])
        items.append({
            "id": r["id"],
            "prnt_url": r["prnt_url"],
            "img_src": r["img_src"],
            "local_filename": r["local_filename"],
            "image_format": r["image_format"],
            "file_size_bytes": r["file_size_bytes"],
            "discovered_at": r["discovered_at"],
            "downloaded_at": r["downloaded_at"],
            "ocr_text": highlighted,
        })

    return jsonify({"items": items, "total": total, "page": page, "pages": pages}), 200


def _regexp(pattern, value):
    """SQLite REGEXP implementation."""
    if value is None:
        return False
    try:
        return bool(re.search(pattern, value, re.IGNORECASE))
    except re.error:
        return False
