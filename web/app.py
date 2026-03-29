"""Flask application factory."""

import os

from flask import Flask, send_from_directory, jsonify
from flask_cors import CORS
from flask_login import LoginManager

import config
import database


def create_app() -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__)
    app.config["SECRET_KEY"] = config.SECRET_KEY
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_HTTPONLY"] = True

    # CORS for SvelteKit dev server
    CORS(app, origins=[config.FRONTEND_DEV_URL], supports_credentials=True)

    # Flask-Login setup
    login_manager = LoginManager()
    login_manager.init_app(app)

    from web.auth import User

    @login_manager.user_loader
    def load_user(username: str):
        with database.get_db() as conn:
            row = conn.execute(
                "SELECT username, password_hash, role, is_active FROM users WHERE username = ?",
                (username,),
            ).fetchone()
        if row and row["is_active"]:
            return User(row["username"], row["role"])
        return None

    @login_manager.unauthorized_handler
    def unauthorized():
        return jsonify({"error": "Authentication required"}), 401

    # Serve downloaded images
    @app.route("/api/images/<path:filename>")
    def serve_image(filename):
        return send_from_directory(str(config.DOWNLOADS_DIR), filename)

    # Register blueprints
    from web.auth import auth_bp
    from web.routes.gallery import gallery_bp
    from web.routes.search import search_bp
    from web.routes.admin import admin_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(gallery_bp)
    app.register_blueprint(search_bp)
    app.register_blueprint(admin_bp)

    # Initialize database
    database.init_db()

    return app
