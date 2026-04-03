"""Prometheus 指标监控"""
import time
import logging
from typing import Dict, Any
from functools import wraps

from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)


# ====== 请求指标 ======
request_counter = Counter(
    "deep_research_requests_total",
    "Total number of requests",
    ["method", "endpoint", "status"]
)

request_duration = Histogram(
    "deep_research_request_duration_seconds",
    "Request duration in seconds",
    ["method", "endpoint"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0]
)


# ====== 任务指标 ======
task_counter = Counter(
    "deep_research_tasks_total",
    "Total number of research tasks",
    ["status", "phase"]
)

task_duration = Histogram(
    "deep_research_task_duration_seconds",
    "Task duration in seconds",
    ["phase"],
    buckets=[5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0]
)

active_tasks = Gauge(
    "deep_research_active_tasks",
    "Number of active research tasks"
)


# ====== 智能体指标 ======
agent_calls = Counter(
    "deep_research_agent_calls_total",
    "Total number of agent calls",
    ["agent", "status"]
)

agent_duration = Histogram(
    "deep_research_agent_duration_seconds",
    "Agent execution duration in seconds",
    ["agent"],
    buckets=[1.0, 5.0, 10.0, 30.0, 60.0]
)


# ====== LLM 指标 ======
llm_calls = Counter(
    "deep_research_llm_calls_total",
    "Total number of LLM calls",
    ["model", "status"]
)

llm_tokens = Counter(
    "deep_research_llm_tokens_total",
    "Total number of LLM tokens",
    ["model", "type"],
    ["prompt", "completion"]
)

llm_duration = Histogram(
    "deep_research_llm_duration_seconds",
    "LLM call duration in seconds",
    ["model"],
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0]
)


# ====== 搜索指标 ======
search_calls = Counter(
    "deep_research_search_calls_total",
    "Total number of search calls",
    ["provider", "status"]
)

search_results = Histogram(
    "deep_research_search_results",
    "Number of search results",
    ["provider"],
    buckets=[1, 5, 10, 20, 50, 100]
)


# ====== 缓存指标 ======
cache_hits = Counter(
    "deep_research_cache_hits_total",
    "Total number of cache hits",
    ["type"]
)

cache_misses = Counter(
    "deep_research_cache_misses_total",
    "Total number of cache misses",
    ["type"]
)


# ====== 错误指标 ======
error_counter = Counter(
    "deep_research_errors_total",
    "Total number of errors",
    ["type", "component"]
)


def track_duration(histogram: Histogram):
    """装饰器：跟踪函数执行时间"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start_time
                histogram.observe(duration)
        return wrapper
    return decorator


def track_task_phase(phase: str):
    """装饰器：跟踪任务阶段"""
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            active_tasks.inc()
            try:
                result = await func(*args, **kwargs)
                task_counter.labels(status="success", phase=phase).inc()
                return result
            except Exception as e:
                task_counter.labels(status="error", phase=phase).inc()
                error_counter.labels(type="task_error", component=phase).inc()
                raise
            finally:
                duration = time.time() - start_time
                task_duration.labels(phase=phase).observe(duration)
                active_tasks.dec()
        return async_wrapper
    return decorator


async def metrics_endpoint(request: Request) -> Response:
    """Prometheus 指标端点"""
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )


def get_metrics_summary() -> Dict[str, Any]:
    """获取指标摘要"""
    return {
        "requests": {
            "total": request_counter._value.get(),
        },
        "tasks": {
            "active": active_tasks._value.get(),
        }
    }
