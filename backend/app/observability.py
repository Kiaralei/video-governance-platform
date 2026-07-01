"""Stage 9：Prometheus 文本渲染（不引 prometheus_client 依赖）。

指标快照由服务层用 SQL 汇总产出，这里只负责渲染为 Prometheus exposition 文本。
对齐设计 §9.4 的业务指标口径。
"""

from __future__ import annotations

from typing import Any

# 指标名 -> (类型, 帮助文本)。
METRIC_META: dict[str, tuple[str, str]] = {
    "vgp_human_review_queue_size": ("gauge", "人审队列深度（pending）"),
    "vgp_human_review_sla_violations_total": ("gauge", "SLA 违规任务数（未决且已过截止）"),
    "vgp_dead_letter_tasks_total": ("gauge", "死信任务累计数"),
    "vgp_flywheel_samples_total": ("gauge", "回流样本总数"),
    "vgp_appeal_overturn_rate": ("gauge", "申诉改判率"),
    "vgp_golden_test_accuracy": ("gauge", "黄金题准确率"),
}


def render_prometheus(snapshot: dict[str, Any]) -> str:
    lines: list[str] = []

    # 决策分布带 label：vgp_pipeline_decision_total{decision="..."}。
    decisions = snapshot.get("pipeline_decision_total", {})
    lines.append("# HELP vgp_pipeline_decision_total 最终决策分布 (pass/block/none)")
    lines.append("# TYPE vgp_pipeline_decision_total gauge")
    for decision, count in sorted(decisions.items()):
        lines.append(f'vgp_pipeline_decision_total{{decision="{decision}"}} {count}')

    # 流水线任务状态分布。
    jobs = snapshot.get("pipeline_jobs", {})
    lines.append("# HELP vgp_pipeline_jobs 机审流水线任务状态分布")
    lines.append("# TYPE vgp_pipeline_jobs gauge")
    for status, count in sorted(jobs.items()):
        lines.append(f'vgp_pipeline_jobs{{status="{status}"}} {count}')

    for name, (mtype, help_text) in METRIC_META.items():
        key = name.replace("vgp_", "")
        if key not in snapshot:
            continue
        lines.append(f"# HELP {name} {help_text}")
        lines.append(f"# TYPE {name} {mtype}")
        lines.append(f"{name} {snapshot[key]}")

    return "\n".join(lines) + "\n"
