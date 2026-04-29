from __future__ import annotations

import time
import logging

from backend.extensions import db
from backend.config import Config
from backend.model.models import Item

logger = logging.getLogger(__name__)

if Config.DEPLOY_MODE != 'desktop':
    from backend import create_app
    app = create_app()
else:
    app = None


def set_app(flask_app: object) -> None:
    global app
    app = flask_app


def process_task(item_id: int) -> None:
    with app.app_context():
        item = db.session.get(Item, item_id)

        if not item:
            logger.error(f"Item {item_id} not found")
            return

        logger.info(f"Processing item {item_id}: {item.title}")

        try:
            item.status = 'processing'
            db.session.commit()

            # --- Replace this block with your actual task logic ---
            time.sleep(2)
            item.description = f"[Processed] {item.description or ''}"
            # --- End of example logic ---

            item.status = 'completed'
            db.session.commit()
            logger.info(f"Item {item_id} completed")

        except Exception as e:
            logger.error(f"Item {item_id} failed: {str(e)}", exc_info=True)
            item.status = 'failed'
            db.session.commit()
