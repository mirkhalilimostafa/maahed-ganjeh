from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_secret_key: str = "dev-secret-change-me"
    app_public_base_url: str = "http://localhost:8080"
    admin_username: str = "admin"
    admin_password: str = "admin"

    database_url: str = "sqlite+aiosqlite:///./ganjeh.db"
    # Production Darkube: /data/uploads (PVC). Local: falls back in connectors/manual_ingest.
    upload_dir: str = "/app/uploads"

    sepidar_mcp_url: str = "http://62.60.162.156:8787/mcp"
    sepidar_mcp_token: str = ""

    maahed_site_base_url: str = "https://maahed.ir"
    maahed_site_admin_login_path: str = "/admin-panel/login"
    maahed_site_username: str = ""
    maahed_site_password: str = ""
    # Optional: if admin captcha is disabled/bypassed for a service account, leave empty.
    # Automated login cannot solve image captcha without a human or OCR service.
    maahed_site_captcha: str = ""

    telegram_bot_token: str = ""
    bale_bot_token: str = ""
    bale_api_base_url: str = "https://tapi.bale.ai"
    telegram_api_base_url: str = "https://api.telegram.org"
    # Default Bale/Telegram chat_id for dashboard link notifications (e.g. "1566616156" or "bale:1566616156").
    # Never fall back to the panel username — messenger APIs need a numeric chat_id.
    bot_notify_recipient: str = ""
    # Inbound file receive from Bale → UPLOAD_DIR + manual_ingests.
    # Comma-separated chat_ids; empty → fall back to BOT_NOTIFY_RECIPIENT.
    bale_ingest_chat_ids: str = ""
    # auto | webhook | poll | off — auto picks webhook when APP_PUBLIC_BASE_URL is public https.
    bale_ingest_mode: str = "auto"
    # Optional Telegram-compatible webhook secret (header X-Telegram-Bot-Api-Secret-Token).
    bale_webhook_secret: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
