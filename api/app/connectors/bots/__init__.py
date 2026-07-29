from __future__ import annotations

from app.config import Settings
from app.connectors.bots.base import BotAdapter
from app.connectors.bots.stub import StubBot

_stub = StubBot()


def get_bot_adapter(settings: Settings) -> BotAdapter:
    """Return real adapters when tokens exist; otherwise StubBot."""
    # Real Telegram/Bale adapters land when tokens are provided (later wiring).
    if settings.telegram_bot_token or settings.bale_bot_token:
        # Tokens present but adapters not yet implemented — still stub with note.
        return _stub
    return _stub


def get_stub_bot() -> StubBot:
    return _stub
