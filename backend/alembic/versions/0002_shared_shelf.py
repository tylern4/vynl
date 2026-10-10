"""Shared shelf: global album dedupe + global tags.

The shelf used to be per-user, so albums deduped on ``(user_id, source,
external_id)`` and tags were scoped by ``user_id``. This revision makes both
global: albums dedupe on ``(source, external_id)`` and tag names are unique
across the whole shelf. Duplicate imports/tags from a multi-user database are
collapsed (earliest row wins) before the new constraints are added.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-09

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())

    # --- albums: global (source, external_id) uniqueness --------------------
    if "albums" in tables:
        # Collapse cross-user duplicate imports of the same provider release
        # into one shared row (earliest id wins). Tracks/plays cascade away.
        op.execute(
            """
            DELETE FROM albums a
            USING albums b
            WHERE a.source = b.source
              AND a.external_id = b.external_id
              AND a.id > b.id
            """
        )
        op.drop_constraint(
            "uq_albums_user_source_external", "albums", type_="unique"
        )
        op.create_unique_constraint(
            "uq_albums_source_external", "albums", ["source", "external_id"]
        )

    # --- tags: one global name ----------------------------------------------
    if "tags" in tables:
        # Repoint album links at the surviving tag before dropping duplicates
        # (album_tags has ON DELETE CASCADE, so links must move first).
        op.execute(
            """
            UPDATE album_tags at
            SET tag_id = dup.keep_id
            FROM (
                SELECT id, min(id) OVER (PARTITION BY name) AS keep_id
                FROM tags
            ) AS dup
            WHERE at.tag_id = dup.id
              AND dup.keep_id <> dup.id
            """
        )
        op.execute(
            """
            DELETE FROM tags t
            USING tags d
            WHERE t.name = d.name AND t.id > d.id
            """
        )
        op.drop_constraint("tags_user_id_fkey", "tags", type_="foreignkey")
        op.drop_index("ix_tags_user_id", table_name="tags")
        op.drop_constraint("uq_tags_user_name", "tags", type_="unique")
        op.drop_column("tags", "user_id")
        op.create_unique_constraint("uq_tags_name", "tags", ["name"])


def downgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())

    if "tags" in tables:
        # Best-effort: the original per-user ownership is not recoverable, so
        # re-added tags carry a NULL user_id (no uniqueness pressure).
        op.drop_constraint("uq_tags_name", "tags", type_="unique")
        op.add_column("tags", sa.Column("user_id", sa.Integer(), nullable=True))
        op.create_index("ix_tags_user_id", "tags", ["user_id"])
        op.create_foreign_key(
            "tags_user_id_fkey",
            "tags",
            "users",
            ["user_id"],
            ["id"],
            ondelete="CASCADE",
        )
        op.create_unique_constraint("uq_tags_user_name", "tags", ["user_id", "name"])

    if "albums" in tables:
        op.drop_constraint("uq_albums_source_external", "albums", type_="unique")
        op.create_unique_constraint(
            "uq_albums_user_source_external",
            "albums",
            ["user_id", "source", "external_id"],
        )
