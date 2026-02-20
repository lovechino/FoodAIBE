"""routes/ai.py – POST /nearby, GET /suggest"""
from typing import Optional
from datetime import datetime
from fastapi import APIRouter, Query, HTTPException
from ..deps import get_suggest_handler, get_nearby_handler
from ..models import SuggestResponse, NearbyRequest, NearbyResponse

router = APIRouter(tags=["AI"])


@router.get("/suggest", response_model=SuggestResponse)
async def suggest(
    city: str = Query(default="ha_noi"),
    hour: Optional[int] = Query(default=None, description="Giờ (0-23). Mặc định: giờ server"),
):
    try:
        h = hour if hour is not None else datetime.now().hour
        return await get_suggest_handler().handle(city, h)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/nearby", response_model=NearbyResponse)
async def nearby(req: NearbyRequest):
    try:
        return await get_nearby_handler().handle(req)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
