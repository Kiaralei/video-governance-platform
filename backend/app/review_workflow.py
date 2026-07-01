"""Stage 6：人审工作流状态机 + 优先级枚举。

对齐设计 §4.1/§4.2。MVP 用 pending → in_review → decided 主路径（release/超时回 pending），
并保留合法转移矩阵以便后续接入 awaiting_second_review / delivery 等状态。
"""

from __future__ import annotations

from enum import Enum


class ReviewStatus(str, Enum):
    PENDING = "pending"          # 待分配
    IN_REVIEW = "in_review"      # 已领取/审核中（持案件锁）
    DECIDED = "decided"          # 已判定（终态，MVP 内）


# 合法状态转移矩阵。self-loop（in_review→in_review 续租/接管）单独放行，不在此表。
VALID_TRANSITIONS: dict[str, set[str]] = {
    ReviewStatus.PENDING.value: {ReviewStatus.IN_REVIEW.value, ReviewStatus.DECIDED.value},
    ReviewStatus.IN_REVIEW.value: {ReviewStatus.PENDING.value, ReviewStatus.DECIDED.value},
    ReviewStatus.DECIDED.value: set(),
}


class QueuePriority(int, Enum):
    CRITICAL = 1        # CSAM/暴力等高危（critical_escalate）
    LEGAL_DEADLINE = 2  # 有法定时限
    HIGH = 3            # 高风险（auto_block）
    NORMAL = 5          # 常规 needs_human_review
    LOW = 8             # 低风险/低置信（auto_pass）
    BACKFILL = 10       # 回扫/补审


# 机审最终决策 -> 队列优先级。
DECISION_PRIORITY: dict[str, int] = {
    "critical_escalate": QueuePriority.CRITICAL.value,
    "auto_block": QueuePriority.HIGH.value,
    "needs_human_review": QueuePriority.NORMAL.value,
    "auto_pass": QueuePriority.LOW.value,
}


def can_transition(current: str, target: str) -> bool:
    if current == target:
        return True  # 幂等/续租
    return target in VALID_TRANSITIONS.get(current, set())
