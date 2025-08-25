# app/db/postgres.py
from __future__ import annotations
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import (
    Text, JSON, Integer, String, Enum, Index, ForeignKey, text as sql
)
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.settings import settings

# ---- Engine & session factory -------------------------------------------------

engine = create_async_engine(settings.PG_URL, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

#@asynccontextmanager
#async def get_session() -> AsyncIterator[AsyncSession]:
#    async with SessionLocal() as session:
#        yield session
async def get_session() -> AsyncSession:
    async with SessionLocal() as session:
        try:
            yield session
        finally:
            # session is closed by context manager
            pass
# ---- Base model ---------------------------------------------------------------

class Base(DeclarativeBase):
    pass

# ---- Models ------------------------------------------------------------------

# Roles as plain TEXT; we’ll enforce acceptable values at app layer ("user" | "admin")
class AppUser(Base):
    __tablename__ = "app_user"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(16), default="user", nullable=False)
    preferred_lang: Mapped[str] = mapped_column(String(8), default="es", nullable=False)
    created_at: Mapped[Optional[str]] = mapped_column(
        # store as timestamptz at DB level; no server_default here (handled by DDL bootstrap)
        nullable=True
    )

    spotify_account: Mapped["SpotifyAccount"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )

class SpotifyAccount(Base):
    __tablename__ = "spotify_account"

    user_id: Mapped[str] = mapped_column(
        Text, ForeignKey("app_user.id", ondelete="CASCADE"), primary_key=True
    )
    spotify_user_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[Optional[str]] = mapped_column(Text)
    token_type: Mapped[Optional[str]] = mapped_column(Text)
    # stored as timestamptz in DB; we can map to text and let queries handle conversion
    expires_at: Mapped[Optional[str]] = mapped_column(nullable=True)

    user: Mapped[AppUser] = relationship(back_populates="spotify_account")

class AnalyticsEvent(Base):
    __tablename__ = "analytics_event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        Text, ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    # created_at set via DB default in bootstrap

    __table_args__ = (
        Index("ix_event_user_type", "user_id", "type"),
    )

class MLModel(Base):
    __tablename__ = "ml_models"

    user_id: Mapped[str] = mapped_column(
        Text, ForeignKey("app_user.id", ondelete="CASCADE"), primary_key=True
    )
    # list[str] of track ids
    recommendations: Mapped[list] = mapped_column(JSON, default=list)

class TrackLanguage(Base):
    __tablename__ = "track_language"

    track_id: Mapped[str] = mapped_column(Text, primary_key=True)
    lang: Mapped[Optional[str]] = mapped_column(String(8))
    # detected_at set via DB default in bootstrap


# ---- Schema bootstrap (DDL) ---------------------------------------------------

SCHEMA_SQL = sql("""
-- types (optional historical enum shown here as comment)
-- CREATE TYPE user_role AS ENUM ('user', 'admin');

-- users
CREATE TABLE IF NOT EXISTS app_user (
  id TEXT PRIMARY KEY,
  email TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  display_name TEXT,
  role VARCHAR(16) NOT NULL DEFAULT 'user',
  preferred_lang TEXT NOT NULL DEFAULT 'es',
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- spotify account
CREATE TABLE IF NOT EXISTS spotify_account (
  user_id TEXT PRIMARY KEY REFERENCES app_user(id) ON DELETE CASCADE,
  spotify_user_id TEXT UNIQUE NOT NULL,
  access_token TEXT NOT NULL,
  refresh_token TEXT NOT NULL,
  scope TEXT,
  token_type TEXT,
  expires_at TIMESTAMPTZ NOT NULL
);

-- analytics events
CREATE TABLE IF NOT EXISTS analytics_event (
  id SERIAL PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
  type VARCHAR(64) NOT NULL,
  payload JSONB NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_event_user_type ON analytics_event (user_id, type);

-- recommendation cache
CREATE TABLE IF NOT EXISTS ml_models (
  user_id TEXT PRIMARY KEY REFERENCES app_user(id) ON DELETE CASCADE,
  recommendations JSONB DEFAULT '[]'::jsonb
);

-- optional track language cache
CREATE TABLE IF NOT EXISTS track_language (
  track_id TEXT PRIMARY KEY,
  lang TEXT,
  detected_at TIMESTAMPTZ DEFAULT NOW()
);
""")

async def bootstrap_schema() -> None:
    """
    Ensures tables exist. Uses explicit DDL so timestamps/defaults are set as desired.
    """
    async with engine.begin() as conn:
        # Create ORM tables (no server defaults here)
        await conn.run_sync(Base.metadata.create_all)
        # Apply DDL for defaults/indexes we want guaranteed
        await conn.execute(SCHEMA_SQL)

# ---- Recommendation refresh (pure SQL) ---------------------------------------

# Aggregates top played track_ids per user based on analytics_event and writes top-10 into ml_models.
REFRESH_SQL = sql("""
INSERT INTO ml_models (user_id, recommendations)
SELECT user_id,
       COALESCE(
         (
           SELECT json_agg(track_id) FROM (
             SELECT (payload->>'track_id') AS track_id,
                    COUNT(*) AS cnt
             FROM analytics_event ae2
             WHERE ae2.user_id = ae.user_id
               AND (payload ? 'track_id')
             GROUP BY 1
             ORDER BY cnt DESC, track_id ASC
             LIMIT 10
           ) t
         ), '[]'::json
       ) AS reco
FROM (SELECT DISTINCT user_id FROM analytics_event) ae
ON CONFLICT (user_id) DO UPDATE
SET recommendations = EXCLUDED.recommendations;
""")

async def refresh_recommendations(session: AsyncSession) -> None:
    await session.execute(REFRESH_SQL)
    await session.commit()
