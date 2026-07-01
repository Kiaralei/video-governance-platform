"""Stage 9：Statement of Reason（对外理由）模板。

对外 SoR 与内部理由（internal reason）物理分离：SoR 只给申诉人/创作者看的合规化措辞，
绝不泄露内部审核笔记或具体阈值。对齐设计 §12.3。
"""

from __future__ import annotations

# 维度 -> 对外可读理由（合规化、不暴露内部细节）。
DIMENSION_PUBLIC_REASON = {
    "dim_gambling": "涉及博彩/彩票相关内容",
    "dim_drug_violence": "涉及毒品或暴力相关内容",
    "dim_minor_compliance": "涉及未成年人保护相关问题",
    "dim_marketing_review": "涉及违规营销或导流",
    "dim_poi_match": "内容与所标注信息不一致",
    "dim_general_policy": "违反平台通用内容政策",
}

SOR_TEMPLATE_ID = "sor_mvp_v1"


def render_sor(decision: str, title: str, triggered_dimension_ids: list[str]) -> str:
    title = title or "（无标题）"
    if decision == "pass":
        return f"您的内容《{title}》已通过审核，可正常展示。"
    reasons = [
        DIMENSION_PUBLIC_REASON.get(d, "违反平台内容规范") for d in triggered_dimension_ids
    ]
    # 去重保序；无具体维度时给出兜底理由。
    reasons = list(dict.fromkeys(reasons)) or ["违反平台内容规范"]
    return (
        f"您的内容《{title}》未通过审核。根据平台社区规范，我们检测到：{'；'.join(reasons)}。"
        f"如您认为存在误判，可在申诉入口提交申诉，平台将安排独立审核员复核。"
    )
