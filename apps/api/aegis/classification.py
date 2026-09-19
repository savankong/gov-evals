"""Classification handling.

A deployment runs on infrastructure accredited to hold data up to some level.
Commercial cloud regions are not accredited for CUI or above, and a platform
that merely documents that fact is relying on every operator to remember it
while typing a dropdown.

Setting `AEGIS_MAX_CLASSIFICATION` makes the deployment refuse artifacts above
its ceiling at the API boundary, which is the only place the refusal is
reliable. The default is no ceiling, so an accredited deployment behaves
exactly as before.
"""

from __future__ import annotations

from fastapi import HTTPException

from .config import get_settings
from .enums import Classification

#: Ordering used for comparisons. Extending the vocabulary means extending this.
MARKING_RANK: dict[str, int] = {
    Classification.UNCLASSIFIED: 0,
    Classification.CUI: 1,
    Classification.CONFIDENTIAL: 2,
    Classification.SECRET: 3,
    Classification.TOP_SECRET: 4,
}


def rank(marking: str | None) -> int:
    """Rank a marking, tolerating banners like "SECRET//NOFORN".

    An unrecognised marking ranks as the highest level it contains rather than
    as unclassified, so a caveat or a typo never downgrades a comparison.
    """
    if not marking:
        return 0
    upper = marking.upper()
    matches = [value for key, value in MARKING_RANK.items() if key in upper]
    return max(matches) if matches else 0


def ceiling() -> str | None:
    value = get_settings().max_classification
    return value or None


def exceeds_ceiling(marking: str | None) -> bool:
    limit = ceiling()
    if not limit:
        return False
    return rank(marking) > rank(limit)


def enforce(marking: str | None, *, field: str = "classification") -> str | None:
    """Reject an artifact marked above this deployment's ceiling.

    Raises 422 rather than 403: the request is well-formed and the caller is
    authorised, but this deployment is not a permissible location for the data.
    """
    if not exceeds_ceiling(marking):
        return marking
    limit = ceiling()
    # 422 written literally: Starlette renamed the constant, and this code
    # should not track which name the installed version happens to use.
    raise HTTPException(
        422,
        detail=(
            f"This deployment is configured to hold data up to {limit}. It cannot accept an "
            f"artifact marked {marking!r} ({field}). Use a deployment accredited for that "
            "marking, or raise AEGIS_MAX_CLASSIFICATION if this one is accredited for it."
        ),
    )


def describe() -> dict:
    """Advertise the ceiling so a client can show it before data is entered."""
    limit = ceiling()
    return {
        "max_classification": limit,
        "permitted": [m for m in Classification.ALL if rank(m) <= rank(limit)]
        if limit
        else list(Classification.ALL),
        "note": (
            f"This deployment accepts artifacts marked up to {limit}. Artifacts above that "
            "marking are refused at the API."
            if limit
            else "No classification ceiling is configured for this deployment."
        ),
    }
