from __future__ import annotations

from typing import Any

from app.config import Settings
from app.connectors.bots.bale import BaleBot
from app.connectors.bots.base import BotAdapter, BotSendResult
from app.connectors.bots.stub import StubBot
from app.connectors.bots.telegram import TelegramBot

_stub = StubBot()


class MultiBot(BotAdapter):
    """Prefer explicit channel hint in recipient, else Bale, else Telegram, else stub."""

    channel = "multi"

    def __init__(self, bots: list[BotAdapter], default: BotAdapter) -> None:
        self.bots = bots
        self.default = default
        self._by_channel = {b.channel: b for b in bots}

    def _pick(self, recipient: str) -> tuple[BotAdapter, str]:
        raw = (recipient or "").strip()
        lower = raw.lower()
        if lower.startswith("bale:"):
            return self._by_channel.get("bale", self.default), raw.split(":", 1)[1].strip()
        if lower.startswith("telegram:") or lower.startswith("tg:"):
            key = "telegram"
            return self._by_channel.get(key, self.default), raw.split(":", 1)[1].strip()
        return self.default, raw

    async def send_message(
        self,
        recipient: str,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> BotSendResult:
        bot, chat = self._pick(recipient)
        return await bot.send_message(chat, message, payload)

    def status(self) -> dict[str, Any]:
        channels = [b.status() for b in self.bots]
        primary = self.default.status()
        return {
            "channel": primary.get("channel", self.channel),
            "ok": any(c.get("ok") for c in channels),
            "configured": True,
            "mode": "multi" if len(self.bots) > 1 else primary.get("mode"),
            "freshness_label": primary.get("freshness_label"),
            "detail": primary.get("detail"),
            "channels": channels,
            "default": primary.get("channel"),
        }


def get_bot_adapter(settings: Settings) -> BotAdapter:
    bots: list[BotAdapter] = []
    if settings.bale_bot_token.strip():
        bots.append(BaleBot(settings.bale_bot_token, api_base=settings.bale_api_base_url))
    if settings.telegram_bot_token.strip():
        bots.append(TelegramBot(settings.telegram_bot_token, api_base=settings.telegram_api_base_url))
    if not bots:
        return _stub
    # Prefer Bale when both exist (company messenger); else the only configured one.
    default = next((b for b in bots if b.channel == "bale"), bots[0])
    if len(bots) == 1:
        return bots[0]
    return MultiBot(bots, default)


def get_stub_bot() -> StubBot:
    return _stub
