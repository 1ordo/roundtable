import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import audit
from app.auth.deps import csrf_protect, get_current_user
from app.auth.tokens import api_tokens_enabled, generate_token, hash_token
from app.db import get_db
from app.models import ApiToken, User

router = APIRouter(
    prefix="/api/tokens", dependencies=[Depends(get_current_user), Depends(csrf_protect)]
)


class TokenOut(BaseModel):
    id: str
    name: str
    scopes: list[str]
    last_used_at: datetime | None
    created_at: datetime
    revoked: bool


class TokenListResponse(BaseModel):
    api_enabled_globally: bool
    api_enabled_for_me: bool
    tokens: list[TokenOut]


def _out(token: ApiToken) -> TokenOut:
    return TokenOut(
        id=str(token.id),
        name=token.name,
        scopes=token.scopes or [],
        last_used_at=token.last_used_at,
        created_at=token.created_at,
        revoked=token.revoked_at is not None,
    )


@router.get("", response_model=TokenListResponse)
async def list_tokens(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> TokenListResponse:
    rows = (
        (
            await db.execute(
                select(ApiToken)
                .where(ApiToken.user_id == user.id)
                .order_by(ApiToken.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return TokenListResponse(
        api_enabled_globally=await api_tokens_enabled(db),
        api_enabled_for_me=user.api_enabled,
        tokens=[_out(t) for t in rows],
    )


class CreateTokenBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    scope: str = Field(pattern="^(read|write)$")


class CreatedToken(BaseModel):
    token: str
    info: TokenOut


@router.post("", response_model=CreatedToken, status_code=201)
async def create_token(
    body: CreateTokenBody,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CreatedToken:
    if not await api_tokens_enabled(db):
        raise HTTPException(status_code=403, detail="personal API access is turned off")
    if not user.api_enabled:
        raise HTTPException(
            status_code=403, detail="ask your admin to enable API access for your account"
        )
    plaintext = generate_token()
    scopes = ["read"] if body.scope == "read" else ["read", "write"]
    token = ApiToken(
        user_id=user.id,
        name=body.name.strip(),
        token_hash=hash_token(plaintext),
        scopes=scopes,
    )
    db.add(token)
    await db.flush()
    await audit(
        db,
        "token.create",
        actor=user,
        request=request,
        object_type="api_token",
        object_id=str(token.id),
        detail={"name": token.name, "scopes": scopes},
    )
    await db.commit()
    return CreatedToken(token=plaintext, info=_out(token))


@router.delete("/{token_id}", status_code=204)
async def revoke_token(
    token_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    try:
        tid = uuid.UUID(token_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="token not found") from exc
    token = (
        await db.execute(select(ApiToken).where(ApiToken.id == tid, ApiToken.user_id == user.id))
    ).scalar_one_or_none()
    if token is None:
        raise HTTPException(status_code=404, detail="token not found")
    if token.revoked_at is None:
        token.revoked_at = datetime.now(UTC)
        await audit(
            db,
            "token.revoke",
            actor=user,
            request=request,
            object_type="api_token",
            object_id=str(token.id),
        )
    await db.commit()
