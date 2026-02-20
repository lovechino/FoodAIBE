"""routes/chat.py – POST /chat, WS /ws/chat"""
from fastapi import APIRouter, WebSocket, HTTPException
from ..deps import get_chat_handler
from ..models import ChatRequest, ChatResponse

router = APIRouter(tags=["AI"])


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    try:
        return await get_chat_handler().handle_rest(req)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket):
    await get_chat_handler().handle_ws(websocket)
