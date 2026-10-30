"""One connection constructor; Redis-compatible ElastiCache uses the same transport."""
from redis.asyncio import Redis
from backend.domain.settings.providers import RedisSettings

def create_redis_client(settings: RedisSettings) -> Redis:
    return Redis(host=settings.host, port=settings.port,
                 password=settings.password.get_secret_value(),
                 decode_responses=False, socket_timeout=2, socket_connect_timeout=2)
