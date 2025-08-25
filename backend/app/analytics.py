from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import require_user, AuthUser
from app.db.postgres import AnalyticsEvent, get_session, refresh_recommendations
from app.schemas.analytics import Event

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/health")
async def health():
    """Check analytics service health."""
    return {"status": "ok"}


@router.post("/events")
async def ingest_event(
    ev: Event,
    user: AuthUser = Depends(require_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Ingest a new analytics event for the current user.
    Example payload:
      {
        "user_id": "user-uuid",
        "type": "play",
        "payload": {"track_id": "track-123"}
      }
    """
    # security: enforce event.user_id matches JWT sub
    if ev.user_id != user.sub:
        raise HTTPException(status_code=403, detail="user_id mismatch")

    await session.execute(
        insert(AnalyticsEvent).values(
            user_id=ev.user_id,
            type=ev.type,
            payload=ev.payload,
        )
    )
    await session.commit()

    # simple: recalc recommendations synchronously
    await refresh_recommendations(session)

    return {"ok": True, "event_type": ev.type}
