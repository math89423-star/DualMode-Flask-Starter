# Architecture

本文档描述 DualMode Flask Starter 的架构设计、模式切换机制和各层职责。

## 设计理念

核心问题：同一个 Flask 应用，如何既能打包成 Windows 桌面程序（零依赖、双击即用），又能部署为 Linux 容器集群（MySQL + Redis + 多 Worker）？

解法：**抽象层隔离基础设施差异**。业务代码只依赖统一接口（`redis_client`、`task_queue`、`db`），由 `extensions.py` 在启动时根据模式注入不同实现。上层代码不需要、也不应该出现 `if desktop / server` 的分支。

```
┌─────────────────────────────────────────────────┐
│                  业务代码层                        │
│         routes / services / worker_engine        │
├─────────────────────────────────────────────────┤
│                  统一接口层                        │
│       db (SQLAlchemy)  ·  redis_client  ·        │
│       task_queue  ·  executor                    │
├──────────────────────┬──────────────────────────┤
│    Desktop 实现       │      Server 实现          │
│  SQLite              │  MySQL 8.0               │
│  MemoryRedis         │  Redis 7.0               │
│  MemoryQueue         │  RQ + Redis              │
│  Flask dev server    │  Gunicorn + Nginx        │
└──────────────────────┴──────────────────────────┘
```

## 模式检测

模式检测发生在 `config.py` 的模块加载阶段，早于 Flask app 创建：

```
DEPLOY_MODE 环境变量
       │
       ▼
  ┌─ "desktop" ──→ Desktop 模式
  │
  ├─ "server"  ──→ Server 模式
  │
  └─ "auto"    ──→ sys.platform == "win32"?
                        ├─ Yes → Desktop
                        └─ No  → Server
```

检测结果存储在 `Config.DEPLOY_MODE`，后续所有条件分支都读取这个值。整个应用中只有以下文件包含模式分支逻辑：

| 文件 | 分支内容 |
|------|---------|
| `config.py` | 数据库 URI（SQLite vs MySQL）、连接池配置、监听地址 |
| `extensions.py` | 导入 MemoryRedis/MemoryQueue 或 redis/rq |
| `__init__.py` | 静态文件目录、SQLite 建表、前端路由 |
| `main.py` | 启动 Worker 线程 + 打开浏览器，或绑定 0.0.0.0 |
| `models.py` | LONGTEXT 类型适配 |
| `worker_engine.py` | Server 模式下自建 app context |

业务代码（routes、services）不包含任何模式判断。

## 启动流程

### Desktop 模式

```
main.py
  │
  ├─ create_app()
  │    ├─ Config: SQLite URI, 127.0.0.1
  │    ├─ extensions: MemoryRedis + MemoryQueue
  │    ├─ db.create_all() (SQLite 自动建表)
  │    ├─ 注册 Blueprint
  │    └─ 注册前端静态路由 (/, /assets/*)
  │
  ├─ task_queue.start_worker(app)
  │    └─ 启动 daemon 线程，循环消费队列
  │
  ├─ webbrowser.open() (仅 PyInstaller 打包后)
  │
  └─ app.run(127.0.0.1:5000, threaded=True)
```

### Server 模式

```
docker-compose up
  │
  ├─ MySQL 容器 (健康检查通过后)
  ├─ Redis 容器
  ├─ Backend 容器
  │    └─ Gunicorn → main.py
  │         ├─ create_app()
  │         │    ├─ Config: MySQL URI, 0.0.0.0
  │         │    ├─ extensions: redis + rq.Queue
  │         │    └─ 注册 Blueprint
  │         └─ app.run(0.0.0.0:5000)
  │
  ├─ RQ Worker 容器 (run_worker.py)
  │    └─ 独立进程消费 Redis 队列
  │
  └─ Nginx 容器
       └─ 反向代理 :80 → backend:5000
           + 静态文件直接 serve
```

## 核心模块详解

### extensions.py — 切换枢纽

这是整个双模式架构的关键文件。它在模块加载时根据 `Config.DEPLOY_MODE` 执行条件导入，对外暴露四个统一接口：

- **`db`** — SQLAlchemy 实例，通过 Config 中不同的 `SQLALCHEMY_DATABASE_URI` 连接 SQLite 或 MySQL
- **`redis_client`** — MemoryRedis 实例或真实 Redis 连接（`decode_responses=True`）
- **`task_queue`** — MemoryQueue 实例或 RQ Queue 实例，都支持 `.enqueue(dotted_path, *args)`
- **`executor`** — ThreadPoolExecutor，两种模式共用

### memory_backend.py — MemoryRedis

线程安全的 Redis 内存替代品，用于 Desktop 模式。实现了业务代码实际使用的 Redis 子集：

- **KV 操作**：`get`, `set`, `setex`, `exists`, `delete`
- **Hash 操作**：`hset`, `hgetall`, `hlen`
- **Set 操作**：`sadd`, `smembers`
- **Pub/Sub**：`publish`, `pubsub()` → `subscribe`, `get_message`, `unsubscribe`
- **TTL 管理**：`setex` 设置过期时间，读取时惰性清理

