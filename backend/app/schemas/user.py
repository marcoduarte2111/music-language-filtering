from typing import Any, Optional
from pydantic import BaseModel, EmailStr, Field

# What the client sends when creating/updating user data
class UserCreate(BaseModel):
    email: EmailStr
    display_name: Optional[str] = None
    # Only used by /auth/register. /users POST can ignore it or require admin.
    password: Optional[str] = None
    preferences: dict[str, Any] = Field(default_factory=dict)

# What the API returns to clients
class UserOut(BaseModel):
    id: str
    email: EmailStr
    display_name: Optional[str] = None
    preferences: dict[str, Any] = Field(default_factory=dict)
    role: str = "user"            # 'user' | 'admin'
    preferred_lang: str = "es"    # e.g., 'es', 'en', 'pt'
