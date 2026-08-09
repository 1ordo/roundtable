import uuid
from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin


class Title(Base, CreatedAtMixin):
    """One movie or series, cached from TMDB. raw_tmdb keeps the full payload
    so later features (embeddings, tagging) can reprocess without refetching."""

    __tablename__ = "titles"
    __table_args__ = (
        UniqueConstraint("tmdb_id", "type", name="uq_titles_tmdb_id_type"),
        Index("ix_titles_name", "name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tmdb_id: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String(8))  # movie | tv
    name: Mapped[str] = mapped_column(String(500))
    original_name: Mapped[str | None] = mapped_column(String(500))
    year: Mapped[int | None] = mapped_column(Integer)
    overview: Mapped[str | None] = mapped_column(String(8000))
    original_language: Mapped[str | None] = mapped_column(String(8))
    runtime: Mapped[int | None] = mapped_column(Integer)  # minutes; tv: episode runtime
    genres: Mapped[list] = mapped_column(JSONB, default=list)  # [{id, name}]
    keywords: Mapped[list] = mapped_column(JSONB, default=list)  # [str]
    poster_path: Mapped[str | None] = mapped_column(String(200))
    backdrop_path: Mapped[str | None] = mapped_column(String(200))
    popularity: Mapped[float | None] = mapped_column(Float)
    tmdb_rating: Mapped[float | None] = mapped_column(Float)
    tmdb_votes: Mapped[int | None] = mapped_column(Integer)
    imdb_id: Mapped[str | None] = mapped_column(String(16), index=True)
    imdb_rating: Mapped[float | None] = mapped_column(Float)
    rt_score: Mapped[int | None] = mapped_column(Integer)
    metacritic: Mapped[int | None] = mapped_column(Integer)
    scores_refreshed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    details_refreshed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Age ratings by country, e.g. {"US": "PG-13", "GB": "12A"}. Official
    # certifications only; nothing inferred.
    certifications: Mapped[dict] = mapped_column(JSONB, default=dict)
    # The franchise this belongs to, when the provider says so.
    collection_id: Mapped[int | None] = mapped_column(Integer, index=True)
    collection_name: Mapped[str | None] = mapped_column(String(300))
    raw_tmdb: Mapped[dict | None] = mapped_column(JSONB)

    availability: Mapped[list["Availability"]] = relationship(
        back_populates="title", cascade="all, delete-orphan"
    )
    episodes: Mapped[list["Episode"]] = relationship(
        back_populates="title", cascade="all, delete-orphan"
    )


class Episode(Base):
    """One episode of a series, cached from TMDB.

    Series were tracked whole until now, which cannot answer the two
    questions people actually have about a show: what did I already see, and
    what do I watch next. Films never grow a row here; only titles of type
    "tv" do.

    air_date is the hinge. It decides what counts as "out", it drives the
    new-episode alert, and it is nullable because TMDB frequently lists an
    announced episode before it has a date.
    """

    __tablename__ = "episodes"
    __table_args__ = (
        UniqueConstraint(
            "title_id",
            "season_number",
            "episode_number",
            name="uq_episodes_title_season_episode",
        ),
        Index("ix_episodes_title_air", "title_id", "air_date"),
        Index("ix_episodes_air_date", "air_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    title_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("titles.id", ondelete="CASCADE"), index=True
    )
    # TMDB's own episode id, when it gave one. Not the key: the season and
    # episode numbers are, because those are what every other source speaks.
    tmdb_id: Mapped[int | None] = mapped_column(Integer)
    # Season 0 is the specials season, and TMDB really does use it.
    season_number: Mapped[int] = mapped_column(Integer)
    episode_number: Mapped[int] = mapped_column(Integer)
    name: Mapped[str | None] = mapped_column(String(500))
    overview: Mapped[str | None] = mapped_column(String(4000))
    air_date: Mapped[date | None] = mapped_column(Date)
    runtime: Mapped[int | None] = mapped_column(Integer)
    still_path: Mapped[str | None] = mapped_column(String(200))
    refreshed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    title: Mapped[Title] = relationship(back_populates="episodes")


class Availability(Base):
    """Where a title streams in one country via one provider. first_seen_at
    versus last_seen_at is what the notification differ works from."""

    __tablename__ = "availability"
    __table_args__ = (
        UniqueConstraint(
            "title_id",
            "country",
            "provider_id",
            "kind",
            name="uq_availability_title_country_provider_kind",
        ),
        Index("ix_availability_title_country", "title_id", "country"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    title_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("titles.id", ondelete="CASCADE"))
    country: Mapped[str] = mapped_column(String(2))
    provider_id: Mapped[int] = mapped_column(Integer)
    provider_name: Mapped[str] = mapped_column(String(120))
    logo_path: Mapped[str | None] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(10))  # stream | rent | buy | ads | free
    link: Mapped[str | None] = mapped_column(String(600))
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    title: Mapped[Title] = relationship(back_populates="availability")


class ApiCache(Base):
    """Generic response cache for list-shaped TMDB calls (trending, discover,
    search). Key encodes endpoint and params; TTL is enforced in code."""

    __tablename__ = "api_cache"

    key: Mapped[str] = mapped_column(String(500), primary_key=True)
    source: Mapped[str] = mapped_column(String(20))
    payload: Mapped[dict] = mapped_column(JSONB)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
