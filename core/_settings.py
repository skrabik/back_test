from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str
    REDIS_URL: str

    TG_BOT_TOKEN: str

    DEBUG: bool = Field(default=False)

    HTTP_SCHEMA: str = Field(default="https://")
    DOMAIN: str

    S3_ENDPOINT: str
    S3_BUCKET: str = Field("default")
    S3_ACCESS: str
    S3_SECRET: str

    DOMAIN: str

    RTNET_BASE_URL: str = Field(default="https://rtnet.space")

    RTNET_RUB_PROJECT_ID: str
    RTNET_RUB_API_ID: str
    RTNET_RUB_PRIVATE_KEY: str

    RTNET_UZS_PROJECT_ID: str
    RTNET_UZS_API_ID: str
    RTNET_UZS_PRIVATE_KEY: str

    model_config = SettingsConfigDict(extra="ignore", env_file=".env")


settings = Settings(_env_file=".env")
