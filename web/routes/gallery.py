"""Gallery API blueprint."""

import math
import os

from flask import Blueprint, request, jsonify
from flask_login import login_required

import config
import database
from web.auth import admin_required

gallery_bp = Blueprint("gallery", __name__, url_prefix="/api/gallery")


def _row_to_dict(row) -> dict:
    d = {
        "id": row["id"],
        "prnt_url": row["prnt_url"],
        "img_src": row["img_src"],
        "local_filename": row["local_filename"],
        "image_format": row["image_format"],
        "ocr_text": row["ocr_text"],
        "discovered_at": row["discovered_at"],
        "downloaded_at": row["downloaded_at"],
    }
    # Include optional fields if present in the row
    for col in ("state", "file_size_bytes"):
        try:
            d[col] = row[col]
        except (IndexError, KeyError):
            pass
    return d


VALID_SORT_COLUMNS = {
    "discovered_at", "downloaded_at", "file_size_bytes", "id", "ocr_processed_at",
}

# Base36 numeric sort: shorter IDs are smaller numbers, then alphabetical within same length
ID_SORT_EXPR = "LENGTH(id), id"


@gallery_bp.route("", methods=["GET"])
@login_required
def list_screenshots():
    page = max(1, request.args.get("page", 1, type=int))
    per_page = min(100, max(1, request.args.get("per_page", 20, type=int)))
    state_param = request.args.get("state", "ocr_complete,downloaded,removed")

    # Sorting
    sort_by = request.args.get("sort", "discovered_at")
    sort_dir = request.args.get("dir", "asc").lower()
    if sort_by not in VALID_SORT_COLUMNS:
        sort_by = "discovered_at"
    if sort_dir not in ("asc", "desc"):
        sort_dir = "asc"

    # Filters
    min_size = request.args.get("min_size", None, type=int)
    max_size = request.args.get("max_size", None, type=int)
    has_ocr = request.args.get("has_ocr", None)  # "true" or "false"
    date_from = request.args.get("date_from", None)
    date_to = request.args.get("date_to", None)
    format_filter = request.args.get("format", None)
    id_from = request.args.get("id_from", None)
    id_to = request.args.get("id_to", None)
    min_id_len = request.args.get("min_id_len", None, type=int)
    max_id_len = request.args.get("max_id_len", None, type=int)

    states = [s.strip() for s in state_param.split(",") if s.strip()]
    placeholders = ",".join("?" for _ in states)

    where = [f"state IN ({placeholders})"]
    params: list = list(states)

    if min_size is not None:
        where.append("file_size_bytes >= ?")
        params.append(min_size)
    if max_size is not None:
        where.append("file_size_bytes <= ?")
        params.append(max_size)
    if has_ocr == "true":
        where.append("ocr_text IS NOT NULL AND ocr_text != ''")
    elif has_ocr == "false":
        where.append("(ocr_text IS NULL OR ocr_text = '')")
    if date_from:
        where.append("downloaded_at >= ?")
        params.append(date_from)
    if date_to:
        where.append("downloaded_at <= ?")
        params.append(date_to)
    if format_filter:
        where.append("image_format = ?")
        params.append(format_filter)
    if id_from:
        where.append("(LENGTH(id) > ? OR (LENGTH(id) = ? AND id >= ?))")
        params.extend([len(id_from), len(id_from), id_from])
    if id_to:
        where.append("(LENGTH(id) < ? OR (LENGTH(id) = ? AND id <= ?))")
        params.extend([len(id_to), len(id_to), id_to])
    if min_id_len is not None:
        where.append("LENGTH(id) >= ?")
        params.append(min_id_len)
    if max_id_len is not None:
        where.append("LENGTH(id) <= ?")
        params.append(max_id_len)

    where_clause = " AND ".join(where)

    with database.get_db() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM screenshots WHERE {where_clause}",
            params,
        ).fetchone()[0]

        pages = max(1, math.ceil(total / per_page))
        offset = (page - 1) * per_page

        rows = conn.execute(
            f"""SELECT id, prnt_url, img_src, state, local_filename, image_format,
                       file_size_bytes, ocr_text, discovered_at, downloaded_at
                FROM screenshots
                WHERE {where_clause}
                ORDER BY {f"LENGTH(id) {sort_dir}, id {sort_dir}" if sort_by == "id" else f"{sort_by} {sort_dir}"}
                LIMIT ? OFFSET ?""",
            params + [per_page, offset],
        ).fetchall()

    return jsonify({
        "items": [_row_to_dict(r) for r in rows],
        "total": total,
        "page": page,
        "pages": pages,
    }), 200


