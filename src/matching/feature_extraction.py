"""
Feature Extraction for Record Matching.

This module extracts and computes features from MARC records
that are used for fuzzy matching and ML-based matching.
"""

import re
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
import numpy as np
from Levenshtein import distance as levenshtein_distance
from fuzzywuzzy import fuzz

from ..parsers.marc_parser import MARCRecord
from ..utils.logging import get_logger


logger = get_logger(__name__)


@dataclass
class MatchFeatures:
    """Container for extracted match features."""

    # Exact match features
    isbn_exact_match: bool
    issn_exact_match: bool
    oclc_number_match: bool

    # String similarity features
    title_similarity: float  # 0-1
    title_levenshtein_distance: int
    author_similarity: float  # 0-1
    publisher_similarity: float  # 0-1

    # Publication features
    year_match: bool
    year_difference: int

    # Classification features
    lc_classification_match: bool
    dewey_classification_match: bool
    subject_overlap: float  # 0-1

    # Composite scores
    overall_confidence: float  # 0-1

    # Raw data for debugging
    debug_info: Dict[str, Any]


class FeatureExtractor:
    """Extracts features for record matching."""

    def __init__(self):
        """Initialize feature extractor."""
        self.logger = get_logger(__name__)

    def extract_features(
        self,
        source_record: MARCRecord,
        candidate_record: Dict[str, Any]
    ) -> MatchFeatures:
        """
        Extract matching features from source and candidate records.

        Args:
            source_record: Source MARC record
            candidate_record: Candidate WorldCat record

        Returns:
            MatchFeatures object with all extracted features
        """
        # ISBN matching
        isbn_match = self._check_isbn_match(
            source_record.isbn,
            candidate_record.get("isbn", [])
        )

        # ISSN matching
        issn_match = self._check_issn_match(
            source_record.issn,
            candidate_record.get("issn", [])
        )

        # OCLC number matching
        oclc_match = self._check_oclc_match(
            source_record.control_number,
            candidate_record.get("oclc_number")
        )

        # Title similarity
        title_sim, title_lev = self._calculate_title_similarity(
            source_record.title,
            candidate_record.get("title")
        )

        # Author similarity
        author_sim = self._calculate_author_similarity(
            source_record.authors,
            candidate_record.get("author")
        )

        # Publisher similarity
        publisher_sim = self._calculate_publisher_similarity(
            source_record.publisher,
            candidate_record.get("publisher")
        )

        # Publication year
        year_match, year_diff = self._check_year_match(
            source_record.publication_year,
            candidate_record.get("year")
        )

        # Classification matching
        lc_match = self._check_classification_match(
            source_record.classification_lc,
            candidate_record.get("classification_lc")
        )

        dewey_match = self._check_classification_match(
            source_record.classification_dewey,
            candidate_record.get("classification_dewey")
        )

        # Subject heading overlap
        subject_overlap = self._calculate_subject_overlap(
            source_record.subject_headings,
            candidate_record.get("subjects", [])
        )

        # Calculate overall confidence
        overall_confidence = self._calculate_overall_confidence(
            isbn_match=isbn_match,
            issn_match=issn_match,
            oclc_match=oclc_match,
            title_sim=title_sim,
            author_sim=author_sim,
            publisher_sim=publisher_sim,
            year_match=year_match,
            lc_match=lc_match,
            dewey_match=dewey_match,
            subject_overlap=subject_overlap
        )

        # Debug information
        debug_info = {
            "source_title": source_record.title,
            "candidate_title": candidate_record.get("title"),
            "source_authors": source_record.authors,
            "candidate_author": candidate_record.get("author"),
            "source_year": source_record.publication_year,
            "candidate_year": candidate_record.get("year")
        }

        return MatchFeatures(
            isbn_exact_match=isbn_match,
            issn_exact_match=issn_match,
            oclc_number_match=oclc_match,
            title_similarity=title_sim,
            title_levenshtein_distance=title_lev,
            author_similarity=author_sim,
            publisher_similarity=publisher_sim,
            year_match=year_match,
            year_difference=year_diff,
            lc_classification_match=lc_match,
            dewey_classification_match=dewey_match,
            subject_overlap=subject_overlap,
            overall_confidence=overall_confidence,
            debug_info=debug_info
        )

    def _check_isbn_match(
        self,
        source_isbns: List[str],
        candidate_isbns: List[str]
    ) -> bool:
        """Check if any ISBNs match."""
        if not source_isbns or not candidate_isbns:
            return False

        # Normalize ISBNs
        source_normalized = {self._normalize_isbn(isbn) for isbn in source_isbns}
        candidate_normalized = {self._normalize_isbn(isbn) for isbn in candidate_isbns}

        return bool(source_normalized & candidate_normalized)

    def _check_issn_match(
        self,
        source_issns: List[str],
        candidate_issns: List[str]
    ) -> bool:
        """Check if any ISSNs match."""
        if not source_issns or not candidate_issns:
            return False

        source_normalized = {self._normalize_issn(issn) for issn in source_issns}
        candidate_normalized = {self._normalize_issn(issn) for issn in candidate_issns}

        return bool(source_normalized & candidate_normalized)

    def _check_oclc_match(
        self,
        source_oclc: Optional[str],
        candidate_oclc: Optional[str]
    ) -> bool:
        """Check if OCLC numbers match."""
        if not source_oclc or not candidate_oclc:
            return False

        # Normalize OCLC numbers (remove prefixes, etc.)
        source_normalized = self._normalize_oclc(source_oclc)
        candidate_normalized = self._normalize_oclc(candidate_oclc)

        return source_normalized == candidate_normalized

    def _calculate_title_similarity(
        self,
        source_title: Optional[str],
        candidate_title: Optional[str]
    ) -> Tuple[float, int]:
        """
        Calculate title similarity.

        Returns:
            Tuple of (similarity score 0-1, Levenshtein distance)
        """
        if not source_title or not candidate_title:
            return 0.0, 9999

        # Normalize titles
        source_norm = self._normalize_title(source_title)
        candidate_norm = self._normalize_title(candidate_title)

        # Calculate similarity using multiple methods
        ratio = fuzz.ratio(source_norm, candidate_norm) / 100.0
        partial_ratio = fuzz.partial_ratio(source_norm, candidate_norm) / 100.0
        token_sort_ratio = fuzz.token_sort_ratio(source_norm, candidate_norm) / 100.0

        # Use the maximum for flexibility
        similarity = max(ratio, partial_ratio, token_sort_ratio)

        # Calculate Levenshtein distance
        lev_dist = levenshtein_distance(source_norm, candidate_norm)

        return similarity, lev_dist

    def _calculate_author_similarity(
        self,
        source_authors: List[str],
        candidate_author: Optional[str]
    ) -> float:
        """Calculate author name similarity."""
        if not source_authors or not candidate_author:
            return 0.0

        # Normalize author names
        candidate_norm = self._normalize_author(candidate_author)

        # Check against all source authors
        max_similarity = 0.0
        for source_author in source_authors:
            source_norm = self._normalize_author(source_author)

            # Use token sort ratio to handle name order variations
            similarity = fuzz.token_sort_ratio(source_norm, candidate_norm) / 100.0
            max_similarity = max(max_similarity, similarity)

        return max_similarity

    def _calculate_publisher_similarity(
        self,
        source_publisher: Optional[str],
        candidate_publisher: Optional[str]
    ) -> float:
        """Calculate publisher similarity."""
        if not source_publisher or not candidate_publisher:
            return 0.0

        source_norm = self._normalize_publisher(source_publisher)
        candidate_norm = self._normalize_publisher(candidate_publisher)

        # Use partial ratio for publisher (handles variations)
        similarity = fuzz.partial_ratio(source_norm, candidate_norm) / 100.0

        return similarity

    def _check_year_match(
        self,
        source_year: Optional[int],
        candidate_year: Optional[Any]
    ) -> Tuple[bool, int]:
        """
        Check if publication years match (with tolerance).

        Returns:
            Tuple of (is_match, year_difference)
        """
        if source_year is None or candidate_year is None:
            return False, 9999

        # Convert candidate year to int if needed
        try:
            if isinstance(candidate_year, str):
                # Extract first 4-digit year
                match = re.search(r'\b(1[0-9]{3}|20[0-9]{2})\b', candidate_year)
                if match:
                    candidate_year = int(match.group(1))
                else:
                    return False, 9999
            else:
                candidate_year = int(candidate_year)
        except (ValueError, TypeError):
            return False, 9999

        year_diff = abs(source_year - candidate_year)

        # Allow ±2 years for reprints/different editions
        is_match = year_diff <= 2

        return is_match, year_diff

    def _check_classification_match(
        self,
        source_class: Optional[str],
        candidate_class: Optional[str]
    ) -> bool:
        """Check if classification numbers match (prefix matching)."""
        if not source_class or not candidate_class:
            return False

        # Normalize
        source_norm = source_class.strip().upper()
        candidate_norm = candidate_class.strip().upper()

        # Exact match
        if source_norm == candidate_norm:
            return True

        # Check if they share significant prefix (first 2-3 characters)
        min_prefix = min(len(source_norm), len(candidate_norm), 3)
        if min_prefix >= 2:
            return source_norm[:min_prefix] == candidate_norm[:min_prefix]

        return False

    def _calculate_subject_overlap(
        self,
        source_subjects: List[str],
        candidate_subjects: List[str]
    ) -> float:
        """Calculate subject heading overlap using Jaccard similarity."""
        if not source_subjects or not candidate_subjects:
            return 0.0

        # Normalize subjects
        source_norm = {self._normalize_subject(s) for s in source_subjects}
        candidate_norm = {self._normalize_subject(s) for s in candidate_subjects}

        # Calculate Jaccard similarity
        intersection = len(source_norm & candidate_norm)
        union = len(source_norm | candidate_norm)

        if union == 0:
            return 0.0

        return intersection / union

    def _calculate_overall_confidence(
        self,
        isbn_match: bool,
        issn_match: bool,
        oclc_match: bool,
        title_sim: float,
        author_sim: float,
        publisher_sim: float,
        year_match: bool,
        lc_match: bool,
        dewey_match: bool,
        subject_overlap: float
    ) -> float:
        """
        Calculate overall confidence score using weighted features.

        Returns:
            Confidence score between 0 and 1
        """
        # If we have exact identifier match, high confidence
        if isbn_match or issn_match or oclc_match:
            base_confidence = 0.95

            # Adjust based on other factors
            if title_sim > 0.8:
                return min(base_confidence + 0.05, 1.0)
            elif title_sim < 0.5:
                return base_confidence - 0.1

            return base_confidence

        # Otherwise, use weighted combination of features
        weights = {
            "title": 0.35,
            "author": 0.25,
            "year": 0.15,
            "publisher": 0.10,
            "classification": 0.10,
            "subjects": 0.05
        }

        score = 0.0

        # Title contribution
        score += weights["title"] * title_sim

        # Author contribution
        score += weights["author"] * author_sim

        # Year contribution
        score += weights["year"] * (1.0 if year_match else 0.0)

        # Publisher contribution
        score += weights["publisher"] * publisher_sim

        # Classification contribution
        if lc_match or dewey_match:
            score += weights["classification"] * 1.0
        else:
            score += weights["classification"] * 0.0

        # Subject contribution
        score += weights["subjects"] * subject_overlap

        return min(score, 1.0)

    # Normalization helpers

    def _normalize_isbn(self, isbn: str) -> str:
        """Normalize ISBN for comparison."""
        # Remove hyphens, spaces, and convert to uppercase
        normalized = re.sub(r'[^0-9X]', '', isbn.upper())

        # Convert ISBN-10 to ISBN-13 if needed
        if len(normalized) == 10:
            # Simple conversion (not complete checksum calculation)
            normalized = "978" + normalized[:-1]

        return normalized

    def _normalize_issn(self, issn: str) -> str:
        """Normalize ISSN for comparison."""
        return re.sub(r'[^0-9X]', '', issn.upper())

    def _normalize_oclc(self, oclc: str) -> str:
        """Normalize OCLC number for comparison."""
        # Remove common prefixes
        oclc = re.sub(r'^(ocm|ocn|on)', '', oclc, flags=re.IGNORECASE)
        # Keep only digits
        return re.sub(r'\D', '', oclc)

    def _normalize_title(self, title: str) -> str:
        """Normalize title for comparison."""
        # Convert to lowercase
        normalized = title.lower()

        # Remove articles
        normalized = re.sub(r'^(the|a|an)\s+', '', normalized)

        # Remove punctuation and extra spaces
        normalized = re.sub(r'[^\w\s]', ' ', normalized)
        normalized = re.sub(r'\s+', ' ', normalized)

        return normalized.strip()

    def _normalize_author(self, author: str) -> str:
        """Normalize author name for comparison."""
        # Convert to lowercase
        normalized = author.lower()

        # Remove common suffixes
        normalized = re.sub(r',?\s+(jr|sr|ii|iii|iv)\.?$', '', normalized)

        # Remove punctuation except spaces
        normalized = re.sub(r'[^\w\s]', ' ', normalized)
        normalized = re.sub(r'\s+', ' ', normalized)

        return normalized.strip()

    def _normalize_publisher(self, publisher: str) -> str:
        """Normalize publisher name for comparison."""
        normalized = publisher.lower()

        # Remove common suffixes
        normalized = re.sub(
            r'\s+(inc|corp|ltd|llc|press|publishers?|books?)\.?$',
            '',
            normalized
        )

        # Remove punctuation
        normalized = re.sub(r'[^\w\s]', ' ', normalized)
        normalized = re.sub(r'\s+', ' ', normalized)

        return normalized.strip()

    def _normalize_subject(self, subject: str) -> str:
        """Normalize subject heading for comparison."""
        normalized = subject.lower()

        # Remove trailing punctuation
        normalized = re.sub(r'[.\-,;:]+$', '', normalized)

        # Normalize spaces
        normalized = re.sub(r'\s+', ' ', normalized)

        return normalized.strip()
