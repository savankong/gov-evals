"""Shared router helpers."""

from __future__ import annotations

import re

from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session

from ..models import Project, User


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "item"


def get_project(db: Session, project_id: str) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    return project


def fetch(db: Session, model, object_id: str, label: str):
    obj = db.get(model, object_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{label} not found")
    return obj


def actor_label(user: User | None) -> str:
    if user is None:
        return "system"
    return user.full_name or user.email


def client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


def audit_context(db: Session, project: Project | None, user: User | None, request: Request) -> dict:
    return {
        "actor_id": user.id if user else None,
        "actor_label": actor_label(user),
        "project_id": project.id if project else None,
        "organization_id": project.program.organization_id if project and project.program else None,
        "source_ip": client_ip(request),
    }
