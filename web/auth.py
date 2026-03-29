"""Authentication blueprint and User model."""

from functools import wraps

from flask import Blueprint, request, jsonify
from flask_login import UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

import database

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


class User(UserMixin):
    """Flask-Login user backed by the users table."""

    def __init__(self, username: str, role: str = "user"):
        self.id = username
        self.username = username
        self.role = role

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    def to_dict(self) -> dict:
        return {"username": self.username, "role": self.role}


def admin_required(fn):
    """Decorator that requires the current user to be an admin."""
    @wraps(fn)
    @login_required
    def wrapper(*args, **kwargs):
        if not current_user.is_admin:
            return jsonify({"error": "Admin access required"}), 403
        return fn(*args, **kwargs)
    return wrapper


# --- Routes ---


@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400

    with database.get_db() as conn:
        row = conn.execute(
            "SELECT username, password_hash, role, is_active FROM users WHERE username = ?",
            (username,),
        ).fetchone()

    if not row or not row["is_active"]:
        return jsonify({"error": "Invalid credentials"}), 401

    if not check_password_hash(row["password_hash"], password):
        return jsonify({"error": "Invalid credentials"}), 401

    user = User(row["username"], row["role"])
    login_user(user, remember=True)

    # Update last login timestamp
    with database.get_db() as conn:
        conn.execute(
            "UPDATE users SET last_login_at = strftime('%Y-%m-%dT%H:%M:%f', 'now') WHERE username = ?",
            (username,),
        )

    return jsonify({"user": user.to_dict()}), 200


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    return jsonify({"message": "Logged out"}), 200


@auth_bp.route("/me", methods=["GET"])
@login_required
def me():
    return jsonify({"user": current_user.to_dict()}), 200


@auth_bp.route("/users", methods=["GET"])
@admin_required
def list_users():
    with database.get_db() as conn:
        rows = conn.execute(
            "SELECT username, role, is_active, created_at, last_login_at FROM users ORDER BY created_at"
        ).fetchall()

    users = [
        {
            "username": r["username"],
            "role": r["role"],
            "is_active": bool(r["is_active"]),
            "created_at": r["created_at"],
            "last_login_at": r["last_login_at"],
        }
        for r in rows
    ]
    return jsonify({"users": users}), 200


@auth_bp.route("/users", methods=["POST"])
@admin_required
def create_user():
    data = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")
    role = data.get("role", "user")

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400

    if role not in ("user", "admin"):
        return jsonify({"error": "Role must be 'user' or 'admin'"}), 400

    password_hash = generate_password_hash(password)

    try:
        with database.get_db() as conn:
            conn.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                (username, password_hash, role),
            )
    except Exception:
        return jsonify({"error": "Username already exists"}), 409

    return jsonify({"user": {"username": username, "role": role}}), 201


@auth_bp.route("/change-password", methods=["POST"])
@login_required
def change_password():
    data = request.get_json(silent=True) or {}
    current_pw = data.get("current_password", "")
    new_pw = data.get("new_password", "")

    if not current_pw or not new_pw:
        return jsonify({"error": "Both current and new password are required"}), 400

    if len(new_pw) < 6:
        return jsonify({"error": "New password must be at least 6 characters"}), 400

    with database.get_db() as conn:
        row = conn.execute(
            "SELECT password_hash FROM users WHERE username = ?",
            (current_user.username,),
        ).fetchone()

    if not row or not check_password_hash(row["password_hash"], current_pw):
        return jsonify({"error": "Current password is incorrect"}), 401

    with database.get_db() as conn:
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE username = ?",
            (generate_password_hash(new_pw), current_user.username),
        )

    return jsonify({"message": "Password changed"}), 200


@auth_bp.route("/users/<username>", methods=["DELETE"])
@admin_required
def delete_user(username: str):
    if username == current_user.username:
        return jsonify({"error": "Cannot delete yourself"}), 400

    with database.get_db() as conn:
        deleted = conn.execute(
            "DELETE FROM users WHERE username = ? RETURNING username",
            (username,),
        ).fetchone()

    if not deleted:
        return jsonify({"error": "User not found"}), 404

    return jsonify({"message": f"User {username} deleted"}), 200
