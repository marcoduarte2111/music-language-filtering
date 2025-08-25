from pydantic import BaseModel, EmailStr

class RegisterIn(BaseModel):
    email: EmailStr
    password: str
    display_name: str | None = None

class LoginIn(BaseModel):
    email: EmailStr
    password: str
