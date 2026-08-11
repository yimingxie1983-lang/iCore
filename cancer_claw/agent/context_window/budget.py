

from __future__ import annotations

from dataclasses import dataclass, field

from cancer_claw.config import settings

def estimate_tokens(text: str) -> int:

    if not text:
        return 0

    chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    ratio = chinese_chars / max(len(text), 1)

    chars_per_token = 2.5 - ratio * 1.0
    return max(int(len(text) / chars_per_token), 1)

@dataclass
class BudgetAllocation:

    total: int
    p0_system: int
    p1_craft: int
    p2_memory: int
    p3_plan: int
    p4_conversation: int
    p5_craft_index: int

@dataclass
class BudgetUsage:

    p0_used: int = 0
    p1_used: int = 0
    p2_used: int = 0
    p3_used: int = 0
    p4_used: int = 0
    p5_used: int = 0

    @property
    def total_used(self) -> int:

        return self.p0_used + self.p1_used + self.p2_used + self.p3_used + self.p4_used + self.p5_used

class ContextBudget:


    def __init__(self, max_tokens: int | None = None):

        self._max_tokens = max_tokens or settings.context.default_max_tokens
        self._usage = BudgetUsage()
        self._allocation = self._calculate_allocation()

    def _calculate_allocation(self) -> BudgetAllocation:

        ctx = settings.context
        total = self._max_tokens


        p0 = ctx.soul_budget + 1000 + 1000
        p1 = int(total * ctx.craft_total_ratio)
        p2 = ctx.memory_budget
        p3 = ctx.plan_budget
        p5 = int(total * ctx.craft_index_ratio)


        p4 = total - p0 - p1 - p2 - p3 - p5
        p4 = max(p4, 2000)

        return BudgetAllocation(
            total=total,
            p0_system=p0,
            p1_craft=p1,
            p2_memory=p2,
            p3_plan=p3,
            p4_conversation=p4,
            p5_craft_index=p5,
        )

    @property
    def allocation(self) -> BudgetAllocation:

        return self._allocation

    @property
    def usage(self) -> BudgetUsage:

        return self._usage

    @property
    def usage_ratio(self) -> float:

        return self._usage.total_used / self._max_tokens

    def update_usage(self, **kwargs):

        for key, value in kwargs.items():
            if hasattr(self._usage, key):
                setattr(self._usage, key, value)

    def remaining(self, zone: str) -> int:

        alloc_key = zone
        usage_key = zone.replace("p0_system", "p0_used").replace("p1_craft", "p1_used") \
                        .replace("p2_memory", "p2_used").replace("p3_plan", "p3_used") \
                        .replace("p4_conversation", "p4_used").replace("p5_craft_index", "p5_used")

        allocated = getattr(self._allocation, alloc_key, 0)
        used = getattr(self._usage, usage_key, 0)
        return max(allocated - used, 0)

    def get_summary(self) -> dict:

        a = self._allocation
        u = self._usage
        return {
            "total": a.total,
            "total_used": u.total_used,
            "usage_ratio": round(self.usage_ratio, 3),
            "zones": {
                "P0_system": {"budget": a.p0_system, "used": u.p0_used},
                "P1_craft": {"budget": a.p1_craft, "used": u.p1_used},
                "P2_memory": {"budget": a.p2_memory, "used": u.p2_used},
                "P3_plan": {"budget": a.p3_plan, "used": u.p3_used},
                "P4_conversation": {"budget": a.p4_conversation, "used": u.p4_used},
                "P5_craft_index": {"budget": a.p5_craft_index, "used": u.p5_used},
            }
        }
