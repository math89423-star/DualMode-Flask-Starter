# DualMode Flask Starter

一套代码，两个灵魂。

DualMode Flask Starter 是一个自适应双模式 Flask 开发框架。同一份代码库根据运行平台自动切换基础设施：Windows 上以单机桌面应用运行（SQLite + 内存队列），Linux/Docker 上以分布式服务运行（MySQL + Redis + RQ）。业务代码无需任何条件分支，基础设施差异被完全封装在抽象层之下。

## 双模式对照

| 层面 | Desktop 模式 | Server 模式 |
|------|-------------|-------------|
| 数据库 | SQLite（本地文件） | MySQL 8.0（容器化） |
| 任务队列 | MemoryQueue（线程级） | RQ + Redis（进程级） |
| 缓存 / PubSub | MemoryRedis（内存） | Redis 7.0 |
| Web 服务器 | Flask 内置 dev server | Gunicorn + Nginx |
| 前端托管 | Flask 直接 serve | Nginx 反向代理 |
| 打包产物 | PyInstaller → 单目录 EXE | Docker Compose → 4 容器 |

模式由 `DEPLOY_MODE` 环境变量控制。设为 `auto`（默认）时，框架通过 `sys.platform` 自动判断：`win32` → desktop，其余 → server。

## 快速开始

### Desktop 模式（Windows）

```bash
cd app
pip install -r requirements.txt
python main.py
# → http://127.0.0.1:5000
```

无需安装 MySQL 或 Redis，所有依赖在内存中模拟。

### Server 模式（Docker）

```bash
bash start.sh up
# → http://localhost
```

首次运行会从 `.env.server.example` 生成 `.env`，编辑数据库密码后重新执行即可。

### Server 模式（裸机）

```bash
bash start.sh init    # 创建 venv，安装依赖
# 编辑 .env，确保 MySQL 和 Redis 已运行
bash start.sh run     # 启动后端
```

## 构建 Windows EXE

```bash
build_exe.bat
# 产物: dist\DualModeStarter\
# 运行: dist\DualModeStarter\DualModeStarter.exe
```

构建脚本会自动将 `.env.desktop.example` 复制为 EXE 目录下的 `.env`。PyInstaller 配置已排除 MySQL、Redis、Gunicorn 等 Server 模式专用依赖。

## 项目结构

```
├── app/
│   ├── main.py                     # 入口：模式感知的启动逻辑
│   ├── run_worker.py               # RQ Worker 入口（仅 Server 模式）
│   ├── requirements.txt
│   ├── Dockerfile.backend
│   ├── backend/
│   │   ├── __init__.py             # create_app() 工厂
│   │   ├── config.py               # 双模式配置 + 平台自动检测
│   │   ├── extensions.py           # 条件导入枢纽：统一接口切换
│   │   ├── memory_backend.py       # MemoryRedis — Redis 的内存替身
│   │   ├── memory_queue.py         # MemoryQueue — RQ 的线程替身
│   │   ├── paths.py                # PyInstaller 路径兼容层
│   │   ├── worker_engine.py        # 后台任务处理器
│   │   ├── schemas.py              # Pydantic 请求/响应模型
│   │   ├── model/
│   │   │   ├── models.py           # 数据模型（含跨数据库类型适配）
│   │   │   └── init_db.py          # 数据库初始化
│   │   ├── routes/
│   │   │   └── example.py          # 示例 CRUD + SSE 流式端点
│   │   ├── services/
│   │   │   └── example_service.py  # 业务逻辑层
│   │   └── utils/
│   │       ├── logging_config.py
│   │       ├── validation.py       # Pydantic 校验装饰器
│   │       └── sse.py              # SSE 流式输出工具
│   ├── config/
│   │   ├── nginx/nginx.conf        # Nginx 反向代理配置
│   │   └── redis.conf              # Redis 配置
│   └── scripts/
│       └── docker-backend.sh       # 容器内启动脚本
├── docker-compose.yml              # 4 容器编排
├── DualModeStarter.spec            # PyInstaller 打包配置
├── build_exe.bat                   # Windows EXE 构建脚本
├── start.sh                        # Docker / 裸机启动脚本
├── .env.desktop.example            # Desktop 模式环境变量模板
├── .env.server.example             # Server 模式环境变量模板
└── ARCHITECTURE.md                 # 架构设计文档
```

