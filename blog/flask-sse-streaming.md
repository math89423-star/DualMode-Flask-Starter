# 不用 FastAPI，Flask 也能优雅地流式推送 —— SSE 实战指南

> 当你的后台任务要跑 30 秒，用户盯着一个转圈的 loading 等结果——这体验谁受得了？
>
> 本文带你用 Flask（同步框架）实现 Server-Sent Events 流式推送，不需要 async，不需要换框架，从协议原理到生产可用的完整方案。

---

## §1 为什么需要 SSE

传统的 HTTP 请求是"一问一答"：客户端发请求，服务端返回结果，连接关闭。但有些场景天然需要服务端主动推送：

- AI 大模型逐字输出（ChatGPT 风格的打字机效果）
- 后台任务进度通知（文件处理、数据导入）
- 实时日志流

常见的解决方案有三种：

| 方案 | 原理 | 适用场景 |
|------|------|---------|
| **轮询** | 客户端每隔 N 秒请求一次 | 简单但浪费资源，延迟高 |
| **WebSocket** | 全双工长连接 | 聊天室、协同编辑等双向通信 |
| **SSE** | 服务端单向推送的长连接 | 进度通知、流式输出等单向场景 |

SSE 是最被低估的那个。它基于普通 HTTP，不需要特殊协议升级，浏览器原生支持 `EventSource` API，实现成本远低于 WebSocket。对于"服务端向客户端推数据"这个需求，SSE 就是最合适的工具。

---

## §2 SSE 协议：其实就是一个不关闭的 HTTP 响应

SSE 的协议简单到令人意外。本质上就是：

1. 服务端返回 `Content-Type: text/event-stream`
2. 响应体不关闭，持续写入数据
3. 每条消息以 `\n\n`（两个换行）分隔

一条 SSE 消息长这样：

```
data: {"status": "processing", "progress": 42}

```

注意最后有一个空行（两个 `\n`），这是消息的结束标记。

SSE 还支持几个可选字段：

```
id: 1001
event: progress
data: {"percent": 42}

```

- `id` — 消息 ID，断线重连时浏览器会通过 `Last-Event-ID` 头告诉服务端从哪里续传
- `event` — 事件类型，前端可以用 `addEventListener('progress', ...)` 监听特定类型
- `data` — 消息体，可以是任意字符串（通常是 JSON）

还有一个特殊的注释行，以冒号开头：

```
: this is a comment

```

浏览器会忽略注释行，但它能防止连接因为长时间没有数据而被中间代理（Nginx、CDN）断开。这就是"心跳"的原理。

---

## §3 最朴素的 Flask SSE：五行代码

Flask 的 `Response` 对象支持传入一个生成器（generator），Flask 会逐个 yield 地把数据写入响应体，而不是等所有数据准备好再一次性返回。这正好是 SSE 需要的。

```python
from flask import Flask, Response
import time

app = Flask(__name__)

@app.route('/stream')
def stream():
    def generate():
        for i in range(10):
            yield f"data: step {i}\n\n"
            time.sleep(1)
    return Response(generate(), mimetype='text/event-stream')
```

跑起来，用 `curl` 测试：

```bash
curl -N http://127.0.0.1:5000/stream
```

你会看到每秒输出一行 `data: step N`。

这就是 Flask SSE 的全部秘密：**generator + `text/event-stream`**。没有魔法，没有第三方库。

但这个朴素版本有几个致命问题：

1. **数据从哪来？** 这里是 `for i in range(10)` 硬编码的，真实场景中数据来自后台任务，而后台任务跑在另一个线程甚至另一个进程里
2. **连接管理呢？** 客户端断开了怎么办？长时间没数据连接会不会被掐？
3. **怎么知道该结束了？** 任务完成后流应该自动关闭

接下来我们逐个解决。

---

## §4 核心问题：后台任务怎么把数据"喂"给 SSE

这是整个方案的关键。SSE 的 generator 在一个请求线程里跑，后台任务在另一个线程（或进程）里跑。它们之间需要一个通信管道。

答案是 **Pub/Sub（发布/订阅）模式**。

```
后台任务（Publisher）          通信管道           SSE 端点（Subscriber）
      │                         │                      │
      ├── publish(channel, msg) │                      │
      │                    ────→│                      │
      │                         │──→ get_message() ───→│
      │                         │                      ├── yield "data: msg\n\n"
      │                         │                      │
```

在生产环境中，这个"通信管道"通常是 Redis 的 Pub/Sub 功能。但在桌面模式下（没有 Redis），我们用一个内存实现来替代。关键是：**SSE 端点的代码不需要知道底层是 Redis 还是内存**。

我们项目中的做法是，在 `extensions.py` 里根据运行模式注入不同实现：

