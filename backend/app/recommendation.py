# app/recommendation.py (añade un endpoint por idioma)
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.postgres import get_session
from app.dependencies import require_user, AuthUser
from app.settings import settings
from app.spotify_client import ensure_access_token, me_top, recommendations
from pydantic import BaseModel

router = APIRouter(prefix="/reco", tags=["reco"])

# mapea idioma -> mercados Spotify (heurística inicial)
LANG_TO_MARKETS = {
    "es": ["ES","MX","AR","CO","CL","PE","US"],   # añade los que prefieras
    "en": ["US","GB","IE","CA","AU","NZ"],
    "pt": ["BR","PT"],
    "fr": ["FR","BE","CA"],
}

class RecoLangIn(BaseModel):
    lang: str = "es"
    limit: int = 30

def pick_market_for_lang(lang: str) -> str:
    return LANG_TO_MARKETS.get(lang, ["US"])[0]

@router.post("/by-language")
async def recommend_by_language(payload: RecoLangIn, user: AuthUser = Depends(require_user), session: AsyncSession = Depends(get_session)):
    access = await ensure_access_token(session, user.sub)

    # 1) Perfil del usuario: top tracks/artists
    top_tracks = await me_top(access, "tracks", limit=5)
    top_artists = await me_top(access, "artists", limit=5)

    seed_tracks = ",".join([t["id"] for t in top_tracks.get("items", [])[:3]])
    seed_artists = ",".join([a["id"] for a in top_artists.get("items", [])[:3]])

    if not seed_tracks and not seed_artists:
        raise HTTPException(400, "No hay suficientes datos de escucha en Spotify para generar recomendaciones")

    seeds = {}
    if seed_tracks: seeds["seed_tracks"] = seed_tracks
    if seed_artists: seeds["seed_artists"] = seed_artists

    # 2) Elegir 'market' según idioma
    market = pick_market_for_lang(payload.lang)

    # 3) Pedir recomendaciones a Spotify
    reco = await recommendations(access, seeds=seeds, limit=min(payload.limit, 100), market=market)

    # 4) (Opcional) post-filtrado por idioma usando heurística ISRC o cache track_language
    # Simplificado: nos quedamos con lo que devuelve el 'market' seleccionado.
    items = [{
        "id": t["id"],
        "name": t["name"],
        "artist": ", ".join([a["name"] for a in t["artists"]]),
        "uri": t["uri"],
        "preview_url": t.get("preview_url"),
        "external_urls": t.get("external_urls",{}).get("spotify")
    } for t in reco.get("tracks", [])]

    return {"lang": payload.lang, "market": market, "items": items}
