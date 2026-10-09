from datetime import datetime, timezone
from typing import Annotated, Iterable, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from .models import Album, Role, Track, UserStatus


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    invite_code: str | None = Field(default=None, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: EmailStr
    role: Role
    status: UserStatus


class UserAdminOut(UserOut):
    created_at: datetime


class RegisterOut(BaseModel):
    user: UserOut
    access_token: str | None = None


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class RoleUpdate(BaseModel):
    role: Role


class PasswordReset(BaseModel):
    password: str = Field(min_length=8, max_length=128)


class UserUpdate(BaseModel):
    status: UserStatus | None = None
    role: Role | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)


class UserCreate(BaseModel):
    """Admin-only direct user creation (issue #9). Skips the invite/pending
    flow: the admin supplies credentials and the account is active by default.
    """

    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: Role = Role.user
    status: UserStatus = UserStatus.active


# --- Collection API (PLAN §5, issue #3) -------------------------------------


class SearchResultOut(BaseModel):
    """One external search hit, normalized to the §5 SearchResult JSON.

    The provider dataclass carries extra ids (``deezer_id`` /
    ``musicbrainz_release_group_id``) used internally by import; those are
    deliberately not part of the wire contract.
    """

    source: str  # "deezer" | "musicbrainz" | "itunes" | "discogs"
    external_id: str
    title: str
    artist: str
    year: int | None = None
    track_count: int | None = None
    cover_url: str | None = None
    label: str | None = None


class AlbumImportRequest(BaseModel):
    source: Literal["deezer", "musicbrainz", "itunes", "discogs"]
    external_id: str = Field(min_length=1, max_length=64)


class ManualTrackInput(BaseModel):
    """One track row from ``POST /albums/manual`` (issue #11).

    Positions are auto-assigned 1..n server-side; ``duration_seconds`` is
    optional (null when omitted).
    """

    title: str = Field(min_length=1, max_length=500)
    duration_seconds: int | None = Field(default=None, ge=0)

    @field_validator("title")
    @classmethod
    def _title_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Track title cannot be blank")
        return value


class ManualAlbumInput(BaseModel):
    """Body of ``POST /api/albums/manual`` — a manually entered album.

    Title/artist are required (trimmed, 1..500); everything else optional.
    No provider is involved, so ``external_id`` is a client-free UUID and no
    artwork is fetched at creation time.
    """

    title: str = Field(min_length=1, max_length=500)
    artist: str = Field(min_length=1, max_length=500)
    year: int | None = None
    label: str | None = Field(default=None, max_length=255)
    country: str | None = Field(default=None, max_length=8)
    favorite: bool = False
    note: str | None = None
    tracks: list[ManualTrackInput] = Field(default_factory=list)

    @field_validator("title", "artist")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Title and artist cannot be blank")
        return value

    @field_validator("year")
    @classmethod
    def _year_sane(cls, value: int | None) -> int | None:
        if value is None:
            return value
        upper = datetime.now(timezone.utc).year + 1
        if not (1000 <= value <= upper):
            raise ValueError(f"Year must be between 1000 and {upper}")
        return value


class TrackPreviewOut(BaseModel):
    """One dry-run track (issue #13); mirrors the TrackInput dataclass."""

    position: int
    title: str
    duration_seconds: int | None = None


class AlbumSourceBreakdown(BaseModel):
    """Which provider fed each part of an assembled (dry-run) album (#13).

    Any field may be ``None`` when that part has no source (e.g. no artwork
    anywhere). Values are provider names: ``"musicbrainz"``, ``"deezer"``,
    ``"itunes"``, ``"discogs"``, ``"cover_art_archive"``.
    """

    metadata_source: str | None = None
    tracklist_source: str | None = None
    artwork_source: str | None = None


class AlbumPreviewOut(BaseModel):
    """Dry-run of what importing {source, external_id} would persist (#13).

    Same assembly code path as import (incl. twin discovery), but nothing is
    written and no 409 is raised — the frontend shows this before committing.
    """

    source: str
    external_id: str
    title: str
    artist: str
    year: int | None = None
    label: str | None = None
    country: str | None = None
    cover_url: str | None = None
    track_count: int
    tracks: list[TrackPreviewOut] = Field(default_factory=list)
    source_breakdown: AlbumSourceBreakdown
    tracklists_by_source: dict[str, list[TrackPreviewOut]] = Field(
        default_factory=dict
    )


class TrackOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    position: int
    title: str
    duration_seconds: int | None = None


class AlbumOut(BaseModel):
    id: int
    title: str
    artist: str
    year: int | None = None
    label: str | None = None
    country: str | None = None
    source: str  # "deezer" | "musicbrainz" | "itunes" | "discogs" | "manual"
    external_id: str
    cover_url: str | None = None
    track_count: int
    favorite: bool
    note: str | None = None
    last_played_at: datetime | None = None
    tags: list[str] = Field(default_factory=list)
    created_at: datetime
    # Present (sorted by position) on detail responses; empty list on lists.
    tracks: list[TrackOut] = Field(default_factory=list)


def album_to_out(album: Album, *, tracks: Iterable[Track] | None = None) -> AlbumOut:
    """Build the PLAN §5 AlbumOut for one album.

    ``tracks=None`` leaves them empty (list views never touch the relationship
    — no N+1); pass an iterable (e.g. ``album.tracks``) for the detail shape.
    Tags are always included, sorted by name.
    """
    return AlbumOut(
        id=album.id,
        title=album.title,
        artist=album.artist,
        year=album.year,
        label=album.label,
        country=album.country,
        source=album.source,
        external_id=album.external_id,
        cover_url=album.cover_url,
        track_count=album.track_count,
        favorite=album.favorite,
        note=album.note,
        last_played_at=album.last_played_at,
        tags=sorted(tag.name for tag in album.tags),
        created_at=album.created_at,
        tracks=(
            sorted(
                (TrackOut.model_validate(track) for track in tracks),
                key=lambda t: t.position,
            )
            if tracks is not None
            else []
        ),
    )


class AlbumUpdate(BaseModel):
    favorite: bool | None = None
    note: str | None = None
    year: int | None = Field(default=None, ge=1800, le=2300)
    label: str | None = Field(default=None, max_length=255)


class TagCreate(BaseModel):
    name: str = Field(min_length=1, max_length=60)


class TagOut(BaseModel):
    id: int
    name: str
    album_count: int


class AlbumTagsPut(BaseModel):
    tags: list[Annotated[str, Field(min_length=1, max_length=60)]]


class PlayCreate(BaseModel):
    played_at: datetime | None = None


class PlayOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    played_at: datetime


class TrackSearchAlbum(BaseModel):
    id: int
    title: str
    artist: str
    year: int | None = None
    cover_url: str | None = None


class TrackSearchOut(BaseModel):
    id: int
    title: str
    duration_seconds: int | None = None
    position: int
    album: TrackSearchAlbum


class RecommendationOut(BaseModel):
    album: AlbumOut
    reason: str
    days_since_played: int | None = None
