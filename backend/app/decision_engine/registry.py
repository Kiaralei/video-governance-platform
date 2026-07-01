"""StrategyRegistry —— 装饰器注册 + copy-on-write 热加载。

两层结构（对齐 technical-design v3.0）：
- 类级 `_strategy_classes`：dimension_id -> 策略类。进程启动时由 @register 装饰器写入，
  运行期只读。
- 实例级 `_configs`：dimension_id -> StrategyConfig。从 dimension_registry 表热加载。
  copy-on-write：reload() 先构建全新 dict，再用一次原子引用赋值替换 —— 并发读者要么看到
  旧快照、要么看到新快照，绝不会看到"改了一半"的中间态；读路径无锁。
"""

from __future__ import annotations

import threading
from typing import Any, Optional

from .base import BaseReviewStrategy
from .types import DimensionStatus, StrategyConfig


class StrategyRegistry:
    _instance: Optional["StrategyRegistry"] = None
    _instance_lock = threading.Lock()

    # 类级注册表：所有子类共享一份（装饰器在导入期写入）。
    _strategy_classes: dict[str, type[BaseReviewStrategy]] = {}

    def __init__(self) -> None:
        # 实例级配置快照。copy-on-write：只整体替换，不原地修改。
        self._configs: dict[str, StrategyConfig] = {}
        self._write_lock = threading.Lock()

    # --- 单例 ---------------------------------------------------------------

    @classmethod
    def get_instance(cls) -> "StrategyRegistry":
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    # --- 装饰器注册 ---------------------------------------------------------

    @classmethod
    def register(cls, dimension_id: str):
        """@StrategyRegistry.register("dim_xxx") —— 把策略类登记进类级注册表。"""

        def decorator(strategy_cls: type[BaseReviewStrategy]) -> type[BaseReviewStrategy]:
            cls._strategy_classes[dimension_id] = strategy_cls
            return strategy_cls

        return decorator

    @classmethod
    def registered_dimension_ids(cls) -> list[str]:
        return sorted(cls._strategy_classes.keys())

    # --- 热加载（copy-on-write） --------------------------------------------

    def reload(self, session) -> int:
        """从 dimension_registry 表重建配置快照并原子替换。返回加载条数。"""
        from sqlalchemy import select

        from ..models import DimensionRegistry  # 延迟导入，避免循环依赖

        with self._write_lock:
            rows = session.execute(select(DimensionRegistry)).scalars().all()
            new_configs: dict[str, StrategyConfig] = {}
            for row in rows:
                new_configs[row.dimension_id] = _row_to_config(row)
            # 原子替换（引用赋值在 GIL 下原子）。
            self._configs = new_configs
        return len(new_configs)

    def load_configs(self, configs: dict[str, StrategyConfig]) -> None:
        """测试/内存场景直接注入配置快照（无需 DB）。"""
        with self._write_lock:
            self._configs = dict(configs)

    def reset(self) -> None:
        """测试专用：清空配置快照（类级策略类保留）。"""
        with self._write_lock:
            self._configs = {}

    # --- 读路径（无锁，读当前快照引用） --------------------------------------

    def configs_snapshot(self) -> dict[str, StrategyConfig]:
        return self._configs

    def get_config(self, dimension_id: str) -> Optional[StrategyConfig]:
        return self._configs.get(dimension_id)

    def build_strategy(self, dimension_id: str) -> Optional[BaseReviewStrategy]:
        config = self._configs.get(dimension_id)
        strategy_cls = self._strategy_classes.get(dimension_id)
        if config is None or strategy_cls is None:
            return None
        return strategy_cls(config)

    def _select(
        self, statuses: set[str], jurisdiction: str, llm_only: bool
    ) -> list[BaseReviewStrategy]:
        selected: list[BaseReviewStrategy] = []
        # 快照到局部变量，避免遍历途中被 reload 替换引用。
        snapshot = self._configs
        for dimension_id, config in snapshot.items():
            if config.status not in statuses:
                continue
            if not config.enabled:
                continue
            if llm_only and not config.llm_review_enabled:
                continue
            if not _enabled_for_jurisdiction(config, jurisdiction):
                continue
            strategy_cls = self._strategy_classes.get(dimension_id)
            if strategy_cls is None:
                # 注册表有配置但代码里没有对应策略类：跳过（部署错配的容错）。
                continue
            selected.append(strategy_cls(config))
        return selected

    def get_active_strategies(self, jurisdiction: str = "global") -> list[BaseReviewStrategy]:
        """生产执行：status=active 且 enabled 的维度。"""
        return self._select({DimensionStatus.ACTIVE.value}, jurisdiction, llm_only=False)

    def get_shadow_strategies(self, jurisdiction: str = "global") -> list[BaseReviewStrategy]:
        """影子执行：status=shadow —— 并行评估但不参与最终聚合。"""
        return self._select({DimensionStatus.SHADOW.value}, jurisdiction, llm_only=False)


def _enabled_for_jurisdiction(config: StrategyConfig, jurisdiction: str) -> bool:
    override = (config.jurisdiction_overrides or {}).get(jurisdiction)
    if isinstance(override, dict) and override.get("enabled") is False:
        return False
    return True


def _row_to_config(row) -> StrategyConfig:
    import json

    def _json(value, default):
        if value is None or value == "":
            return default
        if isinstance(value, (dict, list)):
            return value
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return default

    return StrategyConfig(
        dimension_id=row.dimension_id,
        dimension_name=row.dimension_name,
        dimension_axis=row.dimension_axis,
        enabled=bool(row.enabled),
        llm_review_enabled=bool(row.llm_review_enabled),
        auto_block_threshold=float(row.auto_block_threshold),
        human_review_threshold=float(row.human_review_threshold),
        prompt_template_id=row.prompt_template_id or "",
        severity_tiers=_json(row.severity_tiers, {}),
        jurisdiction_overrides=_json(row.jurisdiction_overrides, {}),
        sor_template_id=row.sor_template_id or "",
        status=row.status,
        version=int(row.version),
    )
