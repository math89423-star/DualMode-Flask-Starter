from flask import Blueprint, request, jsonify
from backend.extensions import db, task_queue
from backend.model.models import Item

example_bp = Blueprint('example', __name__)


@example_bp.route('/items', methods=['GET'])
def list_items():
    items = Item.query.order_by(Item.created_at.desc()).all()
    return jsonify([
        {
            'id': item.id,
            'title': item.title,
            'description': item.description,
            'status': item.status,
            'created_at': item.created_at.isoformat()
        }
        for item in items
    ])


@example_bp.route('/items', methods=['POST'])
def create_item():
    data = request.get_json()
    if not data or not data.get('title'):
        return jsonify({'error': 'title is required'}), 400

    item = Item(
        title=data['title'],
        description=data.get('description', '')
    )
    db.session.add(item)
    db.session.commit()

    return jsonify({
        'id': item.id,
        'title': item.title,
        'status': item.status
    }), 201


@example_bp.route('/items/<int:item_id>', methods=['GET'])
def get_item(item_id):
    item = Item.query.get_or_404(item_id)
    return jsonify({
        'id': item.id,
        'title': item.title,
        'description': item.description,
        'status': item.status,
        'created_at': item.created_at.isoformat()
    })


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
