"""episodes, episode watches and episode alerts

Revision ID: a1c3e5f70b21
Revises: 8b2c7d85f62d
Create Date: 2026-08-09

Series were tracked whole, so nothing could say which episodes someone had
seen or what to put on next. This adds the episode catalog, points a watch
event at an episode, and gives a notification somewhere to record which
episode it announced.

Both new columns are nullable with no server default, deliberately: every
existing watch event is a film or a whole-series log, and rewriting them to
point at episodes would be inventing history that was never recorded.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1c3e5f70b21"
down_revision: str | None = "8b2c7d85f62d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "episodes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("title_id", sa.Uuid(), nullable=False),
        sa.Column("tmdb_id", sa.Integer(), nullable=True),
        sa.Column("season_number", sa.Integer(), nullable=False),
        sa.Column("episode_number", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=500), nullable=True),
        sa.Column("overview", sa.String(length=4000), nullable=True),
        sa.Column("air_date", sa.Date(), nullable=True),
        sa.Column("runtime", sa.Integer(), nullable=True),
        sa.Column("still_path", sa.String(length=200), nullable=True),
        sa.Column("refreshed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["title_id"], ["titles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "title_id",
            "season_number",
            "episode_number",
            name="uq_episodes_title_season_episode",
        ),
    )
    op.create_index("ix_episodes_title_id", "episodes", ["title_id"])
    op.create_index("ix_episodes_title_air", "episodes", ["title_id", "air_date"])
    op.create_index("ix_episodes_air_date", "episodes", ["air_date"])

    op.add_column("watch_events", sa.Column("episode_id", sa.Uuid(), nullable=True))
    op.create_index("ix_watch_events_episode_id", "watch_events", ["episode_id"])
    op.create_foreign_key(
        "fk_watch_events_episode_id",
        "watch_events",
        "episodes",
        ["episode_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.add_column("notifications", sa.Column("episode_id", sa.Uuid(), nullable=True))
    op.create_index("ix_notifications_episode_id", "notifications", ["episode_id"])
    op.create_foreign_key(
        "fk_notifications_episode_id",
        "notifications",
        "episodes",
        ["episode_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("fk_notifications_episode_id", "notifications", type_="foreignkey")
    op.drop_index("ix_notifications_episode_id", table_name="notifications")
    op.drop_column("notifications", "episode_id")

    op.drop_constraint("fk_watch_events_episode_id", "watch_events", type_="foreignkey")
    op.drop_index("ix_watch_events_episode_id", table_name="watch_events")
    op.drop_column("watch_events", "episode_id")

    op.drop_index("ix_episodes_air_date", table_name="episodes")
    op.drop_index("ix_episodes_title_air", table_name="episodes")
    op.drop_index("ix_episodes_title_id", table_name="episodes")
    op.drop_table("episodes")
