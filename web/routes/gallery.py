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


@gallery_bp.route("", methods=["GET"])
@login_required
def list_screenshots():
    page = max(1, request.args.get("page", 1, type=int))
    per_page = min(100, max(1, request.args.get("per_page", 20, type=int)))
    state_param = request.args.get("state", "ocr_complete,downloaded,removed")

    states = [s.strip() for s in state_param.split(",") if s.strip()]
    placeholders = ",".join("?" for _ in states)

    with database.get_db() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM screenshots WHERE state IN ({placeholders})",
            states,
        ).fetchone()[0]

        pages = max(1, math.ceil(total / per_page))
        offset = (page - 1) * per_page

        rows = conn.execute(
            f"""SELECT id, prnt_url, img_src, state, local_filename, image_format,
                       file_size_bytes, ocr_text, discovered_at, downloaded_at
                FROM screenshots
                WHERE state IN ({placeholders})
                ORDER BY discovered_at ASC
                LIMIT ? OFFSET ?""",
            states + [per_page, offset],
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
