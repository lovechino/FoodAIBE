"""
gemini_service.py – Tích hợp Google Gemini API.
Hỗ trợ cả REST (JSON) và streaming (cho WebSocket).
"""
import os
import logging
from typing import AsyncIterator
from datetime import datetime

import google.generativeai as genai
from google.generativeai.types import GenerationConfig

from .router_model import ModelTier, build_system_prompt, get_meal_time
from .models import FoodItem

logger = logging.getLogger(__name__)

# ── Setup ─────────────────────────────────────────────────────────────────────

GEMINI_KEY = os.getenv("GEMINI_API_KEY", "")
genai.configure(api_key=GEMINI_KEY)

_MODEL_MAP: dict[ModelTier, str] = {
    "gemini-flash": "gemini-2.0-flash",
    "gemini-pro":   "gemini-2.0-flash",   # dùng flash-thinking cho heavy
}

_TOKEN_LIMITS: dict[ModelTier, int] = {
    "gemini-flash": 800,
    "gemini-pro":   1500,
}

MAX_HISTORY_TURNS = 6   # Giữ tối đa 3 cặp user-model (tối ưu token)


# ── History helpers ───────────────────────────────────────────────────────────

def _build_history(raw_history: list[dict]) -> list[dict]:
    """
    Chuyển history từ format app [{role, text}] → Gemini format [{role, parts}].
    Cắt bớt nếu quá dài (giữ MAX_HISTORY_TURNS turn gần nhất).
    """
    if not raw_history:
        return []
    # Chỉ giữ N turn gần nhất (để tránh token overflow)
    trimmed = raw_history[-MAX_HISTORY_TURNS:]
    result = []
    for msg in trimmed:
        role = msg.get("role", "user")
        text = msg.get("text", "")
        if role in ("user", "model") and text:
            result.append({"role": role, "parts": [{"text": text}]})
    return result


def _food_context(items: list[FoodItem]) -> str:
    """Chuyển danh sách món ăn thành context text cho Gemini."""
    if not items:
        return ""
    lines = []
    for r in items[:10]:
        price = ""
        if r.gia_min > 1 or r.gia_max > 1:
            price = f", giá {r.gia_min//1000}k–{r.gia_max//1000}k đ"
        note = f", ghi chú: {r.note}" if r.note else ""
        lines.append(f"- {r.ten_quan} ({r.ten_mon}) | {r.dia_chi}, {r.quan}{price}{note}")
    return "Dữ liệu quán ăn tìm được:\n" + "\n".join(lines)


# ── REST (single response) ────────────────────────────────────────────────────

async def chat_gemini(
    message: str,
    city: str,
    tier: ModelTier,
    max_tokens: int,
    history: list[dict] | None = None,
    food_context: list[FoodItem] | None = None,
    user_address: str | None = None,
) -> str:
    """Gọi Gemini và trả về full response string."""
    import asyncio

    hour = datetime.now().hour
    system = build_system_prompt(tier, city, hour, user_address)

    # Thêm food context vào system prompt nếu có
    if food_context:
        system += "\n\n" + _food_context(food_context)

    gemini_history = _build_history(history or [])

    model_name = _MODEL_MAP[tier]
    gen_config = GenerationConfig(max_output_tokens=min(max_tokens, _TOKEN_LIMITS[tier]))

    def _call():
        model = genai.GenerativeModel(
            model_name=model_name,
            system_instruction=system,
            generation_config=gen_config,
        )
        chat = model.start_chat(history=gemini_history)
        resp = chat.send_message(message)
        return resp.text

    loop = asyncio.get_event_loop()
    try:
        text = await loop.run_in_executor(None, _call)
        return text
    except Exception as e:
        logger.error(f"Gemini REST error: {e}")
        return f"Xin lỗi, AI đang gặp sự cố. Vui lòng thử lại sau. ({type(e).__name__})"


# ── Streaming (cho WebSocket) ─────────────────────────────────────────────────

async def stream_gemini(
    message: str,
    city: str,
    tier: ModelTier,
    max_tokens: int,
    history: list[dict] | None = None,
    food_context: list[FoodItem] | None = None,
    user_address: str | None = None,
) -> AsyncIterator[str]:
    """
    AsyncGenerator yield từng chunk text từ Gemini streaming API.
    Dùng cho WebSocket endpoint.
    Dùng threading.Thread để không block event loop.
    """
    import asyncio
    import threading
    from queue import Queue, Empty

    hour = datetime.now().hour
    system = build_system_prompt(tier, city, hour, user_address)
    if food_context:
        system += "\n\n" + _food_context(food_context)

    gemini_history = _build_history(history or [])
    model_name = _MODEL_MAP[tier]
    gen_config = GenerationConfig(max_output_tokens=min(max_tokens, _TOKEN_LIMITS[tier]))

    queue: Queue = Queue()
    DONE = object()  # sentinel

    def _stream_worker():
        try:
            model = genai.GenerativeModel(
                model_name=model_name,
                system_instruction=system,
                generation_config=gen_config,
            )
            chat = model.start_chat(history=gemini_history)
            for chunk in chat.send_message(message, stream=True):
                if chunk.text:
                    queue.put(chunk.text)
        except Exception as e:
            logger.error(f"Gemini stream error: {e}")
            queue.put(f"\n[Lỗi: {type(e).__name__}]")
        finally:
            queue.put(DONE)

    # Run in daemon thread – không block event loop
    thread = threading.Thread(target=_stream_worker, daemon=True)
    thread.start()

    while True:
        try:
            item = queue.get_nowait()
            if item is DONE:
                break
            yield item
        except Empty:
            await asyncio.sleep(0.05)   # yield control về event loop


# ── Nearby ranking ────────────────────────────────────────────────────────────

async def rank_nearby(
    items: list[FoodItem],
    user_address: str,
    city: str,
    food_type: str,
) -> str:
    """
    Dùng Gemini để xếp hạng quán gần user dựa trên địa chỉ text.
    Gemini am hiểu địa lý Việt Nam nên có thể ước tính khoảng cách.
    """
    if not items:
        return f"Không tìm thấy quán **{food_type}** nào trong dữ liệu."

    context = _food_context(items[:15])
    prompt = (
        f"User đang ở: **{user_address}**, thành phố {city}.\n"
        f"Tìm quán **{food_type}** gần nhất.\n\n"
        f"{context}\n\n"
        "Hãy xếp hạng TOP 5 quán gần user nhất dựa vào địa chỉ, "
        "kèm lý do ngắn gọn tại sao mỗi quán được chọn. "
        "Nếu quán nằm cùng quận/đường với user, ưu tiên trước."
    )

    return await chat_gemini(
        message=prompt,
        city=city,
        tier="gemini-flash",
        max_tokens=800,
    )
