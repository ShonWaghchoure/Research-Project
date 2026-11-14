"""Sign-In With Ethereum: nonce + verify → JWT."""

from __future__ import annotations

from datetime import datetime, timezone

from eth_utils import is_address, to_checksum_address
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.limiter import limiter
from app.core.security import build_siwe_message, create_access_token, new_nonce, verify_siwe
from app.db.deps import get_db
from app.db.models import User, UserRole
from app.schemas.auth import NonceRequest, NonceResponse, TokenResponse, VerifyRequest

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/nonce", response_model=NonceResponse)
@limiter.limit("30/minute")
def issue_nonce(body: NonceRequest, request: Request, db: Session = Depends(get_db)) -> NonceResponse:
    if not is_address(body.address):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid address")
    address = to_checksum_address(body.address)
    user = db.query(User).filter(User.address == address).one_or_none()
    if user is None:
        user = User(address=address, role=UserRole.participant, nonce_used=True)
        db.add(user)
        db.flush()
    nonce = new_nonce()
    issued_at = datetime.now(timezone.utc).replace(microsecond=0)
    user.nonce = nonce
    user.nonce_used = False
    user.nonce_issued_at = issued_at
    db.commit()
    message = build_siwe_message(
        address=address, nonce=nonce, chain_id=settings.CHAIN_ID, issued_at=issued_at
    )
    # Bind limiter key (slowapi uses request)
    _ = request
    return NonceResponse(address=address, nonce=nonce, message=message, chain_id=settings.CHAIN_ID)


@router.post("/verify", response_model=TokenResponse)
@limiter.limit("30/minute")
def verify_signature(
    body: VerifyRequest, request: Request, db: Session = Depends(get_db)
) -> TokenResponse:
    _ = request
    if not is_address(body.address):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid address")
    address = to_checksum_address(body.address)
    user = db.query(User).filter(User.address == address).one_or_none()
    if user is None or not user.nonce or user.nonce_used or user.nonce_issued_at is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="nonce required")
    expected = build_siwe_message(
        address=address,
        nonce=user.nonce,
        chain_id=settings.CHAIN_ID,
        issued_at=user.nonce_issued_at,
    )
    try:
        verify_siwe(
            address=address,
            message=body.message,
            signature=body.signature,
            expected_message=expected,
            issued_at=user.nonce_issued_at,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    # Single-use nonce
    user.nonce_used = True
    user.nonce = None
    user.nonce_issued_at = None
    db.commit()

    token = create_access_token(subject=address, role=user.role.value, user_id=user.id)
    return TokenResponse(access_token=token, role=user.role.value, address=address)
