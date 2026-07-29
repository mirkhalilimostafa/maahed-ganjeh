from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import create_access_token, get_current_user, verify_password
from app.db import get_db
from app.models import User

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
) -> TokenOut:
    result = await db.execute(select(User).where(User.username == form_data.username))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="نام کاربری یا رمز اشتباه است")
    token = create_access_token(user.username)
    return TokenOut(access_token=token, username=user.username, role=user.role)


@router.get("/me", response_model=MeOut)
async def me(user: Annotated[User, Depends(get_current_user)]) -> MeOut:
    return MeOut(username=user.username, role=user.role)
