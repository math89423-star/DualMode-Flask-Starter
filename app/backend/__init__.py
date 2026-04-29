from __future__ import annotations

from typing import Any, Type

import os
from flask import Flask
from flask_cors import CORS

from backend.config import Config
from backend.extensions import db
from backend.paths import get_frontend_dist


def create_app(config_class: Type[Any] = Config) -> Flask:
    base_dir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))

    if Config.DEPLOY_MODE == 'desktop':
        static_folder = get_frontend_dist()
    else:
        static_folder = os.path.join(base_dir, 'static')

    app = Flask(__name__, static_folder=static_folder)

    app.config.from_object(config_class)
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
    CORS(app)

    db.init_app(app)

    if Config.DEPLOY_MODE == 'desktop':
        with app.app_context():
            from backend.model.models import Item, Setting
            db.create_all()

    with app.app_context():
        from backend.routes.example import example_bp
        app.register_blueprint(example_bp, url_prefix='/api')

    @app.route('/api/health')
    def health_check():
        return {"status": "ok", "message": "DualMode Flask Starter API is running!"}

    if Config.DEPLOY_MODE == 'desktop':
        dist_dir = get_frontend_dist()

        @app.route('/')
        def serve_index():
            from flask import send_from_directory
            return send_from_directory(dist_dir, 'index.html')

        @app.route('/assets/<path:filename>')
        def serve_assets(filename):
            from flask import send_from_directory
            return send_from_directory(os.path.join(dist_dir, 'assets'), filename)

    return app
