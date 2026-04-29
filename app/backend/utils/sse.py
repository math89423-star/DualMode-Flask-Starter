import json
from typing import Generator
from backend.extensions import redis_client


def sse_stream(channel: str, timeout: float = 30.0, heartbeat: float = 15.0) -> Generator[str, None, None]:
    pubsub = redis_client.pubsub()
    pubsub.subscribe(channel)
    elapsed = 0.0
    poll_interval = 1.0
    try:
        while elapsed < timeout:
            msg = pubsub.get_message(timeout=poll_interval)
            if msg and msg.get("type") == "message":
                data = msg["data"]
                if isinstance(data, bytes):
                    data = data.decode("utf-8")
                yield format_sse(data)
                elapsed = 0.0
                try:
                    payload = json.loads(data)
                    if payload.get("status") in ("completed", "failed"):
                        break
                except (json.JSONDecodeError, AttributeError):
                    pass
            else:
                elapsed += poll_interval
                if elapsed % heartbeat < poll_interval:
                    yield ": heartbeat\n\n"
    finally:
        pubsub.unsubscribe()
        pubsub.close()


def format_sse(data: str, event: str | None = None, id: str | None = None) -> str:
    lines = []
    if id:
        lines.append(f"id: {id}")
    if event:
        lines.append(f"event: {event}")
    lines.append(f"data: {data}")
    return "\n".join(lines) + "\n\n"
