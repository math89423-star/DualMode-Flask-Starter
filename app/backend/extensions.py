from flask_sqlalchemy import SQLAlchemy
from concurrent.futures import ThreadPoolExecutor
from backend.config import Config

db = SQLAlchemy()

executor = ThreadPoolExecutor(max_workers=Config.MAX_WORKERS, thread_name_prefix="Worker")

if Config.DEPLOY_MODE == 'desktop':
    from backend.memory_backend import MemoryRedis
    from backend.memory_queue import MemoryQueue

    redis_client = MemoryRedis()
    rq_redis = None
    task_queue = MemoryQueue()
else:
    import redis
    from rq import Queue

    rq_redis = redis.from_url(Config.REDIS_URL)
    task_queue = Queue('tasks', connection=rq_redis, default_timeout=3600)

    redis_client = redis.from_url(Config.REDIS_URL, decode_responses=True)
