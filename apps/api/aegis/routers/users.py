"""Local account administration (section 49).

Until now the only way to create an account was to bootstrap one at startup,
and the only way to change a password was to redeploy. That made routine
operational acts -- adding a colleague, rotating a credential, removing access
for someone who has left -- into deployment events.

Two rules shape what is here.

**Accounts are deactivated, never deleted.** The audit chain names the actor on
every recorded action, and evidence references the reviewer who judged it.
Deleting a user would leave those references pointing at nothing, which is a
worse outcome than a disabled row. There is no DELETE endpoint, deliberately.

**Changing your own password is a different act from an administrator changing
someone else's.** The first proves you hold the current credential; the second
does not and cannot. They are separate endpoints so the audit record says which
happened, rather than recording both as "password changed".
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..config import DEFAULT_BOOTSTRAP_PASSWORD
from ..db import get_db
from ..enums import Permission, Role
from ..models import Membership, Organization, User
from ..schemas import (
    MembershipIn,
    MembershipOut,
    PasswordChange,
    PasswordReset,
    UserAccountOut,
    UserCreate,
    UserUpdate,
)
from ..security import get_current_user, hash_password, require, verify_password
from .deps import client_ip, fetch

router = APIRouter(tags=["users"])

MIN_PASSWORD_LENGTH = 12


def _check_password(password: str) -> None:
    """Refuse the two passwords that are worse than a weak one.

    A short password, and the one this product ships with -- which is public,
    is in the README, and is the first thing anyone would try.
    """
    if len(password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"A password must be at least {MIN_PASSWORD_LENGTH} characters.",
        )
    if password == DEFAULT_BOOTSTRAP_PASSWORD:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "That is the shipped default password. It is published in this "
            "repository, so it is not a credential.",
        )


def _is_local(user: User) -> bool:
    return (user.identity_provider or "local") == "local"


def _require_local(user: User) -> None:
    """A federated account has no local password, and must not gain one.

    Setting one would create a second way in that whoever configured the
    identity provider never agreed to and would not see.
    """
    if not _is_local(user):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{user.email} signs in through {user.identity_provider}. Giving it a "
            "local password would add a second way in that the identity provider "
            "does not know about.",
        )


def _out(user: User) -> dict:
    payload = UserAccountOut.model_validate(user).model_dump()
    payload["has_local_password"] = bool(user.password_hash)
    return payload


def _other_active_admins(db: Session, user: User) -> int:
    """How many *other* accounts could still administer the organisations this
    one administers. Zero means removing this access locks everybody out."""
    org_ids = [m.organization_id for m in user.memberships if m.role == Role.ORG_ADMIN]
    if not org_ids:
        return 1  # not an admin anywhere; nothing to strand

    rows = db.execute(
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(
            Membership.organization_id.in_(org_ids),
            Membership.role == Role.ORG_ADMIN,
            Membership.user_id != user.id,
            User.is_active.is_(True),
        )
    ).all()
    return len(rows)


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------


@router.get("/users", response_model=list[UserAccountOut])
def list_users(
    include_inactive: bool = True,
    db: Session = Depends(get_db),
    _: User = Depends(require(Permission.ORG_ADMINISTER)),
):
    """Every account, deactivated ones included by default.

    A deactivated account that vanishes from the list is one nobody remembers
    to review.
    """
    users = list(db.execute(select(User).order_by(User.email)).scalars())
    if not include_inactive:
        users = [u for u in users if u.is_active]
    return [_out(u) for u in users]


@router.get("/users/{user_id}", response_model=UserAccountOut)
def read_user(
    user_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require(Permission.ORG_ADMINISTER)),
):
    return _out(fetch(db, User, user_id, "User"))


# ---------------------------------------------------------------------------
# Creating and amending
# ---------------------------------------------------------------------------


@router.post("/users", response_model=UserAccountOut, status_code=201)
def create_user(
    payload: UserCreate,
    request: Request,
    db: Session = Depends(get_db),
    actor: User = Depends(require(Permission.ORG_ADMINISTER)),
):
    """Create a local account, optionally with its opening grant.

    The role is taken here rather than in a second call because an account
    created with no membership can do nothing, and an account that can do
    nothing is one somebody grants too much to later, in a hurry.
    """
    _check_password(payload.password)

    email = payload.email.strip().lower()
    if db.execute(select(User).where(User.email == email)).scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, f"{email} already has an account.")

    if payload.role and payload.role not in Role.ALL:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown role '{payload.role}'.")
    if payload.role and not payload.organization_id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "A role needs an organization_id to be granted in.",
        )

    user = User(
        email=email,
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
        identity_provider="local",
    )
    db.add(user)
    db.flush()

    if payload.organization_id and payload.role:
        fetch(db, Organization, payload.organization_id, "Organization")
        db.add(
            Membership(
                user_id=user.id,
                organization_id=payload.organization_id,
                role=payload.role,
            )
        )

    audit.record(
        db,
        action="user.created",
        object_type="user",
        object_id=user.id,
        actor_id=actor.id,
        actor_label=actor.email,
        organization_id=payload.organization_id,
        source_ip=client_ip(request),
        detail={"email": email, "role": payload.role},
    )
    db.commit()
    db.refresh(user)
    return _out(user)


@router.patch("/users/{user_id}", response_model=UserAccountOut)
def update_user(
    user_id: str,
    payload: UserUpdate,
    request: Request,
    db: Session = Depends(get_db),
    actor: User = Depends(require(Permission.ORG_ADMINISTER)),
):
    """Rename or deactivate. There is no delete, by design -- see the module docstring."""
    user = fetch(db, User, user_id, "User")
    fields = payload.model_dump(exclude_unset=True)

    if fields.get("is_active") is False:
        if user.id == actor.id:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "You cannot deactivate your own account. Ask another administrator.",
            )
        if _other_active_admins(db, user) == 0:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"{user.email} is the only active administrator of an organisation. "
                "Deactivating it would leave nobody able to administer this "
                "deployment. Grant somebody else the role first.",
            )

    before_active = user.is_active
    for field, value in fields.items():
        setattr(user, field, value)

    action = "user.updated"
    if "is_active" in fields and fields["is_active"] != before_active:
        action = "user.deactivated" if not fields["is_active"] else "user.reactivated"

    audit.record(
        db,
        action=action,
        object_type="user",
        object_id=user.id,
        actor_id=actor.id,
        actor_label=actor.email,
        source_ip=client_ip(request),
        detail={"subject": user.email, "fields": sorted(fields)},
    )
    db.commit()
    db.refresh(user)
    return _out(user)


# ---------------------------------------------------------------------------
# Passwords
# ---------------------------------------------------------------------------


@router.post("/users/me/password", status_code=200)
def change_my_password(
    payload: PasswordChange,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Change your own, proving you hold the current one.

    Required even for an administrator. An administrator who has forgotten
    their password should be reset by another administrator, so the record
    shows that is what happened.
    """
    _require_local(user)
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "The current password is wrong.")
    _check_password(payload.new_password)

    user.password_hash = hash_password(payload.new_password)
    audit.record(
        db,
        action="user.password_changed",
        object_type="user",
        object_id=user.id,
        actor_id=user.id,
        actor_label=user.email,
        source_ip=client_ip(request),
        detail={"by": "self"},
    )
    db.commit()
    return {
        "status": "ok",
        # Said rather than discovered: tokens are signed, not looked up, so one
        # issued before this change stays valid until it expires. Rotating
        # AEGIS_SECRET_KEY is what invalidates every session at once.
        "note": (
            "Existing access tokens remain valid until they expire. Rotate "
            "AEGIS_SECRET_KEY to end every session immediately."
        ),
    }


