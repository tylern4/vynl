"""Initial schema: users, albums, tracks, tags, album_tags, and plays tables.

Revision ID: 0001
Revises:
Create Date: 2026-10-08

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())

    if "users" not in existing:
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("email", sa.String(length=255), nullable=False),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("password_hash", sa.String(length=255), nullable=False),
            sa.Column(
                "role",
                sa.Enum("admin", "user", "read_only", name="userrole"),
                nullable=False,
            ),
            sa.Column(
                "status",
                sa.Enum("pending", "active", "denied", name="userstatus"),
                nullable=False,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
        )
        op.create_index("ix_users_email", "users", ["email"], unique=True)

    if "albums" not in existing:
        op.create_table(
            "albums",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column("title", sa.String(length=500), nullable=False),
            sa.Column("artist", sa.String(length=500), nullable=False),
            sa.Column("year", sa.Integer(), nullable=True),
            sa.Column("label", sa.String(length=255), nullable=True),
            sa.Column("country", sa.String(length=8), nullable=True),
            sa.Column("source", sa.String(length=20), nullable=False),
            sa.Column("external_id", sa.String(length=64), nullable=False),
            sa.Column(
                "musicbrainz_release_group_id", sa.String(length=36), nullable=True
            ),
            sa.Column("deezer_id", sa.BigInteger(), nullable=True),
            sa.Column("cover_path", sa.String(length=500), nullable=True),
            sa.Column("cover_url", sa.String(length=1000), nullable=True),
            sa.Column("track_count", sa.Integer(), nullable=False),
            sa.Column("favorite", sa.Boolean(), nullable=False),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("last_played_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "metadata",
                postgresql.JSONB(astext_type=sa.Text()),
                server_default=sa.text("'{}'"),
                nullable=False,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
            sa.UniqueConstraint(
                "user_id", "source", "external_id", name="uq_albums_user_source_external"
            ),
        )
        op.create_index("ix_albums_user_id", "albums", ["user_id"])
        op.create_index("ix_albums_title", "albums", ["title"])
        op.create_index("ix_albums_artist", "albums", ["artist"])
        op.create_index(
            "ix_albums_musicbrainz_release_group_id",
            "albums",
            ["musicbrainz_release_group_id"],
        )
        op.create_index("ix_albums_last_played_at", "albums", ["last_played_at"])

    if "tracks" not in existing:
        op.create_table(
            "tracks",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("album_id", sa.Integer(), nullable=False),
            sa.Column("position", sa.Integer(), nullable=False),
            sa.Column("title", sa.String(length=500), nullable=False),
            sa.Column("duration_seconds", sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(["album_id"], ["albums.id"], ondelete="CASCADE"),
            sa.UniqueConstraint(
                "album_id", "position", name="uq_tracks_album_position"
            ),
        )
        op.create_index("ix_tracks_album_id", "tracks", ["album_id"])

    if "tags" not in existing:
        op.create_table(
            "tags",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=60), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("user_id", "name", name="uq_tags_user_name"),
        )
        op.create_index("ix_tags_user_id", "tags", ["user_id"])

    if "album_tags" not in existing:
        op.create_table(
            "album_tags",
            sa.Column("album_id", sa.Integer(), nullable=False),
            sa.Column("tag_id", sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(["album_id"], ["albums.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["tag_id"], ["tags.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("album_id", "tag_id"),
        )

    if "plays" not in existing:
        op.create_table(
            "plays",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("album_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column(
                "played_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["album_id"], ["albums.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        )
        op.create_index("ix_plays_album_id", "plays", ["album_id"])
        op.create_index("ix_plays_played_at", "plays", ["played_at"])


def downgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())

    if "plays" in existing:
        op.drop_table("plays")
    if "album_tags" in existing:
        op.drop_table("album_tags")
    if "tags" in existing:
        op.drop_table("tags")
    if "tracks" in existing:
        op.drop_table("tracks")
    if "albums" in existing:
        op.drop_table("albums")
    if "users" in existing:
        op.drop_table("users")
    sa.Enum(name="userstatus").drop(bind, checkfirst=True)
    sa.Enum(name="userrole").drop(bind, checkfirst=True)
