from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class BotSendResult:
    ok: bool
    channel: str
    detail: str
    message_id: str | None = None


class BotAdapter(ABC):
    channel: str

    @abstractmethod
    async def send_message(
        self,
        recipient: str,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> BotSendResult:
        raise NotImplementedError

    @abstractmethod
    def status(self) -> dict[str, Any]:
        raise NotImplementedError