## 扩展指南

### 新增数据模型

在 `app/backend/model/models.py` 中定义。大文本字段使用 `LONGTEXT` 变量，它会自动解析为 SQLite 的 `db.Text` 或 MySQL 的 `LONGTEXT`。

### 新增 API 路由

在 `app/backend/routes/` 下创建 Blueprint，然后在 `app/backend/__init__.py` 的 `create_app()` 中注册。

### 新增后台任务

1. 在 `worker_engine.py`（或新模块）中编写处理函数
2. 在路由中入队：`task_queue.enqueue('backend.worker_engine.your_func', arg)`
3. MemoryQueue 和 RQ 都通过点分路径解析函数，调用方式完全一致

### 接入前端

将前端构建产物输出到 `app/frontend/dist/`。Desktop 模式由 Flask 直接 serve，Server 模式由 Nginx 代理。

### 请求校验（Pydantic）

在 `app/backend/schemas.py` 中定义 Pydantic 模型，然后用 `@validate_request` 装饰器应用到路由：

```python
from backend.schemas import ItemCreate
from backend.utils.validation import validate_request

@bp.route('/items', methods=['POST'])
@validate_request(ItemCreate)
def create_item(body: ItemCreate):
    # body 已通过校验，直接使用
    item = Item(title=body.title, description=body.description)
```

校验失败自动返回 422 + 详细字段错误信息。

### SSE 流式输出

框架内置了基于 PubSub 的 SSE 支持，Desktop 和 Server 模式自动适配：

```python
from flask import Response
from backend.utils.sse import sse_stream
from backend.config import RedisKeyManager

@bp.route('/items/<int:item_id>/stream')
def stream_item(item_id):
    channel = RedisKeyManager.stream_channel(item_id)
    return Response(sse_stream(channel), mimetype='text/event-stream')
```

在后台任务中发布事件：

```python
from backend.extensions import redis_client
from backend.config import RedisKeyManager
import json

channel = RedisKeyManager.stream_channel(item_id)
redis_client.publish(channel, json.dumps({"status": "processing", "message": "..."}))
```

前端通过 `EventSource` 接收：

```javascript
const es = new EventSource('/api/items/1/stream');
es.onmessage = (e) => console.log(JSON.parse(e.data));
```

## 环境变量

| 变量 | Desktop 默认值 | Server 默认值 | 说明 |
|------|---------------|---------------|------|
| `DEPLOY_MODE` | `auto` → desktop | `auto` → server | 强制指定：`desktop` 或 `server` |
| `APP_HOST` | `127.0.0.1` | `0.0.0.0` | 监听地址 |
| `APP_PORT` | `5000` | `5000` | HTTP 端口 |
| `MAX_WORKERS` | `4` | `8` | 线程池大小 |
| `DB_USER` | — | `root` | MySQL 用户名 |
| `DB_PASSWORD` | — | （需配置） | MySQL 密码 |
| `DB_HOST` | — | `mysql` | MySQL 主机 |
| `DB_NAME` | — | `dualmode_starter` | MySQL 数据库名 |
| `REDIS_URL` | — | `redis://redis:6379/0` | Redis 连接地址 |
| `ADMIN_USERNAME` | `admin` | `admin` | 管理员用户名 |
| `ADMIN_PASSWORD` | `123456` | `123456` | 管理员密码 |

## start.sh 命令参考

| 命令 | 说明 |
|------|------|
| `up` / `start` | 构建并启动所有 Docker 容器 |
| `down` / `stop` | 停止并移除容器 |
| `restart` | 重启所有容器 |
| `logs` | 查看实时日志 |
| `ps` / `status` | 查看容器状态 |
| `build` | 重新构建镜像（无缓存） |
| `clean` | 移除所有容器、数据卷和镜像 |
| `init` | 裸机初始化（创建 venv + 安装依赖） |
| `run` | 裸机启动后端 |

## Contributors

- **math89423-star** — Creator & Maintainer
- **[Claude](https://github.com/anthropics)** — Architecture design, documentation, code review

## License

MIT