所有操作通过 `threading.Lock` 保证线程安全。Pub/Sub 通过 `queue.Queue` 实现订阅者间的消息分发。

### memory_queue.py — MemoryQueue

RQ 的线程级替代品。核心机制：

1. `enqueue(func_path, *args)` 将 `(dotted_path, args)` 元组放入 `queue.Queue`
2. Worker 线程（daemon）循环取出任务
3. 通过 `importlib.import_module` + `getattr` 动态解析点分路径为可调用函数
4. 在 Flask `app_context()` 中执行任务

与 RQ 的 API 兼容点：`enqueue()` 接受字符串形式的函数路径，这使得路由层的调用代码在两种模式下完全一致。

### paths.py — PyInstaller 路径兼容

PyInstaller 打包后，代码从临时目录 `sys._MEIPASS` 运行，而数据文件需要写在 EXE 所在目录。`paths.py` 区分两种路径：

- **`get_base_dir()`** — 代码/资源所在目录（打包后为 `_MEIPASS`，开发时为 `app/`）
- **`get_runtime_dir()`** — 运行时数据目录（打包后为 EXE 所在目录，开发时为 `app/`）
- **`get_data_dir()`** — SQLite 数据库存放目录（`runtime_dir/data/`）
- **`get_upload_dir()`** — 上传文件目录（`runtime_dir/uploads/`）
- **`get_frontend_dist()`** — 前端构建产物目录（`base_dir/frontend/dist/`）

### config.py — 双模式配置

`Config` 类在类体中使用条件语句，根据模式设置不同的：

- 数据库连接 URI 和连接池参数
- 监听地址（`127.0.0.1` vs `0.0.0.0`）

`WorkerConfig` 提供任务重试策略配置。`RedisKeyManager` 集中管理 Redis key 的命名规范。

### worker_engine.py — 后台任务处理器

示例任务处理器，演示了后台任务的标准模式：

1. 通过 ID 从数据库加载实体
2. 更新状态为 `processing`
3. 执行业务逻辑
4. 更新状态为 `completed` 或 `failed`

Server 模式下，该模块在 RQ Worker 进程中运行，需要自行创建 Flask app 以获取数据库连接。Desktop 模式下，由 MemoryQueue 在 `app_context()` 中调用，app 实例通过 `set_app()` 注入。

## 数据库适配

SQLAlchemy 作为 ORM 层天然支持多数据库，但仍有两处需要显式适配：

1. **字段类型** — MySQL 的 `LONGTEXT` 在 SQLite 中不存在。`models.py` 通过条件变量解决：
   ```python
   LONGTEXT = db.Text if desktop else mysql.LONGTEXT
   ```

2. **连接池** — SQLite 不支持连接池，`Config` 中 Desktop 模式的 `SQLALCHEMY_ENGINE_OPTIONS` 为空字典。

3. **建表方式** — Desktop 模式在 `create_app()` 中调用 `db.create_all()` 自动建表；Server 模式依赖数据库初始化脚本或迁移工具。

## Docker 编排

Server 模式由 4 个容器组成：

```
                    :80
                     │
               ┌─────┴─────┐
               │   Nginx    │  反向代理 + 静态文件
               └─────┬─────┘
                     │ :5000
               ┌─────┴─────┐
               │  Backend   │  Gunicorn + Flask
               └──┬─────┬──┘
                  │     │
          ┌───────┘     └───────┐
          │                     │
    ┌─────┴─────┐         ┌────┴────┐
    │   MySQL   │         │  Redis  │
    │   :3306   │         │  :6379  │
    └───────────┘         └─────────┘
```

- MySQL 配置了健康检查，Backend 在 MySQL 就绪后才启动
- Redis 使用自定义配置文件（`app/config/redis.conf`）
- 数据通过 volume 持久化（`mysql_data/`、`redis_data/`）
- 日志和上传文件映射到宿主机（`logs/`、`uploads/`）

## 扩展架构时的注意事项

**新增基础设施依赖**：如果新功能需要一个 Desktop 模式下不存在的服务（如 Elasticsearch），应在 `memory_backend.py` 中添加对应的内存替身，并在 `extensions.py` 中做条件导入，保持业务代码的模式无关性。

**新增数据模型**：使用 `LONGTEXT` 变量处理大文本字段。避免使用 MySQL 专有的 SQL 语法，尽量通过 SQLAlchemy ORM 操作数据库。

**新增后台任务**：任务函数必须接受可序列化的参数（ID 而非 ORM 对象），因为 RQ 会跨进程传递参数。在函数内部通过 ID 重新查询数据库获取实体。

**前端集成**：构建产物放在 `app/frontend/dist/`。Desktop 模式由 Flask 的 `send_from_directory` 提供服务，Server 模式由 Nginx 直接 serve 静态文件。两种模式下 API 路径一致（`/api/*`），前端代码无需区分。
