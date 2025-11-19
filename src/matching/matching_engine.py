"""
Matching Engine - Multi-stage Pipeline for Record Matching.

This module orchestrates the matching process using multiple strategies:
1. Exact match (ISBN/ISSN/OCLC number)
2. High-confidence fuzzy match (title + author + year)
3. AI-assisted match (ML model for ambiguous cases)
"""

from typing import Dict, List, Optional, Tuple, Any
from enum import Enum
from dataclasses import dataclass
from datetime import datetime
import redis

from ..parsers.marc_parser import MARCRecord
from ..clients.worldcat_client import WorldCatClient, SearchStrategy
from .feature_extraction import FeatureExtractor, MatchFeatures
from .ml_models import HybridMatcher
from ..utils.logging import get_logger
from ..utils.config import get_settings


logger = get_logger(__name__)


class MatchStatus(Enum):
    """Match result status."""
    AUTO_MATCH = "auto_match"           # Confidence > 0.95
    ASSISTED_MATCH = "assisted_match"   # 0.75 - 0.95
    MANUAL_REVIEW = "manual_review"     # 0.50 - 0.75
    NO_MATCH = "no_match"               # < 0.50


class MatchStrategy(Enum):
    """Strategy used for matching."""
    ISBN_EXACT = "isbn_exact"
    ISSN_EXACT = "issn_exact"
    OCLC_NUMBER = "oclc_number"
    TITLE_AUTHOR_FUZZY = "title_author_fuzzy"
    AI_ASSISTED = "ai_assisted"
    ENRICHED = "enriched"


@dataclass
class MatchResult:
    """Result of a matching operation."""

    # Source record info
    source_record_id: str

    # Match status
    match_status: MatchStatus
    confidence_score: float
    requires_review: bool
    review_reason: Optional[str]

    # WorldCat match (if found)
    worldcat_oclc_number: Optional[str]
    worldcat_record: Optional[Dict[str, Any]]

    # Matching details
    match_strategy: MatchStrategy
    match_features: Optional[MatchFeatures]

    # Alternative matches (for review)
    alternative_matches: List[Dict[str, Any]]

    # Local variations detected
    local_variations: List[Dict[str, Any]]

    # Enrichment applied
    enrichment_applied: List[str]

    # Metadata
    processing_timestamp: str
    processing_time_ms: float

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "source_record_id": self.source_record_id,
            "match_status": self.match_status.value,
            "confidence_score": self.confidence_score,
            "requires_review": self.requires_review,
            "review_reason": self.review_reason,
            "worldcat_oclc_number": self.worldcat_oclc_number,
            "worldcat_record": self.worldcat_record,
            "match_strategy": self.match_strategy.value,
            "match_details": {
                "isbn_match": self.match_features.isbn_exact_match if self.match_features else None,
                "title_similarity": self.match_features.title_similarity if self.match_features else None,
                "author_similarity": self.match_features.author_similarity if self.match_features else None,
                "year_match": self.match_features.year_match if self.match_features else None,
            } if self.match_features else None,
            "alternative_matches": self.alternative_matches,
            "local_variations": self.local_variations,
            "enrichment_applied": self.enrichment_applied,
            "processing_timestamp": self.processing_timestamp,
            "processing_time_ms": self.processing_time_ms
        }


