from fastapi import FastAPI
from app import auth, users, music, lyrics, recommendation, analytics
from app.settings import settings
from app.db.postgres import bootstrap_schema

app = FastAPI(title=settings.APP_NAME)

#@app.on_event("startup")
#async def _startup():
#    await bootstrap_schema()

# 👉 asegúrate de incluir los routers
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(music.router)
app.include_router(lyrics.router)
app.include_router(recommendation.router)
app.include_router(analytics.router)

@app.get("/health")
def root_health():
    return {"status": "ok"}
