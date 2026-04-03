"""速率限制器"""
import time
import logging
from typing import Dict, Optional
from dataclasses import dataclass
import asyncio

from ..config.settings import settings

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """速率限制配置"""
    max_requests: int = 10  # 每分钟最大请求数
    window_seconds: int = 60
    burst_size: int = 5


class RateLimiter:
    """令牌桶速率限制器"""

    def __init__(self, config: RateLimitConfig = None):
        self.config = config or RateLimitConfig()
        self._buckets: Dict[str, Dict] = {}
        self._cleanup_interval = 3600  # 1小时清理一次过期bucket
        self._last_cleanup = time.time()

    def _get_bucket(self, key: str) -> Dict:
        """获取或创建令牌桶"""
        now = time.time()

        # 定期清理
        if now - self._last_cleanup > self._cleanup_interval:
            self._cleanup()
            self._last_cleanup = now

        if key not in self._buckets:
            self._buckets[key] = {
                "tokens": self.config.burst_size,
                "last_update": now
            }

        return self._buckets[key]

    def _cleanup(self):
        """清理过期桶"""
        now = time.time()
        expired = [
            k for k, v in self._buckets.items()
            if now - v["last_update"] > self.config.window_seconds * 2
        ]
        for k in expired:
            del self._buckets[k]

    def _refill_bucket(self, bucket: Dict):
        """补充令牌"""
        now = time.time()
        elapsed = now - bucket["last_update"]

        # 每秒补充 tokens
        refill_rate = self.config.max_requests / self.config.window_seconds
        new_tokens = elapsed * refill_rate

        bucket["tokens"] = min(
            self.config.burst_size,
            bucket["tokens"] + new_tokens
        )
        bucket["last_update"] = now

    async def check_limit(self, key: str) -> tuple[bool, Dict]:
        """检查速率限制

        Returns:
            (是否允许, 限制信息)
        """
        bucket = self._get_bucket(key)
        self._refill_bucket(bucket)

        if bucket["tokens"] >= 1:
            bucket["tokens"] -= 1
            return True, {
                "allowed": True,
                "remaining": int(bucket["tokens"]),
                "reset_at": int(bucket["last_update"] + self.config.window_seconds)
            }
        else:
            return False, {
                "allowed": False,
                "remaining": 0,
                "reset_at": int(bucket["last_update"] + self.config.window_seconds),
                "retry_after": int(self.config.window_seconds - (time.time() - bucket["last_update"]))
            }


# 全局速率限制器
default_limiter = RateLimiter(RateLimitConfig(
    max_requests=10,  # 10次/分钟
    window_seconds=60,
    burst_size=3
))


async def check_api_rate_limit(client_id: str) -> tuple[bool, Dict]:
    """检查 API 速率限制

    Args:
        client_id: 客户端标识 (API Key 或 IP)
    """
    return await default_limiter.check_limit(f"api:{client_id}")


def get_rate_limit_status(client_id: str) -> Dict:
    """获取速率限制状态"""
    bucket = default_limiter._get_bucket(f"api:{client_id}")
    return {
        "limit": default_limiter.config.max_requests,
        "window": default_limiter.config.window_seconds,
        "remaining": int(bucket.get("tokens", 0)),
        "reset_at": int(bucket.get("last_update", 0) + default_limiter.config.window_seconds)
    }
