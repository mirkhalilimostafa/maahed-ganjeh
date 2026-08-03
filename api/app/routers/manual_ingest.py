from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.config import get_settings
from app.connectors.darkube_disk import resolve_upload_dir
from app.db import get_db
from app.models import ManualIngest, User

router = APIRouter(prefix="/api/manual-ingest", tags=["manual-ingest"])


def _upload_dir() -> Path:
    return resolve_upload_dir(get_settings())


class ManualIngestOut(BaseModel):
    id: int
    source: str
    data_date: str
    description: str
    filename: str | None
    created_by: str
    storage: str | None = None


@router.post("", response_model=ManualIngestOut)
async def create_manual_ingest(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    source: Annotated[str, Form()],
    data_date: Annotated[str, Form()],
    description: Annotated[str, Form()] = "",
    file: UploadFile | None = File(default=None),
) -> ManualIngestOut:
    filename = None
    upload_dir = _upload_dir()
    if file is not None and file.filename:
        safe = f"{uuid4().hex}_{file.filename}"
        dest = upload_dir / safe
        content = await file.read()
        dest.write_bytes(content)
        filename = safe

    row = ManualIngest(
        source=source,
        data_date=data_date,
        description=description,
        filename=filename,
        created_by=user.username,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return ManualIngestOut(
        id=row.id,
        source=row.source,
        data_date=row.data_date,
        description=row.description,
        filename=row.filename,
        created_by=row.created_by,
        storage=str(upload_dir),
    )


@router.get("", response_model=list[ManualIngestOut])
async def list_manual_ingests(
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[User, Depends(get_current_user)],
) -> list[ManualIngestOut]:
    result = await db.execute(select(ManualIngest).order_by(ManualIngest.id.desc()).limit(50))
    rows = result.scalars().all()
    storage = str(_upload_dir())
    return [
        ManualIngestOut(
            id=r.id,
            source=r.source,
            data_date=r.data_date,
            description=r.description,
            filename=r.filename,
            created_by=r.created_by,
            storage=storage,
        )
        for r in rows
    ]
