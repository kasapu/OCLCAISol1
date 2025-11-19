"""
Database Models and Schema.

This module defines the database models for storing:
- Job records
- Match results
- Audit logs
- Feedback for model training
"""

from typing import Optional
from datetime import datetime
from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Float,
    Boolean,
    DateTime,
    Text,
    JSON,
    ForeignKey,
    Enum as SQLEnum
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, Session
import enum

from ..utils.config import get_settings
from ..utils.logging import get_logger


Base = declarative_base()
logger = get_logger(__name__)


class JobStatus(enum.Enum):
    """Job processing status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class MatchStatusDB(enum.Enum):
    """Match status for database."""
    AUTO_MATCH = "auto_match"
    ASSISTED_MATCH = "assisted_match"
    MANUAL_REVIEW = "manual_review"
    NO_MATCH = "no_match"


class Job(Base):
    """Job table for tracking batch processing jobs."""

    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(100), unique=True, nullable=False, index=True)
    customer_id = Column(String(100), nullable=False, index=True)
    source_system = Column(String(100))
    source_file_path = Column(Text, nullable=False)

    # Job configuration
    config = Column(JSON)

    # Status tracking
    status = Column(SQLEnum(JobStatus), default=JobStatus.PENDING, nullable=False)
    total_records = Column(Integer, default=0)
    processed_records = Column(Integer, default=0)
    matched_records = Column(Integer, default=0)
    review_required = Column(Integer, default=0)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)

    # Error tracking
    error_message = Column(Text)

    # Relationships
    match_results = relationship("MatchResultDB", back_populates="job", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Job(job_id='{self.job_id}', status='{self.status.value}', customer='{self.customer_id}')>"


class MatchResultDB(Base):
    """Match results table."""

    __tablename__ = "match_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(100), ForeignKey("jobs.job_id"), nullable=False, index=True)

    # Source record info
    source_record_id = Column(String(100), nullable=False)
    source_record_data = Column(JSON)

    # Match status
    match_status = Column(SQLEnum(MatchStatusDB), nullable=False, index=True)
    confidence_score = Column(Float, nullable=False)
    requires_review = Column(Boolean, default=False, index=True)
    review_reason = Column(Text)

    # WorldCat match
    worldcat_oclc_number = Column(String(50), index=True)
    worldcat_record = Column(JSON)

    # Matching details
    match_strategy = Column(String(50))
    match_features = Column(JSON)

    # Alternative matches
    alternative_matches = Column(JSON)

    # Local variations
    local_variations = Column(JSON)

    # Enrichment
    enrichment_applied = Column(JSON)

    # Processing metadata
    processing_timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    processing_time_ms = Column(Float)

    # Review status
    reviewed = Column(Boolean, default=False, index=True)
    reviewed_at = Column(DateTime)
    reviewed_by = Column(String(100))
    review_decision = Column(String(50))
    review_notes = Column(Text)

    # Relationships
    job = relationship("Job", back_populates="match_results")
    feedback = relationship("Feedback", back_populates="match_result", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<MatchResult(record_id='{self.source_record_id}', status='{self.match_status.value}', confidence={self.confidence_score:.2f})>"


class Feedback(Base):
    """Feedback table for model training."""

    __tablename__ = "feedback"

    id = Column(Integer, primary_key=True, autoincrement=True)
    match_result_id = Column(Integer, ForeignKey("match_results.id"), nullable=False, index=True)

    # Feedback data
    is_correct_match = Column(Boolean, nullable=False)
    corrected_oclc_number = Column(String(50))
    feedback_type = Column(String(50))  # 'approve', 'reject', 'correct', 'flag'
    comments = Column(Text)

    # User info
    submitted_by = Column(String(100))
    submitted_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Training usage
    used_for_training = Column(Boolean, default=False)
    training_timestamp = Column(DateTime)

    # Relationships
    match_result = relationship("Feedback", back_populates="feedback")

    def __repr__(self):
        return f"<Feedback(match_result_id={self.match_result_id}, is_correct={self.is_correct_match})>"


class AuditLog(Base):
    """Audit log for tracking all system actions."""

    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Action details
    action = Column(String(100), nullable=False, index=True)
    entity_type = Column(String(50))  # 'job', 'match_result', 'feedback', etc.
    entity_id = Column(String(100))

    # User/system info
    performed_by = Column(String(100))
    ip_address = Column(String(50))

    # Details
    details = Column(JSON)
    status = Column(String(50))
    error_message = Column(Text)

    def __repr__(self):
        return f"<AuditLog(action='{self.action}', timestamp='{self.timestamp}')>"


# Database connection and session management

class Database:
    """Database connection manager."""

    def __init__(self, database_url: Optional[str] = None):
        """
        Initialize database connection.

        Args:
            database_url: Database URL (defaults to config)
        """
        settings = get_settings()
        self.database_url = database_url or settings.database_url

        # Create engine
        self.engine = create_engine(
            self.database_url,
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
            echo=settings.debug
        )

        # Create session factory
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine
        )

        self.logger = get_logger(__name__)

    def create_tables(self):
        """Create all tables."""
        self.logger.info("creating_database_tables")
        Base.metadata.create_all(bind=self.engine)
        self.logger.info("database_tables_created")

    def drop_tables(self):
        """Drop all tables (use with caution!)."""
        self.logger.warning("dropping_all_database_tables")
        Base.metadata.drop_all(bind=self.engine)
        self.logger.info("database_tables_dropped")

    def get_session(self) -> Session:
        """
        Get a database session.

        Returns:
            SQLAlchemy Session
        """
        return self.SessionLocal()

    def migrate(self):
        """Run database migrations."""
        # In production, use Alembic for migrations
        # For now, just create tables
        self.create_tables()


# Dependency for FastAPI
def get_db() -> Session:
    """
    Get database session dependency for FastAPI.

    Yields:
        Database session
    """
    settings = get_settings()
    db = Database(settings.database_url)
    session = db.get_session()

    try:
        yield session
    finally:
        session.close()


# Global database instance
_db_instance: Optional[Database] = None


def get_database() -> Database:
    """Get global database instance."""
    global _db_instance

    if _db_instance is None:
        _db_instance = Database()

    return _db_instance


def init_database():
    """Initialize database (create tables)."""
    db = get_database()
    db.create_tables()


if __name__ == "__main__":
    # Script to initialize database
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "migrate":
        init_database()
        print("Database initialized successfully!")
    else:
        print("Usage: python -m src.models.database migrate")
