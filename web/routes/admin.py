"""Admin API blueprint."""

import subprocess
import signal
import sys
import os
from flask import Blueprint, request, jsonify
from flask_login import current_user

import config
import database
from web.auth import admin_required

admin_bp = Blueprint("admin", __name__, url_prefix="/api/admin")


# --- Process management ---
# PIDs are persisted to a file so they survive Flask debug reloads.

_PIDFILE = config.LOG_DIR / "pids.json"
_processes: dict[str, subprocess.Popen] = {}
_log_files: dict[str, object] = {}


def _load_pids() -> dict[str, int]:
    """Load saved PIDs from disk."""
    if _PIDFILE.exists():
        try:
            import json
            with open(_PIDFILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_pids():
    """Persist current PIDs to disk."""
    import json
    pids = {}
    for name, proc in _processes.items():
        if proc and proc.poll() is None:
            pids[name] = proc.pid
    # Also preserve PIDs we don't have Popen objects for (orphans from reload)
    for name, pid in _load_pids().items():
        if name not in pids and _pid_alive(pid):
            pids[name] = pid
    with open(_PIDFILE, "w") as f:
        json.dump(pids, f)


def _pid_alive(pid: int) -> bool:
    """Check if a PID is actually running."""
    try:
        os.kill(pid, 0)  # Signal 0 = just check existence
        return True
    except (OSError, ProcessLookupError):
        return False


def _is_running(name: str) -> tuple[bool, int | None]:
    """Check if a process is running. Returns (running, pid)."""
    # First check our Popen objects
    proc = _processes.get(name)
    if proc is not None and proc.poll() is None:
        return True, proc.pid

    # Fall back to saved PIDs (survives Flask reload)
    saved = _load_pids()
    pid = saved.get(name)
    if pid and _pid_alive(pid):
        return True, pid

    return False, None


@admin_bp.route("/processes", methods=["GET"])
@admin_required
def list_processes():
    status = {}
    for name in ("scraper", "downloader", "ocr"):
        running, pid = _is_running(name)
        status[name] = {"running": running, "pid": pid}

    return jsonify({"processes": status}), 200


@admin_bp.route("/processes/<name>/start", methods=["POST"])
@admin_required
def start_process(name: str):
    if name not in ("scraper", "downloader", "ocr"):
        return jsonify({"error": f"Unknown process: {name}"}), 400

    running, pid = _is_running(name)
    if running:
        return jsonify({"error": f"{name} is already running (PID {pid})"}), 409

    scraper_threads = database.get_setting_int("scraper_threads", 5)
    downloader_threads = database.get_setting_int("downloader_threads", 5)

    cmds = {
        "scraper": [sys.executable, "-m", "scraper.runner", "-t", str(scraper_threads)],
        "downloader": [sys.executable, "-m", "downloader.runner", "-t", str(downloader_threads)],
        "ocr": [sys.executable, "-m", "ocr.runner"],
    }

    log_path = config.LOG_DIR / f"{name}.log"
    log_file = open(log_path, "a")
    _log_files[name] = log_file

    proc = subprocess.Popen(
        cmds[name],
        cwd=str(config.BASE_DIR),
        stdout=log_file,
        stderr=subprocess.STDOUT,
        preexec_fn=os.setsid if os.name != "nt" else None,
    )
    _processes[name] = proc
    _save_pids()

    return jsonify({"message": f"{name} started", "pid": proc.pid}), 200


@admin_bp.route("/processes/<name>/stop", methods=["POST"])
@admin_required
def stop_process(name: str):
    if name not in ("scraper", "downloader", "ocr"):
        return jsonify({"error": f"Unknown process: {name}"}), 400

    is_alive, pid = _is_running(name)
    if not is_alive or pid is None:
        return jsonify({"error": f"{name} is not running"}), 409

    # Try to kill the process group (handles both Popen-tracked and orphans)
    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        # Fall back to killing just the PID
        try:
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass

    # Wait for it to die
    proc = _processes.get(name)
    if proc and proc.poll() is None:
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                os.kill(pid, signal.SIGKILL)
            proc.wait()
    else:
        # Orphan — just wait a moment for SIGTERM to take effect
        import time
        time.sleep(1)
        if _pid_alive(pid):
            os.kill(pid, signal.SIGKILL)

    _processes.pop(name, None)

    # Close log file handle
    lf = _log_files.pop(name, None)
    if lf:
        lf.close()

    _save_pids()

    return jsonify({"message": f"{name} stopped"}), 200


@admin_bp.route("/processes/<name>/logs", methods=["GET"])
@admin_required
def get_logs(name: str):
    if name not in ("scraper", "downloader", "ocr"):
        return jsonify({"error": f"Unknown process: {name}"}), 400

    lines = request.args.get("lines", 100, type=int)
    lines = min(lines, 500)

    log_path = config.LOG_DIR / f"{name}.log"
    if not log_path.exists():
        return jsonify({"lines": [], "total_lines": 0}), 200

    # Read last N lines efficiently
    try:
        with open(log_path, "r", errors="replace") as f:
            all_lines = f.readlines()
            tail = all_lines[-lines:]
            return jsonify({
                "lines": [l.rstrip("\n") for l in tail],
                "total_lines": len(all_lines),
            }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --- Blacklist ---


@admin_bp.route("/blacklist", methods=["GET"])
@admin_required
def list_blacklist():
    with database.get_db() as conn:
        rows = conn.execute(
            "SELECT id, pattern, added_by, added_at, hit_count FROM blacklist_patterns ORDER BY added_at DESC"
        ).fetchall()

    patterns = [
        {
            "id": r["id"],
            "pattern": r["pattern"],
            "added_by": r["added_by"],
            "added_at": r["added_at"],
            "hit_count": r["hit_count"],
        }
        for r in rows
    ]
    return jsonify({"patterns": patterns}), 200


@admin_bp.route("/blacklist", methods=["POST"])
@admin_required
def add_blacklist():
    data = request.get_json(silent=True) or {}
    pattern = data.get("pattern", "").strip()

    if not pattern:
        return jsonify({"error": "Pattern is required"}), 400

    try:
        with database.get_db() as conn:
            cursor = conn.execute(
                "INSERT INTO blacklist_patterns (pattern, added_by) VALUES (?, ?) RETURNING id, added_at",
                (pattern, current_user.username),
            )
            row = cursor.fetchone()
    except Exception:
        return jsonify({"error": "Pattern already exists"}), 409

    return jsonify({
        "id": row["id"],
        "pattern": pattern,
        "added_by": current_user.username,
        "added_at": row["added_at"],
        "hit_count": 0,
    }), 201


@admin_bp.route("/blacklist/<int:pattern_id>", methods=["DELETE"])
@admin_required
def remove_blacklist(pattern_id: int):
    with database.get_db() as conn:
        deleted = conn.execute(
            "DELETE FROM blacklist_patterns WHERE id = ? RETURNING id",
            (pattern_id,),
        ).fetchone()

    if not deleted:
        return jsonify({"error": "Pattern not found"}), 404

    return jsonify({"message": "Deleted"}), 200


# --- Proxies ---


@admin_bp.route("/proxies", methods=["GET"])
@admin_required
def list_proxies():
    page = max(1, request.args.get("page", 1, type=int))
    per_page = min(200, max(1, request.args.get("per_page", 50, type=int)))
    status_filter = request.args.get("status", "all")  # all, alive, dead

    with database.get_db() as conn:
        where = ""
        params: list = []
        if status_filter == "alive":
            where = "WHERE is_alive = 1"
        elif status_filter == "dead":
            where = "WHERE is_alive = 0"

        total = conn.execute(f"SELECT COUNT(*) FROM proxies {where}", params).fetchone()[0]

        import math
        pages = max(1, math.ceil(total / per_page))
        offset = (page - 1) * per_page

        rows = conn.execute(
            f"""SELECT id, protocol, ip, port, proxy_string, is_alive,
                       success_count, failure_count, last_success_at, last_failure_at, source
                FROM proxies {where}
                ORDER BY success_count DESC, failure_count ASC
                LIMIT ? OFFSET ?""",
            params + [per_page, offset],
        ).fetchall()

        summary = conn.execute(
            """SELECT COUNT(*) as total,
                      SUM(CASE WHEN is_alive = 1 THEN 1 ELSE 0 END) as alive,
                      SUM(CASE WHEN is_alive = 0 THEN 1 ELSE 0 END) as dead,
                      SUM(success_count) as total_successes,
                      SUM(failure_count) as total_failures
               FROM proxies"""
        ).fetchone()

    proxies = [
        {
            "id": r["id"],
            "protocol": r["protocol"],
            "ip": r["ip"],
            "port": r["port"],
            "proxy_string": r["proxy_string"],
            "is_alive": bool(r["is_alive"]),
            "success_count": r["success_count"],
            "failure_count": r["failure_count"],
            "last_success_at": r["last_success_at"],
            "last_failure_at": r["last_failure_at"],
            "source": r["source"],
        }
        for r in rows
    ]

    return jsonify({
        "proxies": proxies,
        "total": total,
        "page": page,
        "pages": pages,
        "summary": {
            "total": summary["total"],
            "alive": summary["alive"] or 0,
            "dead": summary["dead"] or 0,
            "total_successes": summary["total_successes"] or 0,
            "total_failures": summary["total_failures"] or 0,
        },
    }), 200


@admin_bp.route("/proxies/refresh", methods=["POST"])
@admin_required
def refresh_proxies():
    """Fetch fresh proxies from API and reset dead proxies."""
    from scraper.proxy_manager import ProxyManager
    pm = ProxyManager()

    # Reset all dead proxies first
    with database.get_db() as conn:
        reset = conn.execute(
            "UPDATE proxies SET is_alive = 1, failure_count = 0 WHERE is_alive = 0 RETURNING id"
        ).fetchall()
        reset_count = len(reset)

    # Fetch new proxies
    new_count = pm.refresh_proxies()

    return jsonify({
        "message": f"Fetched {new_count} proxies, reset {reset_count} dead proxies",
        "fetched": new_count,
        "reset": reset_count,
    }), 200


@admin_bp.route("/proxies/reset-dead", methods=["POST"])
@admin_required
def reset_dead_proxies():
    """Reset all dead proxies back to alive."""
    with database.get_db() as conn:
        reset = conn.execute(
            "UPDATE proxies SET is_alive = 1, failure_count = 0 WHERE is_alive = 0 RETURNING id"
        ).fetchall()

    return jsonify({"message": f"Reset {len(reset)} dead proxies", "count": len(reset)}), 200


@admin_bp.route("/proxies/purge-dead", methods=["POST"])
@admin_required
def purge_dead_proxies():
    """Permanently remove all dead proxies."""
    with database.get_db() as conn:
        deleted = conn.execute("DELETE FROM proxies WHERE is_alive = 0 RETURNING id").fetchall()

    return jsonify({"message": f"Purged {len(deleted)} dead proxies", "count": len(deleted)}), 200


# --- System stats ---


@admin_bp.route("/stats", methods=["GET"])
@admin_required
def system_stats():
    with database.get_db() as conn:
        state_counts = conn.execute(
            "SELECT state, COUNT(*) as count FROM screenshots GROUP BY state"
        ).fetchall()

        total_size = conn.execute(
            "SELECT COALESCE(SUM(file_size_bytes), 0) FROM screenshots"
        ).fetchone()[0]

        proxy_stats = conn.execute(
            """SELECT COUNT(*) as total,
                      SUM(CASE WHEN is_alive = 1 THEN 1 ELSE 0 END) as alive,
                      SUM(success_count) as total_successes,
                      SUM(failure_count) as total_failures
               FROM proxies"""
        ).fetchone()

        blacklist_count = conn.execute(
            "SELECT COUNT(*) FROM blacklist_patterns"
        ).fetchone()[0]

    return jsonify({
        "screenshots": {
            "counts_by_state": {r["state"]: r["count"] for r in state_counts},
            "total_disk_bytes": total_size,
        },
        "proxies": {
            "total": proxy_stats["total"],
            "alive": proxy_stats["alive"] or 0,
            "total_successes": proxy_stats["total_successes"] or 0,
            "total_failures": proxy_stats["total_failures"] or 0,
        },
        "blacklist_patterns": blacklist_count,
    }), 200


# --- Settings ---


@admin_bp.route("/settings", methods=["GET"])
@admin_required
def get_settings():
    return jsonify({"settings": database.get_all_settings()}), 200


@admin_bp.route("/settings", methods=["PUT"])
@admin_required
def update_settings():
    data = request.get_json(silent=True) or {}
    updated = []
    for key, value in data.items():
        if not isinstance(value, str):
            value = str(value)
        database.set_setting(key, value)
        updated.append(key)
    return jsonify({"message": f"Updated {len(updated)} settings", "updated": updated}), 200


@admin_bp.route("/ocr/check-engine", methods=["POST"])
@admin_required
def check_ocr_engine():
    """Check if an OCR engine's dependencies are installed."""
    data = request.get_json(silent=True) or {}
    engine = data.get("engine", "")

    engines = {
        "doctr": {
            "packages": ["python-doctr[torch]"],
            "check": lambda: __import__("doctr"),
        },
        "easyocr": {
            "packages": ["easyocr"],
            "check": lambda: __import__("easyocr"),
        },
    }

    if engine not in engines:
        return jsonify({"error": f"Unknown engine: {engine}"}), 400

    info = engines[engine]
    try:
        info["check"]()
        return jsonify({"installed": True, "engine": engine}), 200
    except ImportError:
        return jsonify({
            "installed": False,
            "engine": engine,
            "packages": info["packages"],
        }), 200


@admin_bp.route("/ocr/rebuild", methods=["POST"])
@admin_required
def rebuild_ocr():
    """Reset all OCR results so images get re-processed with the current engine."""
    with database.get_db() as conn:
        # Reset ocr_complete back to downloaded
        r1 = conn.execute(
            """UPDATE screenshots
               SET state = 'downloaded', ocr_text = NULL, ocr_segments = NULL,
                   ocr_confidence = NULL, ocr_processed_at = NULL,
                   claimed_by = NULL, claimed_at = NULL
               WHERE state = 'ocr_complete' AND local_filename IS NOT NULL
               RETURNING id"""
        ).fetchall()

        # Also reset filtered items (they might pass with a better engine)
        r2 = conn.execute(
            """UPDATE screenshots
               SET state = 'downloaded', ocr_text = NULL, ocr_segments = NULL,
                   ocr_confidence = NULL, ocr_processed_at = NULL,
                   filter_matched_pattern = NULL,
                   claimed_by = NULL, claimed_at = NULL
               WHERE state = 'filtered' AND local_filename IS NOT NULL
               RETURNING id"""
        ).fetchall()

    total = len(r1) + len(r2)
    return jsonify({
        "message": f"Reset {total} screenshots for re-processing ({len(r1)} complete, {len(r2)} filtered)",
        "reset": total,
    }), 200


# --- Start/Stop all ---


@admin_bp.route("/processes/start-all", methods=["POST"])
@admin_required
def start_all():
    started = []
    for name in ("scraper", "downloader", "ocr"):
        running, _ = _is_running(name)
        if not running:
            # Read thread counts from settings
            scraper_threads = database.get_setting_int("scraper_threads", 5)
            downloader_threads = database.get_setting_int("downloader_threads", 5)
            ocr_enabled = database.get_setting_bool("ocr_enabled", True)

            cmds = {
                "scraper": [sys.executable, "-m", "scraper.runner", "-t", str(scraper_threads)],
                "downloader": [sys.executable, "-m", "downloader.runner", "-t", str(downloader_threads)],
                "ocr": [sys.executable, "-m", "ocr.runner"],
            }

            if name == "ocr" and not ocr_enabled:
                continue

            log_path = config.LOG_DIR / f"{name}.log"
            log_file = open(log_path, "a")
            _log_files[name] = log_file

            proc = subprocess.Popen(
                cmds[name],
                cwd=str(config.BASE_DIR),
                stdout=log_file,
                stderr=subprocess.STDOUT,
                preexec_fn=os.setsid if os.name != "nt" else None,
            )
            _processes[name] = proc
            started.append(name)

    _save_pids()
    return jsonify({"message": f"Started {', '.join(started) or 'nothing (all running)'}"}), 200


@admin_bp.route("/processes/stop-all", methods=["POST"])
@admin_required
def stop_all():
    stopped = []
    for name in ("scraper", "downloader", "ocr"):
        running, pid = _is_running(name)
        if running and pid:
            try:
                os.killpg(os.getpgid(pid), signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                try:
                    os.kill(pid, signal.SIGTERM)
                except (ProcessLookupError, PermissionError):
                    pass

            proc = _processes.get(name)
            if proc and proc.poll() is None:
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(os.getpgid(pid), signal.SIGKILL)
                    except (ProcessLookupError, PermissionError):
                        os.kill(pid, signal.SIGKILL)
                    proc.wait()
            else:
                import time as _time
                _time.sleep(1)
                if _pid_alive(pid):
                    os.kill(pid, signal.SIGKILL)

            _processes.pop(name, None)
            lf = _log_files.pop(name, None)
            if lf:
                lf.close()
            stopped.append(name)

    _save_pids()
    return jsonify({"message": f"Stopped {', '.join(stopped) or 'nothing (all stopped)'}"}), 200
