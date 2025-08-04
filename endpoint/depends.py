from typing import Annotated

from fastapi import Security
from fastapi.security import APIKeyHeader
from aiogram.utils.web_app import WebAppInitData, parse_webapp_init_data


authorization: str = Security(APIKeyHeader(name="authorization"))


async def get_web_app_info(sign: Annotated[str, authorization]) -> WebAppInitData:
    return parse_webapp_init_data(sign)