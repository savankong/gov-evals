"""Authentication and access control.

P0 covers local accounts, OIDC-issued identities and role-based access
control. The CAC/PIV path (P1) is wired as far as trusting a verified
client-certificate subject forwarded by the terminating proxy: the platform
never performs certificate validation itself, because in a DoD deployment that
belongs to the reverse proxy or the service mesh.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .enums import DEFAULT_ROLE_PERMISSIONS, Permission, Role
from .models import Membership, Project, RoleDefinition, User

bearer = HTTPBearer(auto_error=False)
ALGORITHM = "HS256"

# bcrypt hashes at most 72 bytes. Rather than silently truncating -- which would
# make two different long passwords equivalent -- long inputs are rejected.
MAX_PASSWORD_BYTES = 72


def hash_password(password: str) -> str:
    encoded = password.encode("utf-8")
    if len(encoded) > MAX_PASSWORD_BYTES:
        raise ValueError(
            f"Password exceeds {MAX_PASSWORD_BYTES} bytes, which bcrypt cannot hash without "
            "truncation. Use a shorter passphrase, or federate this account through OIDC."
        )
    return bcrypt.hashpw(encoded, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    encoded = password.encode("utf-8")
    if len(encoded) > MAX_PASSWORD_BYTES:
        return False
    try:
        return bcrypt.checkpw(encoded, password_hash.encode("utf-8"))
    except ValueError:
        # Malformed stored hash: treat as a failed verification, never a pass.
        return False


def create_access_token(user: User, extra: dict | None = None) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": user.id,
        "email": user.email,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_ttl_minutes),
        "iss": "aegis-eval",
        **(extra or {}),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM], issuer="aegis-eval")
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Invalid token: {exc}") from exc


def _user_from_client_certificate(request: Request, db: Session) -> User | None:
    """Trust a client-certificate subject asserted by the terminating proxy.

    Only consulted when the deployment sets these headers. The proxy is
    responsible for validating the certificate chain against DoD PKI.
    """
    subject = request.headers.get("x-client-cert-subject")
    edipi = request.headers.get("x-client-cert-edipi")
    verified = request.headers.get("x-client-cert-verified", "").upper()
    if not subject or verified not in ("SUCCESS", "TRUE", "1"):
        return None
    stmt = select(User).where(User.external_subject == subject)
    user = db.execute(stmt).scalar_one_or_none()
    if user is None and edipi:
        user = db.execute(select(User).where(User.edipi == edipi)).scalar_one_or_none()
    return user


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is not None:
        payload = decode_token(credentials.credentials)
        user = db.get(User, payload.get("sub"))
        if user and user.is_active:
            return user
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account is unknown or inactive")

    user = _user_from_client_certificate(request, db)
    if user and user.is_active:
        return user

    raise HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        "Authentication required",
        headers={"WWW-Authenticate": "Bearer"},
    )


def permissions_for(db: Session, user: User, project_id: str | None = None) -> set[str]:
    """Resolve the effective permission set for a user in a scope.

    Organization-wide grants always apply; project-scoped grants apply only to
    that project. Role definitions are read from the database so an org admin
    can reshape them (section 49) without a code change.
    """
    memberships = list(db.execute(select(Membership).where(Membership.user_id == user.id)).scalars())
    if not memberships:
        return set()

    org_ids = {m.organization_id for m in memberships}
    definitions: dict[tuple[str, str], list[str]] = {}
    for row in db.execute(
        select(RoleDefinition).where(RoleDefinition.organization_id.in_(org_ids))
    ).scalars():
        definitions[(row.organization_id, row.role)] = list(row.permissions or [])

    granted: set[str] = set()
    for membership in memberships:
        if membership.project_id and membership.project_id != project_id:
            continue
        perms = definitions.get(
            (membership.organization_id, membership.role),
            DEFAULT_ROLE_PERMISSIONS.get(membership.role, []),
        )
        granted.update(perms)
    return granted


def require(permission: str):
    """Dependency factory enforcing a single permission.

    Routes that operate inside a project pass `project_id` as a path parameter;
    when present it narrows which memberships count.
    """

    def dependency(
        request: Request,
        user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        project_id = request.path_params.get("project_id")
        granted = permissions_for(db, user, project_id)
        if permission not in granted:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Missing permission '{permission}' for this scope",
            )
        return user

    return dependency


def organization_id_for_project(db: Session, project_id: str) -> str | None:
    project = db.get(Project, project_id)
    if project is None or project.program is None:
        return None
    return project.program.organization_id


def ensure_role_definitions(db: Session, organization_id: str) -> None:
    """Seed the editable role table with the shipped defaults."""
    existing = {
        row.role
        for row in db.execute(
            select(RoleDefinition).where(RoleDefinition.organization_id == organization_id)
        ).scalars()
    }
    for role in Role.ALL:
        if role in existing:
            continue
        db.add(
            RoleDefinition(
                organization_id=organization_id,
                role=role,
                permissions=list(DEFAULT_ROLE_PERMISSIONS.get(role, [])),
                description=f"Shipped default for {role}. Editable per organization.",
            )
        )
    db.flush()


__all__ = [
    "Permission",
    "create_access_token",
    "decode_token",
    "ensure_role_definitions",
    "get_current_user",
    "hash_password",
    "permissions_for",
    "require",
    "verify_password",
]
