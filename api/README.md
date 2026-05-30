# Comet 后端（api/）

彗记 Comet 的 FastAPI 后端，分层架构：Controller → Service → Repository。

## 目录结构

```
api/
├── app/
│   ├── config.py          # 环境变量配置
│   ├── main.py            # FastAPI 入口
│   ├── celery_app.py      # Celery 多队列配置
│   ├── core/              # 通用：响应包裹、异常、安全(JWT/加密)
│   ├── db/                # 存储连接：postgres / elastic / neo4j / redis
│   ├── controllers/       # 路由层
│   ├── services/          # 业务服务层
│   ├── repositories/      # 数据访问层
│   ├── schemas/           # Pydantic 模型
│   ├── models/            # SQLAlchemy ORM 模型
│   └── tasks/             # Celery 异步任务
├── run.py                 # 本地启动入口
├── pyproject.toml         # 依赖（uv 管理）
├── Dockerfile
└── .env.example
```

## 本地开发（使用 uv）

```bash
# 1. 装依赖（自动创建 .venv）
uv sync

# 2. 准备环境变量
copy .env.example .env        # 按需修改

# 3. 启动（需先用 docker-compose 起好 PG/ES/Neo4j/Redis）
uv run python run.py
```

## 验证点（阶段0）

- `GET /api/hello` → 返回欢迎信息
- `GET /api/health` → 探测四存储连通性

## Celery

```bash
# Worker
uv run celery -A app.celery_app.celery_app worker -l info -Q default,parse,memory
# Beat（定时）
uv run celery -A app.celery_app.celery_app beat -l info
```

## Elasticsearch 中文分词（IK）

知识库的 BM25 全文检索依赖 IK 中文分词插件，否则中文按单字切，检索效果差。
ES 容器基于官方镜像 + analysis-ik 插件构建（见 `docker/es/Dockerfile`）。

首次启用或更新 IK 时需重建 ES 容器：

```bash
# 在项目根目录
docker compose build elasticsearch
docker compose up -d elasticsearch
```

`comet_chunks` 索引的 content 字段使用 ik_max_word（写入）/ ik_smart（查询）。
若索引已用旧 mapping 创建过，需先删除让其按新 mapping 重建：

```bash
curl -X DELETE http://localhost:9200/comet_chunks
# 重启后端会自动重建带 IK 的索引
```
