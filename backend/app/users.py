import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres import AppUser, get_session
from app.schemas.user import UserCreate, UserOut
from app.dependencies import require_user, require_role, AuthUser

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/health")
async def health():
    """Verifica que el módulo de usuarios esté vivo."""
    return {"status": "ok"}


@router.get("/me", response_model=UserOut)
async def get_me(
    current: AuthUser = Depends(require_user),
    session: AsyncSession = Depends(get_session)
):
    """
    Devuelve el perfil del usuario actual (autenticado).
    """
    res = await session.execute(select(AppUser).where(AppUser.id == current.sub))
    user = res.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return UserOut(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        preferences=user.preferences,
        role=user.role,
        preferred_lang=user.preferred_lang
    )


@router.get("/", response_model=list[UserOut])
async def list_users(
    _: AuthUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session)
):
    """
    Lista todos los usuarios de la aplicación.
    Solo accesible para administradores.
    """
    res = await session.execute(select(AppUser).limit(100))
    rows = res.scalars().all()
    return [
        UserOut(
            id=r.id,
            email=r.email,
            display_name=r.display_name,
            preferences=r.preferences,
            role=r.role,
            preferred_lang=r.preferred_lang
        )
        for r in rows
    ]


@router.post("/", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreate,
    session: AsyncSession = Depends(get_session)
):
    """
    Crear un usuario nuevo en la base de datos.
    ⚠️ Normalmente lo harás desde /auth/register,
    pero este endpoint sirve para pruebas.
    """
    new_id = str(uuid.uuid4())
    try:
        await session.execute(insert(AppUser).values(
            id=new_id,
            email=payload.email,
            password_hash=payload.password,  # ya debe venir hasheada en /auth/register
            display_name=payload.display_name,
            role="user",
            preferences=payload.preferences
        ))
        await session.commit()
        return UserOut(
            id=new_id,
            email=payload.email,
            display_name=payload.display_name,
            preferences=payload.preferences,
            role="user",
            preferred_lang="es"
        )
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail="El email ya existe")


@router.patch("/me/lang")
async def update_lang(
    lang: str,
    current: AuthUser = Depends(require_user),
    session: AsyncSession = Depends(get_session)
):
    """
    Permite al usuario actualizar su idioma preferido.
    """
    q = select(AppUser).where(AppUser.id == current.sub)
    res = await session.execute(q)
    user = res.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "Usuario no encontrado")
    user.preferred_lang = lang
    await session.commit()
    return {"ok": True, "preferred_lang": lang}
