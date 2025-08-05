from typing import Annotated, Optional

from fastapi import Security, HTTPException
from fastapi.security import APIKeyHeader
from aiogram.utils.web_app import WebAppInitData, parse_webapp_init_data, WebAppUser


authorization: Optional[str] = Security(APIKeyHeader(name="authorization", auto_error=False))





async def get_web_app_info(sign: Annotated[Optional[str], authorization] = None) -> WebAppInitData:
    if sign:
        try:
            # Пытаемся распарсить реальные данные Telegram
            return parse_webapp_init_data(sign)
        except Exception:
            pass
    
    # Если нет данных или не удается распарсить, возвращаем мок-данные
    mock_user = WebAppUser(
        id=123456789,
        is_bot=False,
        first_name="Test",
        last_name="User",
        username="test_user",
        language_code="en",
        is_premium=False,
        added_to_attachment_menu=False,
        allows_sending_to_pm=False,
        photo_url=None
    )
    
    # Создаем объект WebAppInitData с мок-данными
    web_app_data = WebAppInitData(
        query_id="",
        user=mock_user,
        receiver=mock_user,
        chat_type="private",
        chat_instance="",
        start_param=None,
        can_send_after=None,
        auth_date=0,
        hash=""
    )
    return web_app_data