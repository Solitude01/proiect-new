# AI能力画像文档系统 - 应用目录

本目录包含后端API服务和Web应用的所有代码。

## 目录结构

```
app/
├── main.py                 # FastAPI主应用
├── config.py              # 应用配置
├── database.py            # 数据库连接
├── models.py              # 数据模型
├── schemas.py             # Pydantic模式
├── routes/                # API路由
│   ├── __init__.py
│   ├── projects.py        # 项目API
│   ├── sync.py           # 同步API
│   └── analyze.py        # 分析API
├── services/              # 业务服务
│   ├── __init__.py
│   ├── db_sync.py        # 数据库同步服务
│   ├── excel_processor.py # Excel处理服务
│   └── ai_analyzer.py    # AI分析服务
├── worker/                # Celery任务
│   ├── __init__.py
│   └── celery_app.py     # Celery配置
└── utils/                 # 工具函数
    ├── __init__.py
    └── helpers.py
```

## 快速开始

1. 安装依赖：`pip install -r requirements.txt`
2. 配置环境变量：复制 `.env.example` 为 `.env` 并修改配置
3. 初始化数据库：执行 `create_tables.sql` 脚本
4. 启动应用：`uvicorn app.main:app --reload`

## API文档

启动后访问：http://localhost:8000/docs
