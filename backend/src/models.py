import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Role(str, enum.Enum):
    admin = "admin"
    user = "user"
    read_only = "read_only"


class UserStatus(str, enum.Enum):
    pending = "pending"
    active = "active"
    denied = "denied"


album_tags = Table(
    "album_tags",
    Base.metadata,
    Column("album_id", ForeignKey("albums.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(
        Enum(Role, name="userrole"), nullable=False
    )
    status: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus, name="userstatus"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    albums: Mapped[list["Album"]] = relationship(
        back_populates="user", passive_deletes=True
    )
    plays: Mapped[list["Play"]] = relationship(
        back_populates="user", passive_deletes=True
    )


class Album(Base):
    __tablename__ = "albums"
    __table_args__ = (
        # The shelf is shared, so provider identity dedupes globally. ``user_id``
        # is kept only as attribution ("who added it"), never for scoping.
        UniqueConstraint("source", "external_id", name="uq_albums_source_external"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(500), index=True)
    artist: Mapped[str] = mapped_column(String(500), index=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    country: Mapped[str | None] = mapped_column(String(8), nullable=True)
    source: Mapped[str] = mapped_column(String(20))
    external_id: Mapped[str] = mapped_column(String(64))
    musicbrainz_release_group_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True
    )
    deezer_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    cover_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    cover_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    track_count: Mapped[int] = mapped_column(Integer, default=0)
    favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_played_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    # "metadata" is reserved by SQLAlchemy's declarative system, so the Python
    # attribute is metadata_ while the column keeps the PLAN §4 name.
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, default=dict, server_default="'{}'"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped[User | None] = relationship(back_populates="albums")
    tracks: Mapped[list["Track"]] = relationship(
        back_populates="album", passive_deletes=True
    )
    plays: Mapped[list["Play"]] = relationship(
        back_populates="album", passive_deletes=True
    )
    tags: Mapped[list["Tag"]] = relationship(
        secondary=album_tags, back_populates="albums", passive_deletes=True
    )


class Track(Base):
    __tablename__ = "tracks"
    __table_args__ = (
        UniqueConstraint("album_id", "position", name="uq_tracks_album_position"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    album_id: Mapped[int] = mapped_column(
        ForeignKey("albums.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(500))
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)

    album: Mapped[Album] = relationship(back_populates="tracks")


class Tag(Base):
    __tablename__ = "tags"
    __table_args__ = (
        # Shared-shelf tags are global: a name exists once for the whole shelf.
        UniqueConstraint("name", name="uq_tags_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(60))

    albums: Mapped[list[Album]] = relationship(
        secondary=album_tags, back_populates="tags", passive_deletes=True
    )


class Play(Base):
    __tablename__ = "plays"

    id: Mapped[int] = mapped_column(primary_key=True)
    album_id: Mapped[int] = mapped_column(
        ForeignKey("albums.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    played_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    album: Mapped[Album] = relationship(back_populates="plays")
    user: Mapped[User | None] = relationship(back_populates="plays")
