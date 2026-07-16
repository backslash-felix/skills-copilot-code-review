"""Announcements endpoints for the High School Management System API."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..database import announcements_collection, teachers_collection

router = APIRouter(
    prefix="/announcements",
    tags=["announcements"]
)


class AnnouncementInput(BaseModel):
    """Payload for creating and updating announcements."""

    message: str = Field(min_length=1, max_length=500)
    expires_at: datetime
    starts_at: Optional[datetime] = None


def _normalize_datetime(value: datetime) -> datetime:
    """Normalize datetimes to UTC so filtering works consistently."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _require_signed_in_user(teacher_username: Optional[str]) -> Dict[str, Any]:
    if not teacher_username:
        raise HTTPException(status_code=401, detail="Authentication required")

    teacher = teachers_collection.find_one({"_id": teacher_username})
    if not teacher:
        raise HTTPException(status_code=401, detail="Invalid teacher credentials")

    return teacher


def _serialize_announcement(document: Dict[str, Any]) -> Dict[str, Any]:
    starts_at = document.get("starts_at")
    expires_at = document.get("expires_at")

    return {
        "id": str(document["_id"]),
        "message": document.get("message", ""),
        "starts_at": starts_at.isoformat() if starts_at else None,
        "expires_at": expires_at.isoformat() if expires_at else None,
        "created_by": document.get("created_by", "")
    }


@router.get("", response_model=List[Dict[str, Any]])
def get_active_announcements() -> List[Dict[str, Any]]:
    """Return currently active announcements for public display."""
    now = datetime.now(timezone.utc)

    query = {
        "$and": [
            {"expires_at": {"$gt": now}},
            {
                "$or": [
                    {"starts_at": {"$exists": False}},
                    {"starts_at": None},
                    {"starts_at": {"$lte": now}}
                ]
            }
        ]
    }

    announcements: List[Dict[str, Any]] = []
    for document in announcements_collection.find(query).sort("expires_at", 1):
        announcements.append(_serialize_announcement(document))

    return announcements


@router.get("/manage", response_model=List[Dict[str, Any]])
def get_all_announcements(teacher_username: Optional[str] = Query(None)) -> List[Dict[str, Any]]:
    """Return all announcements for authenticated users managing content."""
    _require_signed_in_user(teacher_username)

    announcements: List[Dict[str, Any]] = []
    for document in announcements_collection.find({}).sort("expires_at", 1):
        announcements.append(_serialize_announcement(document))

    return announcements


@router.post("", response_model=Dict[str, Any])
def create_announcement(
    payload: AnnouncementInput,
    teacher_username: Optional[str] = Query(None)
) -> Dict[str, Any]:
    """Create a new announcement. Requires signed-in teacher."""
    teacher = _require_signed_in_user(teacher_username)

    expires_at = _normalize_datetime(payload.expires_at)
    starts_at = _normalize_datetime(payload.starts_at) if payload.starts_at else None

    if starts_at and starts_at >= expires_at:
        raise HTTPException(status_code=400, detail="Start date must be before expiration date")

    result = announcements_collection.insert_one(
        {
            "_id": str(uuid4()),
            "message": payload.message.strip(),
            "starts_at": starts_at,
            "expires_at": expires_at,
            "created_by": teacher["username"]
        }
    )

    created = announcements_collection.find_one({"_id": result.inserted_id})
    return _serialize_announcement(created)


@router.put("/{announcement_id}", response_model=Dict[str, Any])
def update_announcement(
    announcement_id: str,
    payload: AnnouncementInput,
    teacher_username: Optional[str] = Query(None)
) -> Dict[str, Any]:
    """Update an existing announcement. Requires signed-in teacher."""
    _require_signed_in_user(teacher_username)

    expires_at = _normalize_datetime(payload.expires_at)
    starts_at = _normalize_datetime(payload.starts_at) if payload.starts_at else None

    if starts_at and starts_at >= expires_at:
        raise HTTPException(status_code=400, detail="Start date must be before expiration date")

    result = announcements_collection.update_one(
        {"_id": announcement_id},
        {
            "$set": {
                "message": payload.message.strip(),
                "starts_at": starts_at,
                "expires_at": expires_at
            }
        }
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    updated = announcements_collection.find_one({"_id": announcement_id})
    return _serialize_announcement(updated)


@router.delete("/{announcement_id}")
def delete_announcement(
    announcement_id: str,
    teacher_username: Optional[str] = Query(None)
) -> Dict[str, str]:
    """Delete an announcement. Requires signed-in teacher."""
    _require_signed_in_user(teacher_username)

    result = announcements_collection.delete_one({"_id": announcement_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    return {"message": "Announcement deleted"}
