from pydantic_settings import BaseSettings
from typing import Any


class Settings(BaseSettings):
    ANTHROPIC_API_KEY: str = ""
    DATABASE_URL: str = "sqlite:///./moderation.db"
    UPLOAD_DIR: str = "./uploads"
    FRAMES_DIR: str = "./frames"
    MAX_FRAMES: int = 8
    MODEL: str = "claude-sonnet-4-6"

    class Config:
        env_file = ".env"


settings = Settings()

# Regional policy thresholds — override per market
REGIONAL_POLICIES: dict[str, dict[str, Any]] = {
    "global": {
        "safety_auto_block": 80,
        "safety_human_review": 40,
        "underage_auto_block": 50,   # Lower threshold, zero tolerance
        "quality_auto_block": 90,
        "quality_human_review": 60,
        "business_human_review": 55,
        "misinformation_block": 999,  # Disabled globally
        "extra_checks": [],
    },
    "US": {
        "safety_auto_block": 75,
        "safety_human_review": 35,
        "underage_auto_block": 40,
        "quality_auto_block": 88,
        "quality_human_review": 55,
        "business_human_review": 50,
        "misinformation_block": 65,   # Strict in US
        "extra_checks": ["misinformation", "election_integrity"],
    },
    "EU": {
        "safety_auto_block": 72,
        "safety_human_review": 35,
        "underage_auto_block": 40,
        "quality_auto_block": 85,
        "quality_human_review": 55,
        "business_human_review": 50,
        "misinformation_block": 70,
        "extra_checks": ["hate_speech", "gdpr_compliance"],
    },
    "SEA": {
        "safety_auto_block": 82,
        "safety_human_review": 45,
        "underage_auto_block": 55,
        "quality_auto_block": 92,
        "quality_human_review": 65,
        "business_human_review": 60,
        "misinformation_block": 999,
        "extra_checks": [],
    },
}
