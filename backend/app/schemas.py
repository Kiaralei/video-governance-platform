"""请求体的 Pydantic 契约。

这一层只约束【传输结构】（字段、类型、默认值），并自动生成 OpenAPI 文档。
【业务规则】（标题/描述非空、队列是否已满、裁定只能 pass/block）仍然由
GovernanceService 负责 —— 保持单一事实源，避免同一条规则在两处各写一遍。
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class ContentUploadRequest(BaseModel):
    """内容摄取请求体。

    字段全部带默认值：业务上的“标题/描述不能为空”由服务层校验并返回 400，
    这里不重复。extra="allow" 允许透传未来新增字段而无需改这里。
    """

    model_config = ConfigDict(extra="allow")

    title: str = Field("", description="视频标题")
    description: str = Field("", description="视频简介")
    creator_id: str = Field("anonymous", description="创作者 ID")
    poi: str = Field("global", description="挂载地点 / POI")
    video_url: str = Field("", description="视频来源：远程 URL、本地路径或 file:// 路径")


class BatchIngestRequest(BaseModel):
    """批量摄取。逐条业务校验与错误聚合仍在服务层完成，故 items 保持为松散对象。"""

    items: list[dict[str, Any]] = Field(default_factory=list, description="待摄取内容条目数组")


class ClaimRequest(BaseModel):
    reviewer_id: str = Field("reviewer_demo", description="领取任务的审核员 ID")


class DecideRequest(BaseModel):
    """人审裁定请求。

    decision 声明为 str 而非 Literal["pass","block"]：合法取值属于业务规则，
    由服务层裁决（并被单元测试直接覆盖），schema 只保证 decision/reason 必填。
    """

    decision: str = Field(..., description="裁定结果，MVP 仅接受 pass / block")
    reason: str = Field(..., description="裁定理由")
    reviewer_id: str = Field("reviewer_demo", description="裁定审核员 ID")


class DrainRequest(BaseModel):
    limit: Optional[int] = Field(None, description="本次最多处理的流水线任务数，缺省处理全部积压")
