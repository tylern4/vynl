"""Shared HTTP helpers for the music providers (PLAN §6).

Every provider request goes through this module so tests have a single seam:
inject an ``httpx.Client`` built on ``httpx.MockTransport`` with
``set_client()`` and no test ever touches the network.
"""

from __future__ import annotations

import threading
from typing import Any

import httpx

from .base import NotFound, ProviderError

DEEZER_BASE = "https://api.deezer.com"
MUSICBRAINZ_BASE = "https://musicbrainz.org/ws/2"
COVERART_BASE = "https://coverartarchive.org"

DEFAULT_TIMEOUT = 15.0

_client: httpx.Client | None = None
_client_lock = threading.Lock()


def _build_client() -> httpx.Client:
    # follow_redirects: CAA /front-500 answers 302 → archive.org (PLAN §6).
    return httpx.Client(timeout=DEFAULT_TIMEOUT, follow_redirects=True)


def get_client() -> httpx.Client:
    """Return the shared client, creating it on first use (thread-safe)."""
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = _build_client()
    return _client


def set_client(client: httpx.Client | None) -> None:
    """Test seam: inject a client (e.g. backed by ``httpx.MockTransport``) or reset."""
    global _client
    _client = client


def get_json(
    url: str,
    *,
    params: dict | None = None,
    headers: dict | None = None,
    not_found_statuses: tuple[int, ...] = (404,),
) -> Any:
    """GET ``url`` and return the decoded JSON body.

    Maps failures onto the provider protocol: transport errors and non-OK
    statuses become :class:`ProviderError` (reason includes status + a body
    snippet); 404 — or any status in ``not_found_statuses`` — becomes
    :class:`NotFound`.
    """
    client = get_client()
    try:
        response = client.get(url, params=params, headers=headers)
    except httpx.HTTPError as exc:
        raise ProviderError(f"request to {response_host(url)} failed: {exc}") from exc
    if response.status_code in not_found_statuses:
        raise NotFound(f"HTTP {response.status_code} from {response.url}")
    if response.status_code != 200:
        body = response.text[:200]
        raise ProviderError(f"HTTP {response.status_code} from {response.url}: {body}")
    try:
        return response.json()
    except ValueError as exc:
        raise ProviderError(f"invalid JSON from {response.url}") from exc


def url_exists(url: str) -> bool:
    """Check that ``url`` resolves to a 200 without downloading the resource.

    Uses HEAD (falling back to a streamed GET if the server rejects HEAD);
    the response body is never read. 404, 5xx and transport errors all mean
    "no" — artwork is best-effort and must never raise (PLAN §6: CAA 404 =
    no art).
    """
    client = get_client()
    try:
        response = client.head(url)
        if response.status_code == 405:  # server dislikes HEAD → probe with GET
            with client.stream("GET", url) as streamed:
                return streamed.status_code == 200
        return response.status_code == 200
    except httpx.HTTPError:
        return False


def response_host(url: str) -> str:
    try:
        return httpx.URL(url).host or url
    except Exception:  # noqa: BLE001 - only used for error text
        return url
