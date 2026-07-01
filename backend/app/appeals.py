"""Stage 7：申诉状态机 + 硬约束。对齐设计 §4.2 / PRD 模块 7。

状态机：open → in_review → overturned | rejected（后两者为终态）。
硬约束：
- 二审排除原审核员（独立性）。
- 申诉通道内【不可加重处置】：改判只能 BLOCK → PASS，绝不能 PASS → BLOCK。
- 改判触发恢复连锁四链：恢复可见性 + 账号处罚回滚 + 质检负反馈 + 改判样本回流。
"""

from __future__ import annotations

from enum import Enum


class AppealStatus(str, Enum):
    OPEN = "open"              # 已提交，待分配
    IN_REVIEW = "in_review"    # 二审中
    OVERTURNED = "overturned"  # 改判（终态，触发恢复连锁）
    REJECTED = "rejected"      # 维持原判（终态）


VALID_TRANSITIONS: dict[str, set[str]] = {
    AppealStatus.OPEN.value: {AppealStatus.IN_REVIEW.value},
    AppealStatus.IN_REVIEW.value: {AppealStatus.OVERTURNED.value, AppealStatus.REJECTED.value},
    AppealStatus.OVERTURNED.value: set(),
    AppealStatus.REJECTED.value: set(),
}

# 申诉只能对 BLOCK 处置发起（PASS 无需申诉，且申诉通道不可加重到 BLOCK）。
APPEALABLE_DECISIONS = {"block"}

# 改判方向：原处置 -> 允许改判到的目标处置（不可加重）。
OVERTURN_TARGET = {"block": "pass"}


def can_transition(current: str, target: str) -> bool:
    return target in VALID_TRANSITIONS.get(current, set())
