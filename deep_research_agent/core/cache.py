"""Redis 缓存层"""
import json
import hashlib
import logging
from typing import Any, Optional, Dict
from datetime import timedelta
import redis.asyncio as redis

from ..config.settings import settings

logger = logging.getLogger(__name__)


class CacheManager:
    """缓存管理器"""

    def __init__(self):
        self._redis: Optional[redis.Redis] = None
        self._enabled = False
        self._cache_ttl = 3600  # 默认 1 小时缓存

    async def connect(self):
        """连接 Redis"""
        try:
            self._redis = redis.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                decode_responses=True,
                socket_connect_timeout=5
            )
            await self._redis.ping()
            self._enabled = True
            logger.info("Redis 缓存连接成功")
        except Exception as e:
            logger.warning(f"Redis 连接失败，缓存功能禁用: {e}")
            self._enabled = False

    async def disconnect(self):
        """断开 Redis 连接"""
        if self._redis:
            await self._redis.close()
            self._enabled = False

    def _generate_key(self, prefix: str, *args) -> str:
        """生成缓存键"""
        key_data = "_".join(str(arg) for arg in args)
        key_hash = hashlib.md5(key_data.encode()).hexdigest()[:16]
        return f"dra:{prefix}:{key_hash}"

    async def get(self, prefix: str, *args) -> Optional[Dict[str, Any]]:
        """获取缓存"""
        if not self._enabled or not self._redis:
            return None

        try:
            key = self._generate_key(prefix, *args)
            value = await self._redis.get(key)
            if value:
                return json.loads(value)
        except Exception as e:
            logger.warning(f"缓存读取失败: {e}")

        return None

    async def set(self, prefix: str, value: Dict[str, Any],
                  ttl: Optional[int] = None) -> bool:
        """设置缓存"""
        if not self._enabled or not self._redis:
            return False

        try:
            key = self._generate_key(prefix, *self._extract_keys(value))
            await self._redis.setex(
                key,
                ttl or self._cache_ttl,
                json.dumps(value, ensure_ascii=False)
            )
            return True
        except Exception as e:
            logger.warning(f"缓存写入失败: {e}")
            return False

    def _extract_keys(self, value: Dict) -> tuple:
        """从值中提取键"""
        if "query" in value:
            return (value.get("query"),)
        elif "task_id" in value:
            return (value.get("task_id"),)
        return (str(value),)

    async def delete(self, prefix: str, *args) -> bool:
        """删除缓存"""
        if not self._enabled or not self._redis:
            return False

        try:
            key = self._generate_key(prefix, *args)
            await self._redis.delete(key)
            return True
        except Exception as e:
            logger.warning(f"缓存删除失败: {e}")
            return False

    async def clear_prefix(self, prefix: str) -> bool:
        """清除指定前缀的缓存"""
        if not self._enabled or not self._redis:
            return False

        try:
            pattern = f"dra:{prefix}:*"
            keys = []
            async for key in self._redis.scan_iter(match=pattern):
                keys.append(key)
            if keys:
                await self._redis.delete(*keys)
            return True
        except Exception as e:
            logger.warning(f"缓存清除失败: {e}")
            return False

    @property
    def is_enabled(self) -> bool:
        """缓存是否启用"""
        return self._enabled


# 全局缓存管理器
cache_manager = CacheManager()


async def get_cache_stats() -> Dict[str, Any]:
    """获取缓存统计"""
    if not cache_manager.is_enabled or not cache_manager._redis:
        return {"enabled": False}

    try:
        info = await cache_manager._redis.info("stats")
        return {
            "enabled": True,
            "total_keys": await cache_manager._redis.dbsize(),
            "hits": info.get("keyspace_hits", 0),
            "misses": info.get("keyspace_misses", 0)
        }
    except Exception:
        return {"enabled": False}
