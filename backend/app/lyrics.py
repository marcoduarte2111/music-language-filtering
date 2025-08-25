from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
import httpx
import unicodedata

from app.dependencies import require_user, AuthUser
from app.settings import settings
from app.db.postgres import get_session  # kept for parity / future caching

router = APIRouter(prefix="/lyrics", tags=["lyrics"])


@router.get("/health")
async def health():
    return {"status": "ok"}


def _norm(s: str) -> str:
    """
    Normalize strings for safer comparisons:
    lowercase + strip accents + trim spaces.
    """
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.strip().lower()


async def _genius_search(q: str) -> dict:
    """
    Call Genius /search endpoint.
    Docs: https://docs.genius.com/#search-h2
    Returns JSON payload or raises HTTPException if token missing / request fails.
    """
    token = settings.GENIUS_API_TOKEN
    if not token:
        raise HTTPException(
            status_code=501,
            detail="GENIUS_API_TOKEN is not configured; lyrics search is disabled in this environment.",
        )
    url = "https://api.genius.com/search"
    headers = {"Authorization": f"Bearer {token}"}
    params = {"q": q}
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(url, headers=headers, params=params)
        if r.status_code == 401:
            raise HTTPException(502, "Genius API auth failed (check GENIUS_API_TOKEN).")
        r.raise_for_status()
        return r.json()


def _pick_best_hit(payload: dict, want_artist: str | None, want_title: str | None) -> dict | None:
    """
    Choose the most relevant hit from Genius search results.
    Preference order:
      1) Exact-ish artist AND title match
      2) Exact-ish artist match
      3) First result
    Returns a simplified dict with useful fields.
    """
    hits = (payload or {}).get("response", {}).get("hits", [])
    if not hits:
        return None

    want_artist_n = _norm(want_artist) if want_artist else None
    want_title_n = _norm(want_title) if want_title else None

    best = None
    for h in hits:
        res = h.get("result", {}) or {}
        primary_artist = (res.get("primary_artist", {}) or {}).get("name", "") or ""
        title = res.get("title", "") or ""
        url = res.get("url", "") or ""
        path = res.get("path", "") or ""
        full_title = res.get("full_title", "") or ""

        cand = {
            "song_id": res.get("id"),
            "title": title,
            "full_title": full_title,
            "primary_artist": primary_artist,
            "genius_url": url or (f"https://genius.com{path}" if path else None),
            "thumbnail": (res.get("song_art_image_thumbnail_url") or res.get("header_image_thumbnail_url")),
        }

        # Score candidate
        score = 0
        pa_n = _norm(primary_artist)
        ti_n = _norm(title)

        if want_artist_n and pa_n == want_artist_n:
            score += 5
        if want_title_n and (ti_n == want_title_n or want_title_n in ti_n or ti_n in want_title_n):
            score += 4

        # keep best by score, then fallback to first
        if best is None or score > best["__score"]:
            best = {**cand, "__score": score}

    # remove internal field
    if best:
        best.pop("__score", None)
    return best


@router.get("/")
async def get_lyrics_metadata(
    artist: str,
    title: str,
    _user: AuthUser = Depends(require_user),
    _session: AsyncSession = Depends(get_session),
):
    """
    Returns metadata + Genius URL for the requested song (artist + title).
    Note: Genius API doesn't return full lyrics; provide the URL for the client to open.
    """
    payload = await _genius_search(f"{artist} {title}")
    best = _pick_best_hit(payload, want_artist=artist, want_title=title)
    if not best:
        raise HTTPException(status_code=404, detail="Song not found on Genius.")
    return {
        "artist": best["primary_artist"],
        "title": best["title"],
        "full_title": best["full_title"],
        "genius_url": best["genius_url"],
        "thumbnail": best["thumbnail"],
        "source": "genius",
    }


@router.get("/search")
async def search_lyrics(
    q: str,
    _user: AuthUser = Depends(require_user),
    _session: AsyncSession = Depends(get_session),
):
    """
    Free-form search against Genius. Returns top matches with metadata and URLs.
    Useful for UI autocomplete or when artist/title aren't split.
    """
    payload = await _genius_search(q)
    hits = (payload or {}).get("response", {}).get("hits", [])
    results = []
    for h in hits[:10]:
        res = h.get("result", {}) or {}
        results.append({
            "song_id": res.get("id"),
            "title": res.get("title"),
            "full_title": res.get("full_title"),
            "primary_artist": (res.get("primary_artist", {}) or {}).get("name"),
            "genius_url": res.get("url") or (f"https://genius.com{res.get('path','')}" if res.get("path") else None),
            "thumbnail": res.get("song_art_image_thumbnail_url") or res.get("header_image_thumbnail_url"),
        })
    return {"count": len(results), "items": results}
