from datetime import datetime, timezone

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    return {
        "ok": True,
        "service": "maahed-ganjeh-api",
        "ts": datetime.now(timezone.utc).isoformat(),
    }