```python
# extensions.py
if Config.DEPLOY_MODE == 'desktop':
    from backend.memory_backend import MemoryRedis
    redis_client = MemoryRedis()       # 内存版 Pub/Sub
else:
    import redis
    redis_client = redis.from_url(Config.REDIS_URL, decode_responses=True)  # 真 Redis
```

上层代码只用 `redis_client`，不关心它是什么：

```python
# 发布端（后台任务）
redis_client.publish("stream:task:1", '{"status": "processing"}')

# 订阅端（SSE generator）
pubsub = redis_client.pubsub()
pubsub.subscribe("stream:task:1")
msg = pubsub.get_message(timeout=1.0)
```

---

## §5 完整实现：三个文件串起来

### 5.1 后台任务发布进度事件

`worker_engine.py` 是后台任务的执行器。每次状态变更时，除了写数据库，还要通过 Pub/Sub 发布一条事件：

```python
import json
from backend.extensions import db, redis_client
from backend.config import RedisKeyManager

def _publish_status(item_id: int, status: str, message: str = "") -> None:
    channel = RedisKeyManager.stream_channel(item_id)  # → "stream:task:{id}"
    payload = json.dumps({"item_id": item_id, "status": status, "message": message})
    redis_client.publish(channel, payload)

def process_task(item_id: int) -> None:
    with app.app_context():
        item = db.session.get(Item, item_id)

        item.status = 'processing'
        db.session.commit()
        _publish_status(item_id, "processing", f"Started: {item.title}")

        # ... 执行实际业务逻辑 ...

        item.status = 'completed'
        db.session.commit()
        _publish_status(item_id, "completed", f"Item {item_id} done")
```

注意 `RedisKeyManager.stream_channel(item_id)` 生成的 channel 名是 `stream:task:{id}`。每个任务有自己的 channel，互不干扰。

### 5.2 SSE 生成器：订阅、推送、清理

`utils/sse.py` 是 SSE 的核心。它订阅指定 channel，把收到的消息格式化为 SSE 协议并 yield 出去：

```python
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
                elapsed = 0.0  # 收到消息，重置超时计时器
                try:
                    payload = json.loads(data)
                    if payload.get("status") in ("completed", "failed"):
                        break  # 终态，主动关闭流
                except (json.JSONDecodeError, AttributeError):
                    pass
            else:
                elapsed += poll_interval
                if elapsed % heartbeat < poll_interval:
                    yield ": heartbeat\n\n"  # 心跳保活
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
```

这段代码里有几个值得展开说的设计决策，下一节详细聊。

### 5.3 路由端点：把 generator 交给 Flask

```python
from flask import Response
from backend.utils.sse import sse_stream
from backend.config import RedisKeyManager

@example_bp.route('/items/<int:item_id>/stream', methods=['GET'])
def stream_item(item_id):
    Item.query.get_or_404(item_id)
    channel = RedisKeyManager.stream_channel(item_id)
    return Response(
        sse_stream(channel),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'}
    )
```

两个 header 的作用：
- `Cache-Control: no-cache` — 告诉浏览器和代理不要缓存这个响应
- `X-Accel-Buffering: no` — 告诉 Nginx 不要缓冲响应（否则 Nginx 会攒一批数据再发，SSE 就不"实时"了）

---

## §6 三个必须处理的工程细节

### 6.1 心跳保活

SSE 连接本质上是一个长时间打开的 HTTP 响应。如果长时间没有数据传输，中间的代理服务器（Nginx、云厂商的 LB）可能会认为连接已死并主动断开。

解决方案是定期发送 SSE 注释行：

```python
yield ": heartbeat\n\n"
```

浏览器会忽略注释行，但 TCP 连接上有数据流过，代理就不会断开。我们设置的间隔是 15 秒，这个值在大多数代理的默认超时（60 秒）之内。

### 6.2 超时断开

如果后台任务异常退出，没有发布 `completed` 或 `failed` 事件，SSE 连接就会永远挂着。这会占用服务器线程，最终耗尽连接池。

所以我们设置了一个 30 秒的超时：如果 30 秒内没有收到任何消息（心跳不算），流自动关闭。每次收到真实消息时，计时器重置为 0。

```python
if msg and msg.get("type") == "message":
    # ...
    elapsed = 0.0  # 重置
else:
    elapsed += poll_interval
```

### 6.3 终态自动关闭

当后台任务完成（`completed`）或失败（`failed`）时，SSE 流应该主动关闭，而不是等超时。这样客户端能立即知道"结束了"，而不是等 30 秒后连接断开才知道。

```python
payload = json.loads(data)
if payload.get("status") in ("completed", "failed"):
    break
```

