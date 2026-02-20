"""routes/system.py – /health, /cities"""
from datetime import datetime
from fastapi import APIRouter
from ..deps import get_search

router = APIRouter(tags=["System"])


@router.get("/health")
async def health():
    return {"status": "ok", "time": datetime.now().isoformat(), "cities": get_search().get_all_cities()}


@router.get("/cities")
async def cities():
    return {"cities": get_search().get_all_cities()}
