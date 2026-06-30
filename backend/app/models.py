from sqlalchemy import Column, String, Integer, Float, JSON, DateTime, ForeignKey, Text, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import enum
import uuid


def gen_id():
    return str(uuid.uuid4())


class VideoStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    AUTO_PASS = "auto_pass"
    AUTO_BLOCK = "auto_block"
    HUMAN_REVIEW = "human_review"
    HUMAN_PASS = "human_pass"
    HUMAN_BLOCK = "human_block"


class Region(str, enum.Enum):
    GLOBAL = "global"
    US = "US"
    EU = "EU"
    SEA = "SEA"


class Video(Base):
    __tablename__ = "videos"

    id = Column(String, primary_key=True, default=gen_id)
    title = Column(String, nullable=False)
    description = Column(Text, default="")
    region = Column(String, default="global")
    geo_tag = Column(String, default="")
    creator_id = Column(String, default="")
    status = Column(String, default=VideoStatus.PENDING)
    video_path = Column(String, nullable=False)
    thumbnail_path = Column(String, default="")
    duration_seconds = Column(Float, default=0)
    created_at = Column(DateTime, server_default=func.now())
    processed_at = Column(DateTime, nullable=True)
    processing_ms = Column(Integer, default=0)

    analysis = relationship("Analysis", back_populates="video", uselist=False)
    review = relationship("HumanReview", back_populates="video", uselist=False)
    audit_logs = relationship("AuditLog", back_populates="video")


class Analysis(Base):
    __tablename__ = "analyses"

    id = Column(String, primary_key=True, default=gen_id)
    video_id = Column(String, ForeignKey("videos.id"), unique=True)

    # Dimension 1: Safety
    violence_score = Column(Float, default=0)
    underage_score = Column(Float, default=0)
    substances_score = Column(Float, default=0)
    safety_max_score = Column(Float, default=0)
    safety_details = Column(JSON, default={})

    # Dimension 2: Quality
    art_style_score = Column(Float, default=0)
    marketing_score = Column(Float, default=0)
    quality_max_score = Column(Float, default=0)
    quality_details = Column(JSON, default={})

    # Dimension 3: Business
    description_match_score = Column(Float, default=0)
    geo_validity_score = Column(Float, default=0)
    misinformation_score = Column(Float, default=0)
    content_category = Column(String, default="")
    business_details = Column(JSON, default={})

    # Decision
    overall_risk_score = Column(Float, default=0)
    decision = Column(String, default="")
    decision_reason = Column(Text, default="")
    confidence = Column(Float, default=0)
    model_version = Column(String, default="claude-sonnet-4-6")

    created_at = Column(DateTime, server_default=func.now())
    video = relationship("Video", back_populates="analysis")


class HumanReview(Base):
    __tablename__ = "human_reviews"

    id = Column(String, primary_key=True, default=gen_id)
    video_id = Column(String, ForeignKey("videos.id"), unique=True)
    priority = Column(Integer, default=5)   # 1=critical, 10=low
    assigned_to = Column(String, default="")
    decision = Column(String, default="")
    reviewer_notes = Column(Text, default="")
    override_reason = Column(Text, default="")
    created_at = Column(DateTime, server_default=func.now())
    reviewed_at = Column(DateTime, nullable=True)

    video = relationship("Video", back_populates="review")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String, primary_key=True, default=gen_id)
    video_id = Column(String, ForeignKey("videos.id"))
    action = Column(String, nullable=False)
    actor = Column(String, default="system")
    details = Column(JSON, default={})
    created_at = Column(DateTime, server_default=func.now())

    video = relationship("Video", back_populates="audit_logs")
