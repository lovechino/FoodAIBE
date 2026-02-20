"""
core/gemini.py – GeminiService class.
Trách nhiệm: giao tiếp với Google Gemini API (REST + streaming).
"""
import logging
import threading
from queue import Queue, Empty
from typing import AsyncIterator, Optional
from datetime import datetime

import google.generativeai as genai
from google.generativeai.types import GenerationConfig

from .router import ModelTier
from .prompt import PromptBuilder
from ..models import FoodItem

logger = logging.getLogger(__name__)

_MODEL_MAP: dict[ModelTier, str] = {
    "gemini-flash": "gemini-2.0-flash",
    "gemini-pro":   "gemini-2.0-flash",
}
_MAX_TOKENS: dict[ModelTier, int] = {
    "gemini-flash": 800,
    "gemini-pro":   1500,
}


class GeminiService:
    """Wrapper Gemini API – REST và streaming (WebSocket)."""

    def __init__(self, api_key: str, prompt_builder: PromptBuilder) -> None:
        genai.configure(api_key=api_key)
        self._pb = prompt_builder

    # ── Public API ─────────────────────────────────────────────────────────────

    async def chat(
        self,
        message: str,
        city: str,
        tier: ModelTier,
        max_tokens: int,
        history: list[dict] | None = None,
        food_context: list[FoodItem] | None = None,
        user_address: Optional[str] = None,
    ) -> str:
        """Gọi Gemini REST, trả về full text."""
        import asyncio
        system, gemini_hist, cfg = self._build_params(
            tier, city, max_tokens, history, food_context, user_address
        )
        def _call():
            model = self._build_model(tier, system, cfg)
            return model.start_chat(history=gemini_hist).send_message(message).text
        try:
            return await asyncio.get_event_loop().run_in_executor(None, _call)
        except Exception as e:
            logger.error(f"Gemini.chat error: {e}")
            return f"Xin lỗi, AI đang gặp sự cố. ({type(e).__name__})"

    async def stream(
        self,
        message: str,
        city: str,
        tier: ModelTier,
        max_tokens: int,
        history: list[dict] | None = None,
        food_context: list[FoodItem] | None = None,
        user_address: Optional[str] = None,
    ) -> AsyncIterator[str]:
        """Streaming Gemini – dùng threading.Thread + Queue cho WebSocket."""
        import asyncio
        system, gemini_hist, cfg = self._build_params(
            tier, city, max_tokens, history, food_context, user_address
        )
        queue: Queue = Queue()
        DONE = object()

        def _worker():
            try:
                model = self._build_model(tier, system, cfg)
                chat  = model.start_chat(history=gemini_hist)
                for chunk in chat.send_message(message, stream=True):
                    if chunk.text:
                        queue.put(chunk.text)
            except Exception as e:
                logger.error(f"Gemini.stream error: {e}")
                queue.put(f"\n[Lỗi: {type(e).__name__}]")
            finally:
                queue.put(DONE)

        threading.Thread(target=_worker, daemon=True).start()
        while True:
            try:
                item = queue.get_nowait()
                if item is DONE:
                    break
                yield item
            except Empty:
                await asyncio.sleep(0.05)

    async def rank_nearby(
        self,
        items: list[FoodItem],
        user_address: str,
        city: str,
        food_type: str,
    ) -> str:
        """Dùng Gemini xếp hạng quán gần user dựa trên địa chỉ text."""
        if not items:
            return f"Không tìm thấy quán **{food_type}** nào trong dữ liệu."
        prompt = self._build_nearby_prompt(items, user_address, city, food_type)
        return await self.chat(prompt, city, "gemini-flash", 800)

    # ── Private helpers ────────────────────────────────────────────────────────

    def _build_params(self, tier, city, max_tokens, history, food_ctx, user_address):
        hour    = datetime.now().hour
        meal    = PromptBuilder().trim_history.__doc__ and ""  # unused
        from .router import QueryRouter
        meal    = QueryRouter.get_meal_time(hour)
        system  = self._pb.build_system(tier, city, hour, meal, user_address)
        if food_ctx:
            system += "\n\n" + self._pb.build_food_context(food_ctx)
        hist    = self._pb.build_history(history or [])
        tokens  = min(max_tokens, _MAX_TOKENS[tier])
        cfg     = GenerationConfig(max_output_tokens=tokens)
        return system, hist, cfg

    def _build_model(self, tier: ModelTier, system: str, cfg: GenerationConfig):
        return genai.GenerativeModel(
            model_name=_MODEL_MAP[tier],
            system_instruction=system,
            generation_config=cfg,
        )

    def _build_nearby_prompt(self, items, address, city, food_type) -> str:
        ctx = self._pb.build_food_context(items[:15])
        return (
            f"User ở: **{address}**, thành phố {city}.\n"
            f"Tìm **{food_type}** gần nhất.\n\n{ctx}\n\n"
            "Xếp hạng TOP 5 quán gần user nhất theo địa chỉ. "
            "Ưu tiên quán cùng quận/đường. Kèm lý do ngắn."
        )
