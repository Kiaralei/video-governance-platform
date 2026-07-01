"""BaseReviewStrategy 抽象基类。

新增审核维度时只需：
  1. 继承 BaseReviewStrategy
  2. 实现 review()（同步；引擎用线程池并行执行多个维度）
  3. 在 dimension_registry 表注册配置

无需修改决策引擎、人审工作台、申诉闭环、审计日志等核心代码。

注意：参考设计里的 review() 是 async 的；本仓库全链路同步（SQLAlchemy 同步 session、
Celery/线程 worker），故这里落地为同步方法，并行由 DecisionEngineService 的
ThreadPoolExecutor 提供 —— 语义等价、测试可确定。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .types import DimensionVerdict, StrategyConfig


class BaseReviewStrategy(ABC):
    def __init__(self, config: StrategyConfig):
        self.config = config
        self.dimension_id = config.dimension_id
        self.dimension_name = config.dimension_name

    @abstractmethod
    def review(self, evidence: dict[str, Any], policy_version: str) -> DimensionVerdict:
        """对证据包执行该维度审查。只输出理解与归因，不输出处置动作。"""
        ...

    @abstractmethod
    def build_prompt(self, evidence: dict[str, Any]) -> str:
        """构建该维度的 LLM Prompt。"""
        ...

    # --- 证据取值助手（子类共用，避免各自重复解析 evidence dict） --------------

    def _text_blob(self, evidence: dict[str, Any]) -> str:
        """把标题/简介/OCR/ASR 拼成一段小写文本，供关键词匹配。"""
        meta = evidence.get("metadata", {}) or {}
        parts = [str(meta.get("title", "")), str(meta.get("description", ""))]
        for item in evidence.get("ocr_results", []) or []:
            parts.append(str(item.get("text", "")))
        for seg in evidence.get("asr_transcript", []) or []:
            parts.append(str(seg.get("text", "")))
        return " ".join(parts).lower()

    def _object_labels(self, evidence: dict[str, Any]) -> list[str]:
        return [str(d.get("label", "")).lower() for d in evidence.get("object_detections", []) or []]

    def _scene_tags(self, evidence: dict[str, Any]) -> list[str]:
        return [str(s.get("tag", "")).lower() for s in evidence.get("scene_tags", []) or []]

    def _build_evidence_summary(self, evidence: dict[str, Any]) -> str:
        meta = evidence.get("metadata", {}) or {}
        return (
            f"title={meta.get('title', '')}; "
            f"asr={' '.join(s.get('text', '') for s in evidence.get('asr_transcript', []) or [])}; "
            f"ocr={' '.join(i.get('text', '') for i in evidence.get('ocr_results', []) or [])}; "
            f"objects={','.join(self._object_labels(evidence))}; "
            f"scenes={','.join(self._scene_tags(evidence))}"
        )
