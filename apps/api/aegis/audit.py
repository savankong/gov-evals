"""Hash-chained audit log (section 50).

Each event stores the digest of the previous event, so removing or editing a
row inside the application breaks the chain and `verify_chain` reports it.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .hashing import content_hash
from .models import AuditEvent, utcnow


def _timestamp_key(value: datetime | None) -> str | None:
    """Normalise a timestamp for hashing.

    SQLite returns naive datetimes while Postgres returns aware ones. Both were
    written as UTC, so a naive value is interpreted as UTC. Without this the
    chain would verify on one backend and fail on the other.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _digest(event: AuditEvent, prev_hash: str) -> str:
    return content_hash(
        {
            "prev": prev_hash,
            "action": event.action,
            "object_type": event.object_type,
            "object_id": event.object_id,
            "actor": event.actor_id,
            "detail": event.detail,
            "created_at": _timestamp_key(event.created_at),
        }
    )


def record(
    db: Session,
    *,
    action: str,
    object_type: str,
    object_id: str | None = None,
    actor_id: str | None = None,
    actor_label: str | None = None,
    organization_id: str | None = None,
    project_id: str | None = None,
    detail: dict | None = None,
    source_ip: str | None = None,
) -> AuditEvent:
    prev = db.execute(
        select(AuditEvent).order_by(AuditEvent.sequence.desc()).limit(1)
    ).scalar_one_or_none()
    prev_hash = prev.hash if prev else ""

    event = AuditEvent(
        organization_id=organization_id,
        project_id=project_id,
        actor_id=actor_id,
        actor_label=actor_label,
        action=action,
        object_type=object_type,
        object_id=object_id,
        detail=detail or {},
        source_ip=source_ip,
        prev_hash=prev_hash,
        # Set explicitly rather than left to the column default, because the
        # value is part of the digest and must exist before it is computed.
        created_at=utcnow(),
    )
    event.hash = _digest(event, prev_hash)
    db.add(event)
    db.flush()
    return event


def verify_chain(db: Session, limit: int | None = None) -> dict:
    """Recompute the chain and report the first break, if any."""
    query = select(AuditEvent).order_by(AuditEvent.sequence.asc())
    if limit:
        query = query.limit(limit)
    events = list(db.execute(query).scalars())

    prev_hash = ""
    for event in events:
        expected = _digest(event, prev_hash)
        if event.prev_hash != prev_hash or event.hash != expected:
            return {
                "valid": False,
                "checked": len(events),
                "broken_at_sequence": event.sequence,
                "broken_at_id": event.id,
            }
        prev_hash = event.hash

    return {"valid": True, "checked": len(events), "head": prev_hash}
