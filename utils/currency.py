from core import USDT_RUB_PRICE, USDT_UZS_PRICE
from core import redis


async def get_usdt_rub() -> float:
    return await redis.get("currency:USDTRUB") or USDT_RUB_PRICE


async def get_usdt_uzs() -> float:
    return await redis.get("currency:USDTUZS") or USDT_UZS_PRICE