class MatchingPipeline:
    """Multi-stage matching pipeline."""

    def __init__(
        self,
        worldcat_client: Optional[WorldCatClient] = None,
        hybrid_matcher: Optional[HybridMatcher] = None,
        feature_extractor: Optional[FeatureExtractor] = None
    ):
        """
        Initialize matching pipeline.

        Args:
            worldcat_client: WorldCat API client
            hybrid_matcher: Hybrid matching model
            feature_extractor: Feature extractor
        """
        self.worldcat_client = worldcat_client or WorldCatClient()
        self.hybrid_matcher = hybrid_matcher or HybridMatcher()
        self.feature_extractor = feature_extractor or FeatureExtractor()
        self.settings = get_settings()
        self.logger = get_logger(__name__)

    def match_record(self, source_record: MARCRecord) -> MatchResult:
        """
        Match a single record through the pipeline.

        Args:
            source_record: Source MARC record to match

        Returns:
            MatchResult with matching details
        """
        start_time = datetime.now()

        self.logger.info(
            "matching_record",
            record_id=source_record.control_number,
            title=source_record.title[:50] if source_record.title else None
        )

        # Stage 1: Exact match by ISBN
        if source_record.isbn:
            result = self._match_by_isbn(source_record)
            if result:
                return self._finalize_result(result, start_time)

        # Stage 2: Exact match by ISSN
        if source_record.issn:
            result = self._match_by_issn(source_record)
            if result:
                return self._finalize_result(result, start_time)

        # Stage 3: OCLC number lookup
        if source_record.control_number:
            result = self._match_by_oclc(source_record)
            if result:
                return self._finalize_result(result, start_time)

        # Stage 4: Fuzzy match by title + author
        if source_record.title:
            result = self._match_by_title_author(source_record)
            if result:
                return self._finalize_result(result, start_time)

        # Stage 5: No match found
        return self._create_no_match_result(source_record, start_time)

    def _match_by_isbn(self, source_record: MARCRecord) -> Optional[MatchResult]:
        """Match by ISBN exact match."""
        for isbn in source_record.isbn:
            candidates = self.worldcat_client.search_by_isbn(isbn)

            if candidates:
                # Take the first (best) match
                candidate = candidates[0]

                # Extract features
                features = self.feature_extractor.extract_features(
                    source_record,
                    candidate
                )

                # Verify it's a good match
                if features.isbn_exact_match:
                    confidence = max(0.95, features.overall_confidence)

                    return MatchResult(
                        source_record_id=source_record.control_number or "unknown",
                        match_status=MatchStatus.AUTO_MATCH,
                        confidence_score=confidence,
                        requires_review=False,
                        review_reason=None,
                        worldcat_oclc_number=candidate.get("oclc_number"),
                        worldcat_record=candidate,
                        match_strategy=MatchStrategy.ISBN_EXACT,
                        match_features=features,
                        alternative_matches=candidates[1:5],  # Keep top alternatives
                        local_variations=[],
                        enrichment_applied=[],
                        processing_timestamp=datetime.now().isoformat(),
                        processing_time_ms=0.0
                    )

        return None

    def _match_by_issn(self, source_record: MARCRecord) -> Optional[MatchResult]:
        """Match by ISSN exact match."""
        for issn in source_record.issn:
            candidates = self.worldcat_client.search_by_issn(issn)

            if candidates:
                candidate = candidates[0]

                features = self.feature_extractor.extract_features(
                    source_record,
                    candidate
                )

                if features.issn_exact_match:
                    confidence = max(0.95, features.overall_confidence)

                    return MatchResult(
                        source_record_id=source_record.control_number or "unknown",
                        match_status=MatchStatus.AUTO_MATCH,
                        confidence_score=confidence,
                        requires_review=False,
                        review_reason=None,
                        worldcat_oclc_number=candidate.get("oclc_number"),
                        worldcat_record=candidate,
                        match_strategy=MatchStrategy.ISSN_EXACT,
                        match_features=features,
                        alternative_matches=candidates[1:5],
                        local_variations=[],
                        enrichment_applied=[],
                        processing_timestamp=datetime.now().isoformat(),
                        processing_time_ms=0.0
                    )

        return None

    def _match_by_oclc(self, source_record: MARCRecord) -> Optional[MatchResult]:
        """Match by OCLC number."""
        candidate = self.worldcat_client.search_by_oclc_number(
            source_record.control_number
        )

        if candidate:
            features = self.feature_extractor.extract_features(
                source_record,
                candidate
            )

            if features.oclc_number_match:
                confidence = max(0.98, features.overall_confidence)

                return MatchResult(
                    source_record_id=source_record.control_number or "unknown",
                    match_status=MatchStatus.AUTO_MATCH,
                    confidence_score=confidence,
                    requires_review=False,
                    review_reason=None,
                    worldcat_oclc_number=candidate.get("oclc_number"),
                    worldcat_record=candidate,
                    match_strategy=MatchStrategy.OCLC_NUMBER,
                    match_features=features,
                    alternative_matches=[],
                    local_variations=[],
                    enrichment_applied=[],
                    processing_timestamp=datetime.now().isoformat(),
                    processing_time_ms=0.0
                )

        return None

    def _match_by_title_author(self, source_record: MARCRecord) -> Optional[MatchResult]:
        """Match by title and author fuzzy matching."""
        # Get main author if available
        author = source_record.authors[0] if source_record.authors else None

        # Search WorldCat
        candidates = self.worldcat_client.search_by_title_author(
            title=source_record.title,
            author=author,
            year=source_record.publication_year,
            limit=10
        )

        if not candidates:
            return None

        # Evaluate each candidate
        scored_candidates = []

        for candidate in candidates:
            features = self.feature_extractor.extract_features(
                source_record,
                candidate
            )

            # Calculate hybrid score
            hybrid_score = self.hybrid_matcher.calculate_match_score(
                features,
                source_record.title or "",
                candidate.get("title", "")
            )

            scored_candidates.append({
                "candidate": candidate,
                "features": features,
                "score": hybrid_score
            })

        # Sort by score
        scored_candidates.sort(key=lambda x: x["score"], reverse=True)

        if scored_candidates:
            best = scored_candidates[0]
            score = best["score"]
            features = best["features"]
            candidate = best["candidate"]

            # Determine match status based on confidence thresholds
            if score >= self.settings.confidence_threshold_auto:
                status = MatchStatus.AUTO_MATCH
                requires_review = False
                review_reason = None

            elif score >= self.settings.confidence_threshold_assisted:
                status = MatchStatus.ASSISTED_MATCH
                requires_review = True
                review_reason = "Medium confidence - please verify"

            elif score >= self.settings.confidence_threshold_manual:
                status = MatchStatus.MANUAL_REVIEW
                requires_review = True
                review_reason = "Low confidence - manual review required"

            else:
                # Score too low, treat as no match
                return None

            return MatchResult(
                source_record_id=source_record.control_number or "unknown",
                match_status=status,
                confidence_score=score,
                requires_review=requires_review,
                review_reason=review_reason,
                worldcat_oclc_number=candidate.get("oclc_number"),
                worldcat_record=candidate,
                match_strategy=MatchStrategy.AI_ASSISTED,
                match_features=features,
                alternative_matches=[sc["candidate"] for sc in scored_candidates[1:5]],
                local_variations=[],
                enrichment_applied=[],
                processing_timestamp=datetime.now().isoformat(),
                processing_time_ms=0.0
            )

        return None

    def _create_no_match_result(
        self,
        source_record: MARCRecord,
        start_time: datetime
    ) -> MatchResult:
        """Create a NO_MATCH result."""
        processing_time = (datetime.now() - start_time).total_seconds() * 1000

        return MatchResult(
            source_record_id=source_record.control_number or "unknown",
            match_status=MatchStatus.NO_MATCH,
            confidence_score=0.0,
            requires_review=True,
            review_reason="No suitable match found in WorldCat",
            worldcat_oclc_number=None,
            worldcat_record=None,
            match_strategy=MatchStrategy.AI_ASSISTED,
            match_features=None,
            alternative_matches=[],
            local_variations=[],
            enrichment_applied=[],
            processing_timestamp=datetime.now().isoformat(),
            processing_time_ms=processing_time
        )

    def _finalize_result(
        self,
        result: MatchResult,
        start_time: datetime
    ) -> MatchResult:
        """Finalize result with processing time."""
        processing_time = (datetime.now() - start_time).total_seconds() * 1000
        result.processing_time_ms = processing_time
        result.processing_timestamp = datetime.now().isoformat()

        self.logger.info(
            "matching_completed",
            record_id=result.source_record_id,
            status=result.match_status.value,
            confidence=result.confidence_score,
            strategy=result.match_strategy.value,
            processing_time_ms=processing_time
        )

        return result

    def batch_match(
        self,
        source_records: List[MARCRecord]
    ) -> List[MatchResult]:
        """
        Match multiple records.

        Args:
            source_records: List of source records

        Returns:
            List of match results
        """
        results = []

        for record in source_records:
            try:
                result = self.match_record(record)
                results.append(result)

            except Exception as e:
                self.logger.error(
                    "record_matching_failed",
                    record_id=record.control_number,
                    error=str(e)
                )

                # Create error result
                results.append(
                    MatchResult(
                        source_record_id=record.control_number or "unknown",
                        match_status=MatchStatus.NO_MATCH,
                        confidence_score=0.0,
                        requires_review=True,
                        review_reason=f"Processing error: {str(e)}",
                        worldcat_oclc_number=None,
                        worldcat_record=None,
                        match_strategy=MatchStrategy.AI_ASSISTED,
                        match_features=None,
                        alternative_matches=[],
                        local_variations=[],
                        enrichment_applied=[],
                        processing_timestamp=datetime.now().isoformat(),
                        processing_time_ms=0.0
                    )
                )

        return results
