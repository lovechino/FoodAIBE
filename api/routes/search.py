"""routes/search.py – GET /search, POST /food/click"""
from fastapi import APIRouter, Query, HTTPException
from ..deps import get_search_handler, get_search
from ..models import SearchResponse, ClickRequest, ClickResponse

router = APIRouter(tags=["Search"])


@router.get("/search", response_model=SearchResponse)
async def search(
    q:     str = Query(..., min_length=1),
    city:  str = Query(default="ha_noi"),
    limit: int = Query(default=10, ge=1, le=50),
    mode:  str = Query(default="hybrid", description="hybrid | text | semantic"),
):
    try:
        return await get_search_handler().handle(q, city, limit, mode)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/food/click", response_model=ClickResponse, tags=["Search"])
async def record_click(req: ClickRequest):
    """Ghi nhận lượt click vào quán – tăng so_lan_click +1."""
    try:
        new_count = await get_search().increment_click(req.city, req.id)
        return ClickResponse(id=req.id, city=req.city, so_lan_click=new_count)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