@gallery_bp.route("/random", methods=["GET"])
@login_required
def random_screenshot():
    with database.get_db() as conn:
        row = conn.execute(
            """SELECT id, prnt_url, img_src, local_filename, image_format,
                      ocr_text, discovered_at, downloaded_at
               FROM screenshots
               WHERE state IN ('ocr_complete', 'downloaded')
               ORDER BY RANDOM() LIMIT 1"""
        ).fetchone()

    if not row:
        return jsonify({"error": "No screenshots available"}), 404

    return jsonify(_row_to_dict(row)), 200


@gallery_bp.route("/stats", methods=["GET"])
@login_required
def stats():
    with database.get_db() as conn:
        state_counts = conn.execute(
            "SELECT state, COUNT(*) as count FROM screenshots GROUP BY state"
        ).fetchall()

        total_size = conn.execute(
            "SELECT COALESCE(SUM(file_size_bytes), 0) FROM screenshots"
        ).fetchone()[0]

    return jsonify({
        "counts_by_state": {r["state"]: r["count"] for r in state_counts},
        "total_disk_bytes": total_size,
    }), 200


@gallery_bp.route("/public-stats", methods=["GET"])
def public_stats():
    """Public stats endpoint — no auth required."""
    with database.get_db() as conn:
        total_images = conn.execute(
            "SELECT COUNT(*) FROM screenshots WHERE state IN ('downloaded', 'ocr_complete')"
        ).fetchone()[0]

        total_size = conn.execute(
            "SELECT COALESCE(SUM(file_size_bytes), 0) FROM screenshots WHERE state IN ('downloaded', 'ocr_complete')"
        ).fetchone()[0]

    return jsonify({
        "total_images": total_images,
        "total_bytes": total_size,
    }), 200


@gallery_bp.route("/<screenshot_id>", methods=["GET"])
@login_required
def get_screenshot(screenshot_id: str):
    with database.get_db() as conn:
        row = conn.execute(
            """SELECT id, prnt_url, img_src, state, local_filename, image_format,
                      file_size_bytes, ocr_text, discovered_at, downloaded_at
               FROM screenshots WHERE id = ?""",
            (screenshot_id,),
        ).fetchone()

    if not row:
        return jsonify({"error": "Screenshot not found"}), 404

    return jsonify(_row_to_dict(row)), 200


@gallery_bp.route("/<screenshot_id>", methods=["DELETE"])
@admin_required
def delete_screenshot(screenshot_id: str):
    with database.get_db() as conn:
        row = conn.execute(
            "SELECT local_filename FROM screenshots WHERE id = ?",
            (screenshot_id,),
        ).fetchone()

        if not row:
            return jsonify({"error": "Screenshot not found"}), 404

        # Delete the file from disk if it exists
        if row["local_filename"]:
            filepath = config.DOWNLOADS_DIR / row["local_filename"]
            if filepath.is_file():
                os.remove(filepath)

        # Keep the row but mark as removed
        conn.execute(
            """UPDATE screenshots
               SET state = 'removed', local_filename = NULL, file_size_bytes = 0,
                   ocr_text = NULL, ocr_segments = NULL, ocr_confidence = NULL,
                   updated_at = strftime('%Y-%m-%dT%H:%M:%f', 'now')
               WHERE id = ?""",
            (screenshot_id,),
        )

    return jsonify({"message": "Removed"}), 200
