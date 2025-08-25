import jwt
from datetime import datetime, timedelta
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from passlib.context import CryptContext
from typing import Annotated, List

from app.settings import settings

# Password hashing context (bcrypt)
pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(raw: str) -> str:
    """Hash a plain password using bcrypt."""
    return pwd_ctx.hash(raw)

def verify_password(raw: str, hashed: str) -> bool:
    """Verify a plain password against a hash."""
    return pwd_ctx.verify(raw, hashed)


# ---------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------

class AuthUser:
    """
    Lightweight object representing an authenticated user.
    """
    def __init__(self, sub: str, role: str = "user", scope: List[str] | None = None):
        self.sub = sub
        self.role = role
        self.scope = scope or ["user"]

def create_jwt(sub: str, role: str = "user", scope: List[str] | None = None) -> str:
    """
    Create a JWT for the given user id (sub), role and scopes.
    """
    payload = {
        "sub": sub,
        "role": role,
        "scope": scope or ["user"],
        "exp": datetime.utcnow() + timedelta(minutes=settings.JWT_EXPIRE_MIN),
        "iat": datetime.utcnow(),
        "iss": settings.APP_NAME,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALG)


# ---------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------

security = HTTPBearer(auto_error=True)

async def require_user(
    creds: Annotated[HTTPAuthorizationCredentials, Depends(security)]
) -> AuthUser:
    """
    Validate the Bearer token from Authorization header.
    Returns an AuthUser if valid, raises HTTP 401 otherwise.
    """
    token = creds.credentials
    try:
        data = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALG])
        return AuthUser(
            sub=data.get("sub"),
            role=data.get("role", "user"),
            scope=data.get("scope", []),
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired"
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        )

def require_role(*roles: str):
    """
    Dependency factory: ensures current user has one of the allowed roles.
    Usage:
        @router.get("/admin")
        async def only_admin(u: AuthUser = Depends(require_role("admin"))):
            return {"msg": "ok"}
    """
    async def _inner(user: AuthUser = Depends(require_user)):
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden"
            )
        return user
    return _inner
