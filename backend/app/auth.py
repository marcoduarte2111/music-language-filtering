import uuid
import httpx
import urllib.parse
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy import select, insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres import AppUser, get_session
from app.dependencies import (
    hash_password,
    verify_password,
    create_jwt,
    require_user,
    AuthUser,
)
from app.schemas.auth import RegisterIn, LoginIn
from app.settings import settings
from app.spotify_client import save_spotify_tokens, api_get

router = APIRouter(prefix="/auth", tags=["auth"])

# ---------- Registro & Login (usuarios de tu app) ----------

@router.post("/register", status_code=201)
async def register(payload: RegisterIn, session: AsyncSession = Depends(get_session)):
    """Registrar un nuevo usuario local."""
    uid = str(uuid.uuid4())
    try:
        await session.execute(
            insert(AppUser).values(
                id=uid,
                email=payload.email,
                password_hash=hash_password(payload.password),
                display_name=payload.display_name,
                role="user",
                preferences={},
            )
        )
        await session.commit()
        return {"id": uid, "email": payload.email}
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail="El email ya existe")


@router.post("/login")
async def login(payload: LoginIn, session: AsyncSession = Depends(get_session)):
    """Login con email y password → devuelve JWT."""
    q = select(AppUser).where(AppUser.email == payload.email)
    res = await session.execute(q)
    user = res.scalar_one_or_none()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Credenciales inválidas")
    token = create_jwt(sub=user.id, role=user.role)
    return {"token": token}


# ---------- Integración con Spotify (OAuth) ----------

SPOTIFY_AUTHORIZE = "https://accounts.spotify.com/authorize"
SPOTIFY_TOKEN = "https://accounts.spotify.com/api/token"
SPOTIFY_SCOPES = "user-top-read"
REDIRECT_URI = "http://localhost:8000/auth/spotify/callback"

@router.get("/spotify/login")
async def spotify_login(_=Depends(require_user)):
    """Redirige a Spotify para que el usuario autorice la app."""
    params = {
        "client_id": settings.SPOTIFY_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": SPOTIFY_SCOPES,
    }
    return RedirectResponse(url=f"{SPOTIFY_AUTHORIZE}?{urllib.parse.urlencode(params)}")


@router.get("/spotify/callback")
async def spotify_callback(
    code: str,
    user: AuthUser = Depends(require_user),
    session: AsyncSession = Depends(get_session),
):
    """Recibe el code de Spotify y guarda tokens en la DB."""
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "client_id": settings.SPOTIFY_CLIENT_ID,
        "client_secret": settings.SPOTIFY_CLIENT_SECRET,
    }
    async with httpx.AsyncClient() as client:
        r = await client.post(SPOTIFY_TOKEN, data=data, timeout=20)
        r.raise_for_status()
        token_payload = r.json()

    access_token = token_payload["access_token"]
    refresh_token = token_payload["refresh_token"]
    expires_in = token_payload.get("expires_in", 3600)

    me = await api_get(access_token, "/me")
    spotify_user_id = me["id"]

    await save_spotify_tokens(
        session,
        user.sub,
        spotify_user_id,
        access_token,
        refresh_token,
        expires_in,
        token_payload.get("scope", ""),
        token_payload.get("token_type", "Bearer"),
    )

    return {"ok": True, "spotify_user_id": spotify_user_id}
