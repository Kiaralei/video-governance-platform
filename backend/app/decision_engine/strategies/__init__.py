"""策略实现集合。导入即触发 @StrategyRegistry.register 装饰器注册。

新增维度：在本目录新建一个策略文件，用 @StrategyRegistry.register("dim_xxx") 装饰类，
并在此 import。数据库 dimension_registry 表插入对应配置后即可上线，核心代码零改动。
"""

from __future__ import annotations

from . import (  # noqa: F401
    drug_violence,
    gambling,
    general_policy,
    marketing,
    minor_compliance,
    poi_match,
)