`break` 跳出 `while` 循环后，`finally` 块会执行 `unsubscribe()` 和 `close()` 清理订阅。

---

## §7 前端怎么接：EventSource API

浏览器原生提供了 `EventSource` API，专门用于接收 SSE：

```javascript
// 发起处理请求
fetch('/api/items/1/process', { method: 'POST' });

// 监听进度
const es = new EventSource('/api/items/1/stream');

es.onmessage = (event) => {
    const data = JSON.parse(event.data);
    console.log(`Status: ${data.status}, Message: ${data.message}`);

    if (data.status === 'completed' || data.status === 'failed') {
        es.close();  // 服务端关了流，客户端也关闭连接
    }
};

es.onerror = (event) => {
    console.error('SSE connection error');
    es.close();
};
```

`EventSource` 有一个很好的特性：**自动重连**。如果连接意外断开，浏览器会自动尝试重新连接。如果你不想要这个行为（比如任务已经完成了），记得调用 `es.close()`。

---

## §8 完整数据流：从点击按钮到看到结果

把所有模块串起来，一次完整的交互是这样的：

```
浏览器                        Flask                    后台任务
  │                             │                         │
  ├─ POST /items/1/process ───→ │                         │
  │                             ├─ enqueue(process_task) →│
  │ ◄── 200 {"status":"queued"} │                         │
  │                             │                         │
  ├─ GET /items/1/stream ─────→ │                         │
  │    (EventSource 连接)       ├─ subscribe(channel)     │
  │                             │                         │
  │                             │                         ├─ status = "processing"
  │                             │    ◄── publish() ───────┤
  │ ◄── data: {"status":       │                         │
  │      "processing"} ────────┤                         │
  │                             │                         ├─ (执行业务逻辑...)
  │ ◄── : heartbeat ──────────┤  (15s 无消息时)          │
  │                             │                         │
  │                             │                         ├─ status = "completed"
  │                             │    ◄── publish() ───────┤
  │ ◄── data: {"status":       │                         │
  │      "completed"} ─────────┤                         │
  │                             ├─ unsubscribe, close     │
  ├─ es.close() ──────────────→│                         │
  │  (连接关闭)                 │                         │
```

---

## §9 "为什么不直接用 FastAPI？"

这是写这篇文章一定会被问到的问题。坦率地说：

**FastAPI 的 SSE 体验确实更好。** `async def` + `StreamingResponse` + `async generator` 是天然的流式模型，不需要线程，不需要 PubSub 中转，代码更直观。

但"更好"不等于"必须换"。以下几个场景，Flask + SSE 是更务实的选择：

**1. 已有 Flask 项目加功能**

你的项目已经有 20 个路由、一套 Flask-SQLAlchemy 的模型层、一堆 Blueprint。为了一个 SSE 端点把整个项目迁移到 FastAPI？ORM 层要从同步换成 async session，所有 `db.session` 调用都要改，测试要重写。这个迁移成本远大于在 Flask 里加几十行 SSE 代码。

**2. 需要打包成桌面应用**

PyInstaller 打包 Flask 是成熟路径，社区踩坑经验丰富。FastAPI + uvicorn 的打包问题明显更多——uvicorn 的 event loop 和 PyInstaller 的冻结机制有冲突，libuv 的 C 扩展在打包时经常出问题。

**3. 同步代码更容易理解和调试**

async/await 引入了新的心智负担：哪些库是 async 兼容的？忘了 `await` 会怎样？数据库驱动要换成 async 版本吗？对于初中级团队，同步代码的可维护性优势不可忽视。

**总结：** 如果你从零开始一个以流式输出为核心的项目（比如 AI 应用的后端），FastAPI 是更好的起点。但如果你在已有的 Flask 项目上加 SSE 能力，本文的方案就是最小代价的正确做法。

---

## §10 总结

Flask 做 SSE 的核心就三件事：

1. **generator + `text/event-stream`** — Flask 原生支持，不需要任何第三方库
2. **Pub/Sub 做跨线程通信** — 后台任务 publish，SSE generator subscribe，解耦干净
3. **心跳 + 超时 + 终态检测** — 三个工程细节决定了方案能不能上生产

完整代码在 [DualMode-Flask-Starter](https://github.com/math89423-star/DualMode-Flask-Starter) 项目中，核心文件：

- `app/backend/utils/sse.py` — SSE 生成器
- `app/backend/worker_engine.py` — 后台任务 + 事件发布
- `app/backend/routes/example.py` — SSE 路由端点
- `app/backend/memory_backend.py` — 内存版 Pub/Sub（Desktop 模式替身）

如果这篇文章对你有帮助，给项目点个 star 就是最好的支持。
