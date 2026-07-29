from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_secret_key: str = "dev-secret-change-me"
    app_public_base_url: str = "http://localhost:8080"
    admin_username: str = "admin"
    admin_password: str = "admin"

    database_url: str = "sqlite+aiosqlite:///./ganjeh.db"

    sepidar_mcp_url: str = "http://62.60.162.156:8787/mcp"
    sepidar_mcp_token: str = ""

    maahed_site_base_url: str = "https://maahed.ir"
    maahed_site_username: str = ""
    maahed_site_password: str = ""

    telegram_bot_token: str = ""
    bale_bot_token: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
