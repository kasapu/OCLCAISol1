"""
FastAPI Application - Main Entry Point.

This module provides the REST API for the OCLC WMS Matcher system.
"""

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime
import uuid

from ..models.database import get_db, init_database, Job, JobStatus, MatchResultDB
from ..parsers.marc_parser import MARCParser, MARCFormat
from ..matching.matching_engine import MatchingPipeline, MatchStatus
from ..utils.config import get_settings
from ..utils.logging import get_logger


# Initialize settings and logger
settings = get_settings()
logger = get_logger(__name__)

# Create FastAPI app
app = FastAPI(
    title="OCLC WMS Matcher API",
    description="AI-powered bibliographic record matching and data enrichment system",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url, "*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Pydantic Models for API

class JobCreate(BaseModel):
    """Request model for creating a job."""
    customer_id: str = Field(..., description="Customer identifier")
    source_system: Optional[str] = Field(None, description="Source library system")
    source_file: str = Field(..., description="Path to source MARC file")
    options: Optional[dict] = Field(default_factory=dict, description="Processing options")


class JobResponse(BaseModel):
    """Response model for job."""
    job_id: str
    customer_id: str
    status: str
    total_records: int
    processed_records: int
    matched_records: int
    review_required: int
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True


class MatchResultResponse(BaseModel):
    """Response model for match result."""
    id: int
    source_record_id: str
    match_status: str
    confidence_score: float
    requires_review: bool
    worldcat_oclc_number: Optional[str]
    match_strategy: Optional[str]
    processing_timestamp: datetime
    reviewed: bool

    class Config:
        from_attributes = True


class StatsResponse(BaseModel):
    """Response model for statistics."""
    total_jobs: int
    active_jobs: int
    completed_jobs: int
    total_records_processed: int
    auto_match_rate: float
    avg_confidence_score: float


# API Endpoints

@app.on_event("startup")
async def startup_event():
    """Initialize application on startup."""
    logger.info("starting_api_application", version="1.0.0")

    # Initialize database
    try:
        init_database()
        logger.info("database_initialized")
    except Exception as e:
        logger.error("database_initialization_failed", error=str(e))


@app.get("/", tags=["Health"])
async def root():
    """Root endpoint - health check."""
    return {
        "status": "healthy",
        "service": "OCLC WMS Matcher API",
        "version": "1.0.0"
    }


@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat()
    }


@app.post("/api/v1/jobs", response_model=JobResponse, tags=["Jobs"])
async def create_job(
    job_data: JobCreate,
    db: Session = Depends(get_db)
):
    """
    Create a new matching job.

    This endpoint creates a new job for batch processing MARC records.
    """
    try:
        # Generate job ID
        job_id = f"JOB-{uuid.uuid4().hex[:12].upper()}"

        # Create job record
        job = Job(
            job_id=job_id,
            customer_id=job_data.customer_id,
            source_system=job_data.source_system,
            source_file_path=job_data.source_file,
            config=job_data.options,
            status=JobStatus.PENDING
        )

        db.add(job)
        db.commit()
        db.refresh(job)

        logger.info(
            "job_created",
            job_id=job_id,
            customer_id=job_data.customer_id
        )

        # TODO: Trigger async processing with Celery
        # from ..pipeline.batch_processor import process_job
        # process_job.delay(job_id)

        return JobResponse(
            job_id=job.job_id,
            customer_id=job.customer_id,
            status=job.status.value,
            total_records=job.total_records,
            processed_records=job.processed_records,
            matched_records=job.matched_records,
            review_required=job.review_required,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at
        )

    except Exception as e:
        logger.error("job_creation_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/jobs/{job_id}", response_model=JobResponse, tags=["Jobs"])
async def get_job(
    job_id: str,
    db: Session = Depends(get_db)
):
    """Get job status and details."""
    job = db.query(Job).filter(Job.job_id == job_id).first()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return JobResponse(
        job_id=job.job_id,
        customer_id=job.customer_id,
        status=job.status.value,
        total_records=job.total_records,
        processed_records=job.processed_records,
        matched_records=job.matched_records,
        review_required=job.review_required,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at
    )


