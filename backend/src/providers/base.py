"""Shared data types for the music metadata provider layer (PLAN §6).

Routers and services consume only these dataclasses — provider-specific payload
shapes never leak past this module.
"""

from dataclasses import dataclass, field


class ProviderError(Exception):
    """An upstream music provider failed (network, rate limit, bad payload)."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class NotFound(ProviderError):
    """The requested album id does not exist at the provider."""


@dataclass
class SearchResult:
    """One album as returned by external search, normalized across providers."""

    source: str  # "deezer" | "musicbrainz"
    external_id: str  # Deezer album id or MusicBrainz release-group MBID
    title: str
    artist: str
    year: int | None = None
    track_count: int | None = None
    cover_url: str | None = None
    label: str | None = None
    # Populated on merged rows so import can pull metadata from both sources.
    deezer_id: int | None = None
    musicbrainz_release_group_id: str | None = None


@dataclass
class TrackInput:
    """One track of an imported album, ordered by position."""

    position: int
    title: str
    duration_seconds: int | None = None


@dataclass
class ImportedAlbum:
    """Full album metadata assembled from one or both providers."""

    source: str
    external_id: str
    title: str
    artist: str
    year: int | None = None
    label: str | None = None
    country: str | None = None
    musicbrainz_release_group_id: str | None = None
    deezer_id: int | None = None
    cover_url: str | None = None
    metadata: dict = field(default_factory=dict)
    tracks: list[TrackInput] = field(default_factory=list)
