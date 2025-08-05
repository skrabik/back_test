import asyncio
import os
from typing import Callable, Awaitable

import anyio
import uvicorn
from anyio.abc import TaskGroup
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


from core import settings
from endpoint.http import router
from utils.get_token_price import task_get_token_price
from utils.scheduler_games_task import scheduler_games_task

app = FastAPI()
app.include_router(router, prefix="/api")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def index():
    return "OK"


config = uvicorn.Config(
    "main:app", "0.0.0.0", log_level=4, workers=1, reload=False,
)

server = uvicorn.Server(config)


async def start_server(tg: TaskGroup, server: Callable[[], Awaitable]):
    await server()
    tg.cancel_scope.cancel()





async def start_get_token_price(tg: TaskGroup):
    await task_get_token_price()
    tg.cancel_scope.cancel()


async def start_scheduler_games(tg: TaskGroup):
    await scheduler_games_task()
    tg.cancel_scope.cancel()


async def main():
    async with anyio.create_task_group() as tg:
        tg.start_soon(start_server, tg, server.serve)
        tg.start_soon(start_get_token_price, tg)
        tg.start_soon(start_scheduler_games, tg)


if __name__ == '__main__':
    os.system("alembic upgrade head")
    asyncio.run(main())
