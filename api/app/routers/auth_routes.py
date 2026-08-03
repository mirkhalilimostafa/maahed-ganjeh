from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import create_access_token, get_current_user, verify_password
from app.db import get_db
from app.models import User
from app.services.health_loop import run_login_health_loop

router = APIRouter(prefix="/api/auth", tags=["auth"])


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    role: str


class MeOut(BaseModel):
    username: str
    role: str


@router.post("/login", response_model=TokenOut)
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)],
    background: BackgroundTasks,
) -> TokenOut:
    result = await db.execute(select(User).where(User.username == form_data.username))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="نام کاربری یا رمز اشتباه است")
    token = create_access_token(user.username)
    # هر ورود: وضعیت سایت/سپیدار/بات/داده؛ قطعی غیرقابل‌رفع → اعلان بله
    background.add_task(run_login_health_loop)
    return TokenOut(access_token=token, username=user.username, role=user.role)


@router.get("/me", response_model=MeOut)
async def me(user: Annotated[User, Depends(get_current_user)]) -> MeOut:
    return MeOut(username=user.username, role=user.role)
