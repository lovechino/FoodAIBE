"""
handlers/chat_handler.py – ChatHandler class.
Trách nhiệm: orchestrate Router + Search + Simple + Gemini cho chat.
"""
import logging
from datetime import datetime
from typing import Optional

from fastapi import WebSocket, WebSocketDisconnect

from ..core.router import QueryRouter, RouteDecision
from ..core.search import SearchService
from ..core.simple import SimpleQueryHandler
from ..core.gemini import GeminiService
from ..models import ChatRequest, ChatResponse, FoodItem

logger = logging.getLogger(__name__)


class ChatHandler:
    """Điều phối chat: simple template → Gemini → WebSocket streaming."""

    def __init__(
        self,
        router: QueryRouter,
        search: SearchService,
        simple: SimpleQueryHandler,
        gemini: GeminiService,
    ) -> None:
        self._router = router
        self._search = search
        self._simple = simple
        self._gemini = gemini

    # ── REST ──────────────────────────────────────────────────────────────────

    async def handle_rest(self, req: ChatRequest) -> ChatResponse:
        """Xử lý POST /chat."""
        decision = self._router.route(req.message, has_location=bool(req.user_address))
        logger.info("[Chat] '%s' → %s (%s)", req.message[:40], decision.model, decision.query_type)

        if decision.model == "local":
            result = await self._try_simple(req.message, req.city)
            if result:
                return result
            decision = self._fallback_decision()

        reply, items = await self._call_gemini(req, decision)
        return ChatResponse(reply=reply, model_used=decision.model, query_type=decision.query_type, results=items)

    # ── WebSocket ─────────────────────────────────────────────────────────────

    async def handle_ws(self, websocket: WebSocket) -> None:
        """Xử lý WS /ws/chat – vòng lặp nhận-gửi."""
        await websocket.accept()
        try:
            while True:
                data = await websocket.receive_json()
                await self._handle_ws_message(data, websocket)
        except WebSocketDisconnect:
            logger.info("WebSocket disconnected")
        except Exception as e:
            logger.error("WebSocket error: %s", e)
            await self._safe_send_error(websocket, str(e))

    # ── Private helpers ────────────────────────────────────────────────────────

    async def _try_simple(self, message: str, city: str) -> Optional[ChatResponse]:
        hour   = datetime.now().hour
        search = lambda kw, lim=10: self._search.hybrid_search(city, kw, lim)
        text, items, handled = await self._simple.handle(message, search, hour)
        if not handled:
            return None
        return ChatResponse(reply=text, model_used="local", query_type="simple", results=items)

    async def _call_gemini(self, req: ChatRequest, decision: RouteDecision):
        items = await self._search.hybrid_search(req.city, req.message, top_k=10)
        reply = await self._gemini.chat(
            req.message, req.city, decision.model, decision.max_output_tokens,
            history=req.history, food_context=items, user_address=req.user_address,
        )
        return reply, items

    async def _handle_ws_message(self, data: dict, ws: WebSocket) -> None:
        message = data.get("message", "").strip()
        if not message:
            await ws.send_json({"error": "Empty message"})
            return
        city, history, addr = data.get("city", "ha_noi"), data.get("history", []), data.get("user_address")
        decision = self._router.route(message, has_location=bool(addr))

        if decision.model == "local":
            handled = await self._ws_try_simple(message, city, ws)
            if handled:
                return
            decision = self._fallback_decision()

        await self._ws_stream_gemini(message, city, decision, history, addr, ws)

    async def _ws_try_simple(self, message: str, city: str, ws: WebSocket) -> bool:
        hour   = datetime.now().hour
        search = lambda kw, lim=10: self._search.hybrid_search(city, kw, lim)
        text, items, handled = await self._simple.handle(message, search, hour)
        if not handled:
            return False
        await ws.send_text(text)
        await ws.send_json({"done": True, "model": "local", "type": "simple",
                            "results": [i.model_dump() for i in items]})
        return True

    async def _ws_stream_gemini(self, message, city, decision, history, addr, ws):
        items = await self._search.hybrid_search(city, message, top_k=10)
        async for chunk in self._gemini.stream(
            message, city, decision.model, decision.max_output_tokens,
            history=history, food_context=items, user_address=addr,
        ):
            await ws.send_text(chunk)
        await ws.send_json({"done": True, "model": decision.model, "type": decision.query_type,
                            "results": [i.model_dump() for i in items]})

    @staticmethod
    def _fallback_decision() -> RouteDecision:
        from ..core.router import RouteDecision
        return RouteDecision("gemini-flash", 600, "complex", "Fallback từ simple")

    @staticmethod
    async def _safe_send_error(ws: WebSocket, msg: str) -> None:
        try:
            await ws.send_json({"error": msg})
        except Exception:
            pass
