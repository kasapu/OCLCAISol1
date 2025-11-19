"""
Configuration management for OCLC WMS Matcher.

This module handles loading and validating configuration from environment variables
and provides a centralized configuration object for the entire application.
"""

from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field, validator


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Application
    app_name: str = Field(default="OCLC WMS Matcher", env="APP_NAME")
    app_version: str = Field(default="1.0.0", env="APP_VERSION")
    app_env: str = Field(default="development", env="APP_ENV")
    debug: bool = Field(default=True, env="DEBUG")
    log_level: str = Field(default="INFO", env="LOG_LEVEL")

    # WorldCat API
    worldcat_api_key: str = Field(default="", env="WORLDCAT_API_KEY")
    worldcat_api_secret: str = Field(default="", env="WORLDCAT_API_SECRET")
    worldcat_base_url: str = Field(
        default="https://worldcat.org/api",
        env="WORLDCAT_BASE_URL"
    )
    worldcat_rate_limit: int = Field(default=100, env="WORLDCAT_RATE_LIMIT")
    worldcat_rate_period: int = Field(default=60, env="WORLDCAT_RATE_PERIOD")

    # AI/ML Services
    openai_api_key: str = Field(default="", env="OPENAI_API_KEY")
    anthropic_api_key: str = Field(default="", env="ANTHROPIC_API_KEY")
    huggingface_token: str = Field(default="", env="HUGGINGFACE_TOKEN")
    openai_rate_limit: int = Field(default=50, env="OPENAI_RATE_LIMIT")
    openai_rate_period: int = Field(default=60, env="OPENAI_RATE_PERIOD")

    # Database
    database_url: str = Field(
        default="postgresql://oclc_user:oclc_password@localhost:5432/oclc_wms",
        env="DATABASE_URL"
    )
    database_pool_size: int = Field(default=10, env="DATABASE_POOL_SIZE")
    database_max_overflow: int = Field(default=20, env="DATABASE_MAX_OVERFLOW")

    # Redis
    redis_url: str = Field(default="redis://localhost:6379/0", env="REDIS_URL")
    redis_cache_ttl: int = Field(default=3600, env="REDIS_CACHE_TTL")

    # Celery
    celery_broker_url: str = Field(
        default="redis://localhost:6379/1",
        env="CELERY_BROKER_URL"
    )
    celery_result_backend: str = Field(
        default="redis://localhost:6379/2",
        env="CELERY_RESULT_BACKEND"
    )

    # Processing Configuration
    batch_size: int = Field(default=1000, env="BATCH_SIZE")
    max_workers: int = Field(default=4, env="MAX_WORKERS")
    max_concurrent_jobs: int = Field(default=10, env="MAX_CONCURRENT_JOBS")
    processing_timeout: int = Field(default=7200, env="PROCESSING_TIMEOUT")

    # Confidence Thresholds
    confidence_threshold_auto: float = Field(
        default=0.95,
        env="CONFIDENCE_THRESHOLD_AUTO"
    )
    confidence_threshold_assisted: float = Field(
        default=0.75,
        env="CONFIDENCE_THRESHOLD_ASSISTED"
    )
    confidence_threshold_manual: float = Field(
        default=0.50,
        env="CONFIDENCE_THRESHOLD_MANUAL"
    )

    # Enrichment Sources
    enable_open_library: bool = Field(default=True, env="ENABLE_OPEN_LIBRARY")
    enable_google_books: bool = Field(default=True, env="ENABLE_GOOGLE_BOOKS")
    enable_ai_enrichment: bool = Field(default=True, env="ENABLE_AI_ENRICHMENT")
    open_library_api_url: str = Field(
        default="https://openlibrary.org/api",
        env="OPEN_LIBRARY_API_URL"
    )
    google_books_api_key: str = Field(default="", env="GOOGLE_BOOKS_API_KEY")

    # Security
    secret_key: str = Field(
        default="your_secret_key_here_change_in_production",
        env="SECRET_KEY"
    )
    algorithm: str = Field(default="HS256", env="ALGORITHM")
    access_token_expire_minutes: int = Field(
        default=30,
        env="ACCESS_TOKEN_EXPIRE_MINUTES"
    )

    # API Server
    api_host: str = Field(default="0.0.0.0", env="API_HOST")
    api_port: int = Field(default=8000, env="API_PORT")
    api_workers: int = Field(default=4, env="API_WORKERS")

    # Frontend
    frontend_url: str = Field(default="http://localhost:3000", env="FRONTEND_URL")

    # Storage
    upload_dir: str = Field(default="/tmp/oclc_uploads", env="UPLOAD_DIR")
    result_dir: str = Field(default="/tmp/oclc_results", env="RESULT_DIR")
    max_upload_size: int = Field(default=524288000, env="MAX_UPLOAD_SIZE")

    # ML Model Configuration
    sentence_transformer_model: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2",
        env="SENTENCE_TRANSFORMER_MODEL"
    )
    ml_model_path: str = Field(default="/models", env="ML_MODEL_PATH")
    model_cache_dir: str = Field(default="/models/cache", env="MODEL_CACHE_DIR")

    # Quality Thresholds
    min_completeness_score: int = Field(
        default=40,
        env="MIN_COMPLETENESS_SCORE"
    )
    dark_record_threshold: int = Field(
        default=40,
        env="DARK_RECORD_THRESHOLD"
    )

    # Monitoring
    enable_metrics: bool = Field(default=True, env="ENABLE_METRICS")
    metrics_port: int = Field(default=9090, env="METRICS_PORT")
    sentry_dsn: str = Field(default="", env="SENTRY_DSN")

    # Feature Flags
    enable_experimental_features: bool = Field(
        default=False,
        env="ENABLE_EXPERIMENTAL_FEATURES"
    )
    enable_active_learning: bool = Field(
        default=True,
        env="ENABLE_ACTIVE_LEARNING"
    )
    enable_batch_enrichment: bool = Field(
        default=True,
        env="ENABLE_BATCH_ENRICHMENT"
    )

    @validator("confidence_threshold_auto")
    def validate_auto_threshold(cls, v):
        """Validate AUTO threshold is between 0 and 1."""
        if not 0 <= v <= 1:
            raise ValueError("Auto threshold must be between 0 and 1")
        return v

    @validator("confidence_threshold_assisted")
    def validate_assisted_threshold(cls, v):
        """Validate ASSISTED threshold is between 0 and 1."""
        if not 0 <= v <= 1:
            raise ValueError("Assisted threshold must be between 0 and 1")
        return v

    @validator("confidence_threshold_manual")
    def validate_manual_threshold(cls, v):
        """Validate MANUAL threshold is between 0 and 1."""
        if not 0 <= v <= 1:
            raise ValueError("Manual threshold must be between 0 and 1")
        return v

    class Config:
        """Pydantic configuration."""
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


# Global settings instance
settings = Settings()


def get_settings() -> Settings:
    """Get the global settings instance."""
    return settings


def reload_settings() -> Settings:
    """Reload settings from environment (useful for testing)."""
    global settings
    settings = Settings()
    return settings
