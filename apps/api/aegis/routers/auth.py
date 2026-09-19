"""Authentication endpoints (section 48)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..config import get_settings
from ..db import get_db
from ..enums import DEFAULT_ROLE_PERMISSIONS
from ..models import Membership, RoleDefinition, User
from ..schemas import LoginRequest, MeResponse, TokenResponse, UserOut
from ..security import create_access_token, get_current_user, permissions_for, verify_password
from .deps import client_ip

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.execute(select(User).where(User.email == payload.email)).scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash) or not user.is_active:
        # Same response for unknown account and wrong password.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")

    audit.record(
        db,
        action="auth.login",
        object_type="user",
        object_id=user.id,
        actor_id=user.id,
        actor_label=user.email,
        source_ip=client_ip(request),
    )
    db.commit()

    settings = get_settings()
    return TokenResponse(
        access_token=create_access_token(user),
        expires_in_minutes=settings.access_token_ttl_minutes,
    )


@router.get("/me", response_model=MeResponse)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> MeResponse:
    memberships = list(
        db.execute(select(Membership).where(Membership.user_id == user.id)).scalars()
    )
    return MeResponse(
        user=UserOut.model_validate(user),
        memberships=[
            {
                "organization_id": m.organization_id,
                "project_id": m.project_id,
                "role": m.role,
            }
            for m in memberships
        ],
        permissions=sorted(permissions_for(db, user)),
    )


@router.get("/roles")
def roles(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    """The editable role/permission matrix for the caller's organizations."""
    org_ids = {
        m.organization_id
        for m in db.execute(select(Membership).where(Membership.user_id == user.id)).scalars()
    }
    definitions = list(
        db.execute(
            select(RoleDefinition).where(RoleDefinition.organization_id.in_(org_ids or [""]))
        ).scalars()
    )
    return {
        "shipped_defaults": DEFAULT_ROLE_PERMISSIONS,
        "configured": [
            {
                "organization_id": d.organization_id,
                "role": d.role,
                "permissions": d.permissions,
                "description": d.description,
            }
            for d in definitions
        ],
    }


@router.get("/providers")
def providers() -> dict:
    """What identity paths this deployment has configured."""
    settings = get_settings()
    return {
        "local_accounts": True,
        "oidc": {
            "configured": bool(settings.oidc_issuer),
            "issuer": settings.oidc_issuer or None,
            "client_id": settings.oidc_client_id or None,
        },
        "client_certificate": {
            "enabled": True,
            "note": (
                "CAC/PIV authentication is accepted when the terminating proxy validates the "
                "certificate chain and forwards x-client-cert-subject, x-client-cert-edipi and "
                "x-client-cert-verified. The platform does not validate certificates itself."
            ),
        },
    }
