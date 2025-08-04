import asyncio
import logging
import random
from io import BytesIO

import aiohttp
from aiogram import Bot
from miniopy_async import Minio  # type: ignore

from core import settings

client = Minio(
    settings.S3_ENDPOINT.replace("https://", "").replace("http://", ""),
    access_key=settings.S3_ACCESS,
    secret_key=settings.S3_SECRET,
    secure=not ("localhost" in settings.S3_ENDPOINT or "minio:" in settings.S3_ENDPOINT or False)
)


async def get_user_profile_photo(user_id: int) -> str | None:
    bot = Bot(settings.TG_BOT_TOKEN)
    try:
        user_photos = (await bot.get_user_profile_photos(user_id)).photos
        file_path = (await bot.get_file(user_photos[0][-1].file_id)).file_path
    except Exception as e:
        logging.exception("can't get user photo", exc_info=e)
        return None

    async with aiohttp.ClientSession() as session:
        async with session.get(f"https://api.telegram.org/file/bot{settings.TG_BOT_TOKEN}/{file_path}") as resp:
            avatar = await upload_file(
                data=await resp.read(),
                extension=file_path.split(".")[-1],
                user_id=user_id,
            )

    return avatar


async def upload_file(
        data: bytes,
        extension: str,
        user_id: int,
) -> str:
    key = f"avatar_{user_id}_{random.randint(1, 999999)}.{extension}"

    await client.put_object(
        settings.S3_BUCKET,
        key,
        BytesIO(data),
        -1,
        part_size=5 * 1024 * 1024,
        metadata={
            'x-amz-acl': 'public-read',
            'ACL': 'public-read'
        },
    )

    return f"{settings.HTTP_SCHEMA}{settings.S3_ENDPOINT}/{settings.S3_BUCKET}/{key}"


if __name__ == "__main__":
    asyncio.run(upload_file(b"test", extension="txt", user_id=1))
