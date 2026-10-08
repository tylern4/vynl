"""External album search for the "add album" flow (PLAN §5).

Thin wrapper over the provider layer: ``search_albums_detailed`` merges/
dedupes Deezer + MusicBrainz and reports which provider (if any) degraded —
that name is surfaced as §5's ``X-Search-Degraded`` header while the body
stays a plain ``SearchResult[]`` array. Only an all-providers failure
surfaces as 502.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from .. import providers
from ..auth import get_current_user
from ..models import User
from ..schemas import SearchResultOut

router = APIRouter(prefix="/search", tags=["search"])

DEGRADED_HEADER = "X-Search-Degraded"


@router.get("/albums", response_model=list[SearchResultOut])
def search_albums(
    response: Response,
    current_user: Annotated[User, Depends(get_current_user)],
    q: Annotated[str, Query(min_length=1, max_length=200)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
):
    try:
        outcome = providers.search_albums_detailed(q, limit=limit)
    except providers.ProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Album search failed: {exc.reason}",
        )
    if outcome.degraded:
        # §5: `X-Search-Degraded: deezer` — the failing provider's name(s).
        # Both failing raises above, so this is a single name in practice.
        response.headers[DEGRADED_HEADER] = ",".join(outcome.degraded)
    return outcome.results
