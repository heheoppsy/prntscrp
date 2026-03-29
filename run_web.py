"""Entry point for the Flask API server."""

import os
import config
from web.app import create_app

app = create_app()

if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host=config.API_HOST, port=config.API_PORT, debug=debug)
