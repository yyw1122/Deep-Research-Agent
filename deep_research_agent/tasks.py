"""Celery 任务队列配置"""
from celery import Celery
from celery.signals import worker_init
import os

# Celery 配置
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")

# 创建 Celery 应用
app = Celery(
    "deep_research_agent",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
    include=["deep_research_agent.tasks"]
)

# 配置
app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,  # 1小时超时
    task_soft_time_limit=3000,  # 50分钟软超时
    worker_prefetch_multiplier=1,
    worker_concurrency=4,
)


@worker_init.connect
def initialize_worker(**kwargs):
    """初始化 worker"""
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
