import asyncio
import logging

import httpx

from core import redis
from utils.round_down import round_down


async def task_get_token_price():
    while True:
        try:
            await get_token_price()
            await asyncio.sleep(300)
        except Exception as e:
            logging.exception("task get token price exception", exc_info=e)
            await asyncio.sleep(900)


async def get_token_price():
    symbol = 'BTCUSDT'
    api_url = 'https://api.binance.com/api/v3/ticker/price?symbol={}'.format(symbol)

    async with httpx.AsyncClient() as client:
        response = await client.get(api_url)

    if response.status_code != 200:
        logging.error(f"get_token_price error: {response.text}")
        return

    price = round_down(float(response.json()["price"]))
    await redis.set("token_price", price)

    logging.info("get_token_price success with price: %s", price)
