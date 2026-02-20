"""
core/router.py – QueryRouter class.
Phân loại query và quyết định model AI phù hợp.
Trách nhiệm: phân loại ONLY – không gọi AI, không search.
"""
import re
from dataclasses import dataclass
from typing import Literal

ModelTier = Literal["local", "gemini-flash", "gemini-pro"]
QueryType = Literal["simple", "complex", "heavy"]

SIMPLE_PATTERNS = [
    r"t[oô]i (mu[oố]n|th[iíì]ch|c[aầ]n) [aă]n",
    r"cho t[oô]i ([aă]n|th[uử]|g[oợ]i [yý])",
    r"[aă]n g[iì] (ngon|b[aâ]y gi[oờ]|h[oô]m nay)",
    r"m[oó]n g[iì] ngon",
    r"g[oợ]i [yý] (m[oó]n|[dđ][oồ] [aă]n|qu[aá]n)",
    r"gi[aá] (bao nhi[eê]u|th[eế] n[aà]o)",
    r"so s[aá]nh gi[aá]",
    r"bao nhi[eê]u ti[eề]n",
    # No-diacritic
    r"toi (muon|thich|can) an",
    r"cho toi (an|thu|goi y)",
    r"goi y (mon|do an|quan)",
    r"gia bao nhieu|bao nhieu tien|so sanh gia",
]

COMPLEX_PATTERNS = [
    r"g[aầ]n (t[oô]i|[dđ][aâ]y|nh[aấ]t)",
    r"qu[aá]n (g[aầ]n|xung quanh|khu v[uự]c)",
    r"t[iì]m (qu[aá]n|ch[oỗ] [aă]n|nh[aà] h[aà]ng)",
    r"b[aâ]y gi[oờ] (n[eê]n|c[oó] th[eể]|mu[oố]n)",
    r"(t[oố]i|tr[uư]a|s[aá]ng|chi[eề]u) (nay|h[oô]m nay|n[aà]y)",
    r"l[uú]c (n[aà]y|b[aâ]y gi[oờ]|\d+h)",
    r"ch[iỉ] ([dđ][uư][oờ]ng|t[oô]i|c[aá]ch [dđ]i)",
    # No-diacritic
    r"gan (toi|day|nhat)",
    r"tim (quan|cho an)",
    r"bay gio nen",
]

HEAVY_PATTERNS = [
    r"so s[aá]nh.+(v[oớ]i|v[aà]|vs).+(v[oớ]i|v[aà]|vs)",
    r"(k[eế] ho[aạ]ch|l[iị]ch).+([aă]n|b[uữ]a).+(c[aả] ng[aà]y|h[oô]m nay)",
]


@dataclass
class RouteDecision:
    model: ModelTier
    max_output_tokens: int
    query_type: QueryType
    reason: str


class QueryRouter:
    """Phân loại query → chọn model tier phù hợp."""

    def __init__(self) -> None:
        self._simple  = [re.compile(p, re.I) for p in SIMPLE_PATTERNS]
        self._complex = [re.compile(p, re.I) for p in COMPLEX_PATTERNS]
        self._heavy   = [re.compile(p, re.I) for p in HEAVY_PATTERNS]

    # ── Public ─────────────────────────────────────────────────────────────────

    def route(self, query: str, has_location: bool = False) -> RouteDecision:
        """Phân tích query và trả về RouteDecision."""
        q = query.strip()
        if self._is_heavy(q):
            return RouteDecision("gemini-pro", 1500, "heavy", "Query phức tạp nhiều tầng")
        if self._is_complex(q, has_location):
            return RouteDecision("gemini-flash", 800, "complex", "Query location/time/đa điều kiện")
        return RouteDecision("local", 256, "simple", "Simple – dùng template")

    @staticmethod
    def get_meal_time(hour: int) -> str:
        """Trả về tên bữa ăn theo giờ."""
        if 6  <= hour < 10: return "Bữa sáng"
        if 10 <= hour < 14: return "Bữa trưa"
        if 14 <= hour < 17: return "Xế chiều"
        if 17 <= hour < 21: return "Bữa tối"
        return "Ăn đêm"

    # ── Private ────────────────────────────────────────────────────────────────

    def _is_heavy(self, q: str) -> bool:
        return len(q) > 200 or any(p.search(q) for p in self._heavy)

    def _is_complex(self, q: str, has_location: bool) -> bool:
        location_hit = has_location and re.search(r"g[aầ]n|xung quanh|khu v[uự]c|gan|nearby", q, re.I)
        return bool(location_hit) or any(p.search(q) for p in self._complex) or len(q) > 100

    def _match(self, patterns: list, q: str) -> bool:
        return any(p.search(q) for p in patterns)