@router.post("/users/{user_id}/password", status_code=200)
def reset_password(
    user_id: str,
    payload: PasswordReset,
    request: Request,
    db: Session = Depends(get_db),
    actor: User = Depends(require(Permission.ORG_ADMINISTER)),
):
    """Set somebody else's password.

    Refused on your own account: that is the other endpoint, which requires the
    current password. Keeping them apart means the audit log distinguishes
    "changed their own" from "had theirs changed for them", which is the
    difference anyone reviewing it cares about.
    """
    user = fetch(db, User, user_id, "User")
    if user.id == actor.id:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Use /users/me/password to change your own, which requires the current one.",
        )
    _require_local(user)
    _check_password(payload.new_password)

    user.password_hash = hash_password(payload.new_password)
    audit.record(
        db,
        action="user.password_reset",
        object_type="user",
        object_id=user.id,
        actor_id=actor.id,
        actor_label=actor.email,
        source_ip=client_ip(request),
        detail={"subject": user.email, "by": "administrator"},
    )
    db.commit()
    return {
        "status": "ok",
        "note": (
            f"{user.email} can sign in with the new password. Existing tokens "
            "remain valid until they expire."
        ),
    }


# ---------------------------------------------------------------------------
# Access
# ---------------------------------------------------------------------------


@router.post("/users/{user_id}/memberships", response_model=MembershipOut, status_code=201)
def grant_membership(
    user_id: str,
    payload: MembershipIn,
    request: Request,
    db: Session = Depends(get_db),
    actor: User = Depends(require(Permission.ORG_ADMINISTER)),
):
    user = fetch(db, User, user_id, "User")
    fetch(db, Organization, payload.organization_id, "Organization")
    if payload.role not in Role.ALL:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown role '{payload.role}'.")

    existing = db.execute(
        select(Membership).where(
            Membership.user_id == user.id,
            Membership.organization_id == payload.organization_id,
            Membership.project_id == payload.project_id,
            Membership.role == payload.role,
        )
    ).scalar_one_or_none()
    if existing:
        return existing

    membership = Membership(user_id=user.id, **payload.model_dump())
    db.add(membership)
    db.flush()
    audit.record(
        db,
        action="membership.granted",
        object_type="user",
        object_id=user.id,
        actor_id=actor.id,
        actor_label=actor.email,
        organization_id=payload.organization_id,
        project_id=payload.project_id,
        source_ip=client_ip(request),
        detail={"subject": user.email, "role": payload.role},
    )
    db.commit()
    db.refresh(membership)
    return membership


@router.delete("/users/{user_id}/memberships/{membership_id}", status_code=200)
def revoke_membership(
    user_id: str,
    membership_id: str,
    request: Request,
    db: Session = Depends(get_db),
    actor: User = Depends(require(Permission.ORG_ADMINISTER)),
):
    """Revoke a grant.

    This deletes an authorisation, not a person: the user row and everything
    their actions are recorded against stay exactly where they were.
    """
    user = fetch(db, User, user_id, "User")
    membership = fetch(db, Membership, membership_id, "Membership")
    if membership.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Membership not found")

    if membership.role == Role.ORG_ADMIN and _other_active_admins(db, user) == 0:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "That is the last active administrator grant for this organisation. "
            "Revoking it would leave nobody able to administer this deployment.",
        )

    db.delete(membership)
    audit.record(
        db,
        action="membership.revoked",
        object_type="user",
        object_id=user.id,
        actor_id=actor.id,
        actor_label=actor.email,
        organization_id=membership.organization_id,
        source_ip=client_ip(request),
        detail={"subject": user.email, "role": membership.role},
    )
    db.commit()
    return {"status": "ok", "revoked": membership_id}
