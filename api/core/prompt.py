"""
core/prompt.py – PromptBuilder class.
Trách nhiệm: xây dựng system prompt và context cho Gemini.
"""
from typing import Optional
from ..models import FoodItem
from .router import ModelTier

MAX_HISTORY_TURNS = 6  # BR4: giữ tối đa 6 turn


class PromptBuilder:
    """Xây dựng prompts cho Gemini API."""

    # ── System prompt ──────────────────────────────────────────────────────────

    def build_system(
        self,
        tier: ModelTier,
        city: str,
        hour: int,
        meal_time: str,
        user_address: Optional[str] = None,
    ) -> str:
        """Trả về system prompt phù hợp với tier."""
        loc = f"User ở: {user_address}." if user_address else "Không có địa chỉ."
        if tier == "local":
            return f"AI ẩm thực – {city} – {hour}h ({meal_time})."
        if tier == "gemini-flash":
            return (
                f"Bạn là trợ lý ẩm thực AI cho {city}. "
                f"Hiện tại: {hour}h ({meal_time}). {loc} "
                "Trả lời ngắn gọn, chính xác, tiếng Việt."
            )
        return (
            f"Bạn là chuyên gia ẩm thực AI cho {city}.\n"
            f"Thời gian: {hour}h ({meal_time}). {loc}\n"
            "Tư vấn món ăn, tìm quán gần user, gợi ý phù hợp.\n"
            "Luôn trả lời tiếng Việt, thân thiện, cụ thể."
        )

    # ── Food context ───────────────────────────────────────────────────────────

    def build_food_context(self, items: list[FoodItem]) -> str:
        """Chuyển danh sách FoodItem thành text context."""
        if not items:
            return ""
        lines = [self._format_item(r) for r in items[:10]]
        return "Dữ liệu quán ăn:\n" + "\n".join(lines)

    def _format_item(self, r: FoodItem) -> str:
        price = self._price_range(r.gia_min, r.gia_max)
        note = f", {r.note}" if r.note else ""
        return f"- {r.ten_quan} ({r.ten_mon}) | {r.dia_chi}, {r.quan}{price}{note}"

    def _price_range(self, mn: int, mx: int) -> str:
        if mn <= 1 and mx <= 1:
            return ""
        return f", {mn // 1000}k–{mx // 1000}k đ"

    # ── History ────────────────────────────────────────────────────────────────

    def build_history(self, raw: list[dict]) -> list[dict]:
        """Chuyển [{role, text}] → Gemini format [{role, parts}]."""
        trimmed = self.trim_history(raw)
        return [
            {"role": m["role"], "parts": [{"text": m["text"]}]}
            for m in trimmed
            if m.get("role") in ("user", "model") and m.get("text")
        ]

    def trim_history(self, history: list[dict]) -> list[dict]:
        """Giữ tối đa MAX_HISTORY_TURNS turn gần nhất (BR4)."""
        return history[-MAX_HISTORY_TURNS:] if history else []
