from pydantic import BaseModel
from typing import Any, Dict

class Event(BaseModel):
    """
    Analytics event schema.

    Example:
    {
        "user_id": "uuid-of-user",
        "type": "play",
        "payload": {"track_id": "123", "duration": 180}
    }
    """
    user_id: str
    type: str
    payload: Dict[str, Any]

    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "c1a3a0da-8d3b-4c6f-9a1a-4a6be1d8bcd1",
                "type": "play",
                "payload": {"track_id": "spotify:track:6rqhFgbbKwnb9MLmUQDhG6"},
            }
        }
