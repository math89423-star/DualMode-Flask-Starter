import os
from redis import Redis
from rq import Worker

redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
redis_conn = Redis.from_url(redis_url)


def recover_orphaned_tasks():
    from backend import create_app
    from backend.extensions import db
    from backend.model.models import Item

    app = create_app()
    with app.app_context():
        orphaned = Item.query.filter(Item.status == 'processing').all()
        if orphaned:
            for item in orphaned:
                item.status = 'failed'
            db.session.commit()
            print(f"[Worker Recovery] Marked {len(orphaned)} orphaned items as failed")


if __name__ == '__main__':
    recover_orphaned_tasks()
    worker = Worker(['tasks'], connection=redis_conn)
    worker.work()
