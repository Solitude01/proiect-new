"""
Celery 异步任务配置
"""
from celery import Celery
from app.config import settings

# 创建Celery应用
celery_app = Celery(
    "ai_capability_profile",
    broker=f"redis://{settings.redis_host}:{settings.redis_port}/{settings.redis_db}",
    backend=f"redis://{settings.redis_host}:{settings.redis_port}/{settings.redis_db}",
    include=["app.worker.tasks"],
)

# Celery配置
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,  # 1小时超时
    worker_prefetch_multiplier=1,  # 每次只处理一个任务
)


# 定时任务配置（可选）
celery_app.conf.beat_schedule = {
    # 每天凌晨2点执行数据同步
    "daily-sync": {
        "task": "app.worker.tasks.scheduled_sync",
        "schedule": 0,  # 禁用，手动启用
        # "schedule": crontab(hour=2, minute=0),  # 每天凌晨2点
    },
}
