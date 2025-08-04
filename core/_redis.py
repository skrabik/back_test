from redis.asyncio import Redis

from core import settings

redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)


async def set_user_rating(user_id: int, wins: float) -> None:
    await redis.zadd("rating", {user_id: wins})


async def get_token_price() -> float | None:
    ret = await redis.get("token_price")
    return float(ret) if ret is not None else None
