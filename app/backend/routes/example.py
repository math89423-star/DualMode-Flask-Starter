from flask import Blueprint, request, jsonify, Response
from backend.extensions import db, task_queue
from backend.model.models import Item
from backend.schemas import ItemCreate, ItemResponse
from backend.config import RedisKeyManager
from backend.utils.validation import validate_request
from backend.utils.sse import sse_stream

example_bp = Blueprint('example', __name__)


@example_bp.route('/items', methods=['GET'])
def list_items():
    items = Item.query.order_by(Item.created_at.desc()).all()
    return jsonify([ItemResponse.model_validate(item).model_dump(mode="json") for item in items])


@example_bp.route('/items', methods=['POST'])
@validate_request(ItemCreate)
def create_item(body: ItemCreate):
    item = Item(title=body.title, description=body.description)
    db.session.add(item)
    db.session.commit()
    return jsonify(ItemResponse.model_validate(item).model_dump(mode="json")), 201


@example_bp.route('/items/<int:item_id>', methods=['GET'])
def get_item(item_id):
    item = Item.query.get_or_404(item_id)
    return jsonify(ItemResponse.model_validate(item).model_dump(mode="json"))


@example_bp.route('/items/<int:item_id>/process', methods=['POST'])
def process_item(item_id):
    item = Item.query.get_or_404(item_id)
    if item.status == 'processing':
        return jsonify({'error': 'item is already being processed'}), 409

    item.status = 'queued'
    db.session.commit()

    task_queue.enqueue('backend.worker_engine.process_task', item.id)

    return jsonify({
        'id': item.id,
        'status': item.status,
        'message': 'item queued for processing'
    })


@example_bp.route('/items/<int:item_id>/stream', methods=['GET'])
def stream_item(item_id):
    Item.query.get_or_404(item_id)
    channel = RedisKeyManager.stream_channel(item_id)
    return Response(
        sse_stream(channel),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'}
    )