@app.get("/api/v1/jobs", response_model=List[JobResponse], tags=["Jobs"])
async def list_jobs(
    customer_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """List all jobs with optional filtering."""
    query = db.query(Job)

    if customer_id:
        query = query.filter(Job.customer_id == customer_id)

    if status:
        try:
            status_enum = JobStatus[status.upper()]
            query = query.filter(Job.status == status_enum)
        except KeyError:
            raise HTTPException(status_code=400, detail="Invalid status value")

    jobs = query.order_by(Job.created_at.desc()).limit(limit).all()

    return [
        JobResponse(
            job_id=job.job_id,
            customer_id=job.customer_id,
            status=job.status.value,
            total_records=job.total_records,
            processed_records=job.processed_records,
            matched_records=job.matched_records,
            review_required=job.review_required,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at
        )
        for job in jobs
    ]


@app.get("/api/v1/jobs/{job_id}/results", response_model=List[MatchResultResponse], tags=["Results"])
async def get_job_results(
    job_id: str,
    requires_review: Optional[bool] = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """Get match results for a job."""
    # Verify job exists
    job = db.query(Job).filter(Job.job_id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Query results
    query = db.query(MatchResultDB).filter(MatchResultDB.job_id == job_id)

    if requires_review is not None:
        query = query.filter(MatchResultDB.requires_review == requires_review)

    results = query.offset(offset).limit(limit).all()

    return [
        MatchResultResponse(
            id=result.id,
            source_record_id=result.source_record_id,
            match_status=result.match_status.value,
            confidence_score=result.confidence_score,
            requires_review=result.requires_review,
            worldcat_oclc_number=result.worldcat_oclc_number,
            match_strategy=result.match_strategy,
            processing_timestamp=result.processing_timestamp,
            reviewed=result.reviewed
        )
        for result in results
    ]


@app.get("/api/v1/results/{result_id}", tags=["Results"])
async def get_result_detail(
    result_id: int,
    db: Session = Depends(get_db)
):
    """Get detailed information about a match result."""
    result = db.query(MatchResultDB).filter(MatchResultDB.id == result_id).first()

    if not result:
        raise HTTPException(status_code=404, detail="Result not found")

    return {
        "id": result.id,
        "job_id": result.job_id,
        "source_record_id": result.source_record_id,
        "source_record_data": result.source_record_data,
        "match_status": result.match_status.value,
        "confidence_score": result.confidence_score,
        "requires_review": result.requires_review,
        "review_reason": result.review_reason,
        "worldcat_oclc_number": result.worldcat_oclc_number,
        "worldcat_record": result.worldcat_record,
        "match_strategy": result.match_strategy,
        "match_features": result.match_features,
        "alternative_matches": result.alternative_matches,
        "local_variations": result.local_variations,
        "enrichment_applied": result.enrichment_applied,
        "processing_timestamp": result.processing_timestamp,
        "processing_time_ms": result.processing_time_ms,
        "reviewed": result.reviewed,
        "reviewed_at": result.reviewed_at,
        "reviewed_by": result.reviewed_by,
        "review_decision": result.review_decision,
        "review_notes": result.review_notes
    }


@app.get("/api/v1/stats", response_model=StatsResponse, tags=["Analytics"])
async def get_stats(
    customer_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get system statistics."""
    from sqlalchemy import func

    # Build query
    jobs_query = db.query(Job)
    results_query = db.query(MatchResultDB)

    if customer_id:
        jobs_query = jobs_query.filter(Job.customer_id == customer_id)
        # Filter results by jobs from this customer
        job_ids = [job.job_id for job in jobs_query.all()]
        results_query = results_query.filter(MatchResultDB.job_id.in_(job_ids))

    # Calculate stats
    total_jobs = jobs_query.count()
    active_jobs = jobs_query.filter(Job.status.in_([JobStatus.PENDING, JobStatus.RUNNING])).count()
    completed_jobs = jobs_query.filter(Job.status == JobStatus.COMPLETED).count()

    total_records = results_query.count()

    # Auto match rate
    from ..matching.matching_engine import MatchStatus as MatchStatusEnum
    from ..models.database import MatchStatusDB
    auto_matches = results_query.filter(MatchResultDB.match_status == MatchStatusDB.AUTO_MATCH).count()
    auto_match_rate = (auto_matches / total_records * 100) if total_records > 0 else 0.0

    # Average confidence
    avg_confidence = db.query(func.avg(MatchResultDB.confidence_score)).scalar() or 0.0

    return StatsResponse(
        total_jobs=total_jobs,
        active_jobs=active_jobs,
        completed_jobs=completed_jobs,
        total_records_processed=total_records,
        auto_match_rate=round(auto_match_rate, 2),
        avg_confidence_score=round(float(avg_confidence), 3)
    )


@app.post("/api/v1/match/single", tags=["Matching"])
async def match_single_record(file: UploadFile = File(...)):
    """
    Match a single MARC record.

    Upload a MARC file containing one record for immediate matching.
    """
    try:
        # Save uploaded file temporarily
        import tempfile
        import os

        with tempfile.NamedTemporaryFile(delete=False, suffix=".mrc") as tmp_file:
            content = await file.read()
            tmp_file.write(content)
            tmp_file_path = tmp_file.name

        try:
            # Parse record
            parser = MARCParser()
            records = parser.parse_file(tmp_file_path)

            if not records:
                raise HTTPException(status_code=400, detail="No valid MARC records found")

            # Match the first record
            pipeline = MatchingPipeline()
            result = pipeline.match_record(records[0])

            return result.to_dict()

        finally:
            # Clean up
            os.unlink(tmp_file_path)

    except Exception as e:
        logger.error("single_match_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
