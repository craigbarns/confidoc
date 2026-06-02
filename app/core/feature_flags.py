"""ConfiDoc Backend — Redis-based Feature Flags."""

from typing import Any

import redis.asyncio as aioredis

from app.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


class FeatureFlags:
    """Simple feature flag manager using Redis."""

    PREFIX = "confidoc:ff:"

    def __init__(self):
        self.redis_url = settings.REDIS_URL
        self._redis = None

    async def _get_redis(self):
        if self._redis is None:
            self._redis = aioredis.from_url(
                self.redis_url, decode_responses=True, socket_connect_timeout=1
            )
        return self._redis

    async def is_enabled(self, flag_name: str, default: bool = False) -> bool:
        """Check if a feature flag is enabled."""
        try:
            r = await self._get_redis()
            val = await r.get(f"{self.PREFIX}{flag_name}")
            if val is None:
                return default
            return val.lower() == "true"
        except Exception as exc:
            logger.warning("feature_flag_check_failed", flag=flag_name, error=str(exc))
            return default

    async def set_flag(self, flag_name: str, enabled: bool) -> None:
        """Set a feature flag value."""
        try:
            r = await self._get_redis()
            await r.set(f"{self.PREFIX}{flag_name}", str(enabled).lower())
            logger.info("feature_flag_updated", flag=flag_name, enabled=enabled)
        except Exception as exc:
            logger.error("feature_flag_update_failed", flag=flag_name, error=str(exc))


# Singleton instance
feature_flags = FeatureFlags()
