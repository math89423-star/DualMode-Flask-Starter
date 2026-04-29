from backend.extensions import db
from backend.model.models import Item


def get_all_items():
    return Item.query.order_by(Item.created_at.desc()).all()


def create_item(title: str, description: str = '') -> Item:
    item = Item(title=title, description=description)
    db.session.add(item)
    db.session.commit()
    return item


def get_item(item_id: int) -> Item:
    return Item.query.get_or_404(item_id)
