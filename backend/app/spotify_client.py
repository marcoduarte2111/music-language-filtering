# app/spotify_client.py
import time, base64
from typing import Dict, Any, List
import httpx
from sqlalchemy import select, update, insert
from sqlalchemy.ext.asyncio import AsyncSession
from app.settings import settings
from app.db.postgres import get_session, AppUser
from app.db.postgres import engine
from app.db.postgres import Base
from app.db.postgres import SessionLocal
from app.db.postgres import MLModel
from app.db.postgres import AnalyticsEvent
from sqlalchemy import text as sql

SPOTIFY_AUTH_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_API_BASE = "https://api.spotify.com/v1"

def _basic_auth_header() -> dict:
    key = f"{settings.SPOTIFY_CLIENT_ID}:{settings.SPOTIFY_CLIENT_SECRET}".encode()
    return {"Authorization": "Basic " + base64.b64encode(key).decode()}

async def get_spotify_tokens(session: AsyncSession, user_id: str):
    res = await session.execute(sql("SELECT * FROM spotify_account WHERE user_id = :uid"), {"uid": user_id})
    row = res.mappings().first()
    return row

async def save_spotify_tokens(session: AsyncSession, user_id: str, spotify_user_id: str,
                              access_token: str, refresh_token: str, expires_in: int,
                              scope: str = "", token_type: str = "Bearer"):
    expires_at = int(time.time()) + int(expires_in) - 30  # 30s margen
    q = sql("""
        INSERT INTO spotify_account (user_id, spotify_user_id, access_token, refresh_token, scope, token_type, expires_at)
        VALUES (:user_id, :spotify_user_id, :access_token, :refresh_token, :scope, :token_type, to_timestamp(:expires_at))
        ON CONFLICT (user_id) DO UPDATE SET
          access_token = EXCLUDED.access_token,
          refresh_token = EXCLUDED.refresh_token,
          scope = EXCLUDED.scope,
          token_type = EXCLUDED.token_type,
          expires_at = EXCLUDED.expires_at
    """)
    await session.execute(q, {
        "user_id": user_id,
        "spotify_user_id": spotify_user_id,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "scope": scope,
        "token_type": token_type,
        "expires_at": expires_at
    })
    await session.commit()

async def ensure_access_token(session: AsyncSession, user_id: str) -> str:
    row = await get_spotify_tokens(session, user_id)
    if not row:
        raise ValueError("Usuario no conectado a Spotify")
    access_token = row["access_token"]
    expires_at = int(row["expires_at"].timestamp())
    if time.time() < expires_at:
        return access_token
    # refresh
    async with httpx.AsyncClient() as client:
        data = {
            "grant_type": "refresh_token",
            "refresh_token": row["refresh_token"]
        }
        headers = _basic_auth_header()
        r = await client.post(SPOTIFY_AUTH_URL, data=data, headers=headers, timeout=20)
        r.raise_for_status()
        payload = r.json()
        new_access = payload["access_token"]
        new_expires_in = payload.get("expires_in", 3600)
        scope = payload.get("scope", row["scope"])
        token_type = payload.get("token_type", "Bearer")
        await save_spotify_tokens(session, user_id, row["spotify_user_id"], new_access, row["refresh_token"], new_expires_in, scope, token_type)
        return new_access

async def api_get(access_token: str, path: str, params: dict | None = None):
    url = f"{SPOTIFY_API_BASE}{path}"
    headers = {"Authorization": f"Bearer {access_token}"}
    async with httpx.AsyncClient() as client:
        r = await client.get(url, headers=headers, params=params, timeout=20)
        r.raise_for_status()
        return r.json()

async def me_top(access_token: str, type_: str = "tracks", limit: int = 20, time_range: str = "medium_term"):
    return await api_get(access_token, f"/me/top/{type_}", {"limit": limit, "time_range": time_range})

async def recommendations(access_token: str, seeds: dict, limit: int = 50, market: str | None = None, tunables: dict | None = None):
    params = {"limit": limit, **seeds}
    if market: params["market"] = market
    if tunables: params.update(tunables)
    return await api_get(access_token, "/recommendations", params)
