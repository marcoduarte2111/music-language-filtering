from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import require_user, AuthUser
from app.db.postgres import get_session
from app.spotify_client import ensure_access_token, me_top, api_get

router = APIRouter(prefix="/music", tags=["music"])


@router.get("/health")
async def health():
    """Comprobar estado del módulo de música."""
    return {"status": "ok"}


@router.get("/me/top/tracks")
async def my_top_tracks(
    limit: int = 10,
    time_range: str = "medium_term",
    user: AuthUser = Depends(require_user),
    session: AsyncSession = Depends(get_session)
):
    """
    Devuelve las canciones más escuchadas del usuario en Spotify.
    - limit: número de tracks (máx. 50)
    - time_range: short_term (4 semanas), medium_term (6 meses), long_term (años)
    """
    access = await ensure_access_token(session, user.sub)
    data = await me_top(access, type_="tracks", limit=limit, time_range=time_range)
    return data


@router.get("/me/top/artists")
async def my_top_artists(
    limit: int = 10,
    time_range: str = "medium_term",
    user: AuthUser = Depends(require_user),
    session: AsyncSession = Depends(get_session)
):
    """
    Devuelve los artistas más escuchados del usuario en Spotify.
    """
    access = await ensure_access_token(session, user.sub)
    data = await me_top(access, type_="artists", limit=limit, time_range=time_range)
    return data


@router.get("/search")
async def search_tracks(
    q: str,
    limit: int = 10,
    user: AuthUser = Depends(require_user),
    session: AsyncSession = Depends(get_session)
):
    """
    Buscar canciones en Spotify por texto.
    """
    access = await ensure_access_token(session, user.sub)
    result = await api_get(access, "/search", {"q": q, "type": "track", "limit": limit})
    return result


@router.get("/track/{track_id}")
async def get_track(
    track_id: str,
    user: AuthUser = Depends(require_user),
    session: AsyncSession = Depends(get_session)
):
    """
    Obtener información detallada de un track en Spotify.
    """
    access = await ensure_access_token(session, user.sub)
    result = await api_get(access, f"/tracks/{track_id}")
    if not result:
        raise HTTPException(status_code=404, detail="Track not found")
    return result
