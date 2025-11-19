"""
MARC Record Parser and Analyzer.

This module provides functionality to parse MARC21 bibliographic records
from various formats (binary, XML, JSON) and analyze their completeness.
"""

import json
from typing import Dict, List, Optional, Union, Any
from pathlib import Path
from enum import Enum
import chardet
from pymarc import MARCReader, Record, Field
from pymarc.exceptions import RecordLengthInvalid, RecordLeaderInvalid
import xml.etree.ElementTree as ET

from ..utils.logging import get_logger


logger = get_logger(__name__)


class MARCFormat(Enum):
    """Supported MARC formats."""
    BINARY = "binary"
    XML = "xml"
    JSON = "json"


class FieldImportance(Enum):
    """Field importance levels for completeness scoring."""
    CRITICAL = 10  # Control numbers, identifiers
    HIGH = 7       # Title, author, publication
    MEDIUM = 5     # Classification, subjects
    LOW = 3        # Notes, physical description
    OPTIONAL = 1   # Local fields


# Field weights for completeness scoring
FIELD_WEIGHTS = {
    # Control fields
    "001": FieldImportance.CRITICAL,
    "003": FieldImportance.MEDIUM,
    "005": FieldImportance.LOW,
    "008": FieldImportance.HIGH,

    # ISBN/ISSN
    "020": FieldImportance.CRITICAL,  # ISBN
    "022": FieldImportance.CRITICAL,  # ISSN

    # Authors
    "100": FieldImportance.HIGH,      # Main author
    "110": FieldImportance.HIGH,      # Corporate author
    "111": FieldImportance.HIGH,      # Meeting name
    "700": FieldImportance.MEDIUM,    # Added author
    "710": FieldImportance.MEDIUM,    # Corporate added entry

    # Title
    "245": FieldImportance.CRITICAL,  # Title statement
    "246": FieldImportance.LOW,       # Varying form of title

    # Edition, Publication
    "250": FieldImportance.MEDIUM,    # Edition
    "260": FieldImportance.HIGH,      # Publication (pre-RDA)
    "264": FieldImportance.HIGH,      # Publication (RDA)

    # Physical description
    "300": FieldImportance.LOW,       # Physical description

    # Series
    "490": FieldImportance.MEDIUM,    # Series statement

    # Notes
    "500": FieldImportance.LOW,       # General note
    "504": FieldImportance.LOW,       # Bibliography note
    "505": FieldImportance.LOW,       # Contents note

    # Subject headings
    "600": FieldImportance.MEDIUM,    # Subject - personal name
    "610": FieldImportance.MEDIUM,    # Subject - corporate
    "650": FieldImportance.MEDIUM,    # Subject - topical
    "651": FieldImportance.MEDIUM,    # Subject - geographic

    # Classification
    "050": FieldImportance.MEDIUM,    # LC Classification
    "082": FieldImportance.MEDIUM,    # Dewey Classification
}


class MARCRecord:
    """
    Wrapper class for MARC records with analysis capabilities.
    """

    def __init__(self, record: Record):
        """
        Initialize MARCRecord.

        Args:
            record: pymarc Record object
        """
        self.record = record
        self._completeness_score: Optional[float] = None
        self._field_analysis: Optional[Dict[str, Any]] = None

    @property
    def control_number(self) -> Optional[str]:
        """Get the control number (001 field)."""
        field_001 = self.record.get_fields("001")
        return str(field_001[0].data) if field_001 else None

    @property
    def isbn(self) -> List[str]:
        """Get all ISBNs from 020 field."""
        isbns = []
        for field in self.record.get_fields("020"):
            if field.get_subfields("a"):
                isbn = field.get_subfields("a")[0]
                # Clean ISBN (remove hyphens and qualifiers)
                isbn = isbn.split("(")[0].replace("-", "").strip()
                if isbn:
                    isbns.append(isbn)
        return isbns

    @property
    def issn(self) -> List[str]:
        """Get all ISSNs from 022 field."""
        issns = []
        for field in self.record.get_fields("022"):
            if field.get_subfields("a"):
                issn = field.get_subfields("a")[0].strip()
                if issn:
                    issns.append(issn)
        return issns

    @property
    def title(self) -> Optional[str]:
        """Get the main title from 245 field."""
        field_245 = self.record.get_fields("245")
        if not field_245:
            return None

        title_parts = []
        field = field_245[0]

        # Subfield 'a' is the main title
        if field.get_subfields("a"):
            title_parts.append(field.get_subfields("a")[0])

        # Subfield 'b' is the subtitle
        if field.get_subfields("b"):
            title_parts.append(field.get_subfields("b")[0])

        return " ".join(title_parts).strip(" /,.:;")

    @property
    def authors(self) -> List[str]:
        """Get all author names."""
        authors = []

        # Main entry - personal name (100)
        for field in self.record.get_fields("100"):
            if field.get_subfields("a"):
                authors.append(field.get_subfields("a")[0].strip(" ,.:;"))

        # Main entry - corporate name (110)
        for field in self.record.get_fields("110"):
            if field.get_subfields("a"):
                authors.append(field.get_subfields("a")[0].strip(" ,.:;"))

        # Added entries (700, 710)
        for tag in ["700", "710"]:
            for field in self.record.get_fields(tag):
                if field.get_subfields("a"):
                    authors.append(field.get_subfields("a")[0].strip(" ,.:;"))

        return authors

    @property
    def publication_year(self) -> Optional[int]:
        """Extract publication year from 260/264 fields or 008."""
        # Try 260 field first (pre-RDA)
        for field in self.record.get_fields("260"):
            if field.get_subfields("c"):
                date_str = field.get_subfields("c")[0]
                year = self._extract_year(date_str)
                if year:
                    return year

        # Try 264 field (RDA)
        for field in self.record.get_fields("264"):
            if field.get_subfields("c"):
                date_str = field.get_subfields("c")[0]
                year = self._extract_year(date_str)
                if year:
                    return year

        # Fall back to 008 field
        field_008 = self.record.get_fields("008")
        if field_008:
            control_field = str(field_008[0].data)
            if len(control_field) >= 11:
                year_str = control_field[7:11]
                try:
                    year = int(year_str)
                    if 1000 <= year <= 2100:
                        return year
                except ValueError:
                    pass

        return None

    @property
    def publisher(self) -> Optional[str]:
        """Get publisher name from 260/264 fields."""
        # Try 260 field
        for field in self.record.get_fields("260"):
            if field.get_subfields("b"):
                return field.get_subfields("b")[0].strip(" ,.:;")

        # Try 264 field
        for field in self.record.get_fields("264"):
            if field.get_subfields("b"):
                return field.get_subfields("b")[0].strip(" ,.:;")

        return None

    @property
    def classification_lc(self) -> Optional[str]:
        """Get Library of Congress classification from 050 field."""
        field_050 = self.record.get_fields("050")
        if field_050 and field_050[0].get_subfields("a"):
            return field_050[0].get_subfields("a")[0].strip()
        return None

    @property
    def classification_dewey(self) -> Optional[str]:
        """Get Dewey Decimal classification from 082 field."""
        field_082 = self.record.get_fields("082")
        if field_082 and field_082[0].get_subfields("a"):
            return field_082[0].get_subfields("a")[0].strip()
        return None

    @property
    def subject_headings(self) -> List[str]:
        """Get all subject headings from 6XX fields."""
        subjects = []

        for tag in ["600", "610", "650", "651"]:
            for field in self.record.get_fields(tag):
                if field.get_subfields("a"):
                    subjects.append(field.get_subfields("a")[0].strip(" ,.:;"))

        return subjects

    def _extract_year(self, date_str: str) -> Optional[int]:
        """
        Extract a 4-digit year from a date string.

        Args:
            date_str: Date string that may contain a year

        Returns:
            Extracted year or None
        """
        import re

        # Look for 4-digit year
        year_match = re.search(r'\b(1[0-9]{3}|20[0-9]{2})\b', date_str)
        if year_match:
            return int(year_match.group(1))

        return None

    def analyze_completeness(self) -> Dict[str, Any]:
        """
        Analyze record completeness and calculate quality score.

        Returns:
            Dictionary containing:
                - score: Completeness score (0-100)
                - is_dark_record: Whether record is considered "dark" (sparse)
                - missing_critical: List of missing critical fields
                - present_fields: List of present field tags
                - field_counts: Count of fields by importance level
        """
        if self._field_analysis is not None:
            return self._field_analysis

        present_fields = []
        missing_critical = []
        field_counts = {level: 0 for level in FieldImportance}
        total_weight = 0
        achieved_weight = 0

        # Analyze field presence
        for tag, importance in FIELD_WEIGHTS.items():
            total_weight += importance.value

            fields = self.record.get_fields(tag)
            if fields:
                present_fields.append(tag)
                field_counts[importance] += 1
                achieved_weight += importance.value
            elif importance == FieldImportance.CRITICAL:
                missing_critical.append(tag)

        # Calculate score (0-100)
        score = (achieved_weight / total_weight * 100) if total_weight > 0 else 0

        # Determine if this is a "dark record"
        from ..utils.config import get_settings
        settings = get_settings()
        is_dark_record = score < settings.dark_record_threshold

        self._field_analysis = {
            "score": round(score, 2),
            "is_dark_record": is_dark_record,
            "missing_critical": missing_critical,
            "present_fields": present_fields,
            "field_counts": {
                level.name: count for level, count in field_counts.items()
            },
            "total_fields": len(present_fields)
        }

        return self._field_analysis

    @property
    def completeness_score(self) -> float:
        """Get the completeness score (0-100)."""
        if self._completeness_score is None:
            analysis = self.analyze_completeness()
            self._completeness_score = analysis["score"]
        return self._completeness_score

    @property
    def is_dark_record(self) -> bool:
        """Check if this is a dark record (sparse, low completeness)."""
        analysis = self.analyze_completeness()
        return analysis["is_dark_record"]

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert record to dictionary representation.

        Returns:
            Dictionary with all extracted fields and metadata
        """
        return {
            "control_number": self.control_number,
            "isbn": self.isbn,
            "issn": self.issn,
            "title": self.title,
            "authors": self.authors,
            "publication_year": self.publication_year,
            "publisher": self.publisher,
            "classification_lc": self.classification_lc,
            "classification_dewey": self.classification_dewey,
            "subject_headings": self.subject_headings,
            "completeness": self.analyze_completeness(),
            "leader": self.record.leader if self.record.leader else None
        }

    def __repr__(self) -> str:
        """String representation of the record."""
        return (
            f"MARCRecord(control_number={self.control_number}, "
            f"title={self.title[:50] if self.title else None}..., "
            f"completeness={self.completeness_score:.1f})"
        )


class MARCParser:
    """Parser for MARC records in various formats."""

    def __init__(self):
        """Initialize the MARC parser."""
        self.logger = get_logger(__name__)

    def parse_file(
        self,
        file_path: Union[str, Path],
        format: Optional[MARCFormat] = None
    ) -> List[MARCRecord]:
        """
        Parse MARC records from a file.

        Args:
            file_path: Path to the MARC file
            format: MARC format (auto-detected if None)

        Returns:
            List of MARCRecord objects
        """
        file_path = Path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Auto-detect format if not specified
        if format is None:
            format = self._detect_format(file_path)

        self.logger.info(
            "parsing_marc_file",
            file_path=str(file_path),
            format=format.value
        )

        if format == MARCFormat.BINARY:
            return self._parse_binary(file_path)
        elif format == MARCFormat.XML:
            return self._parse_xml(file_path)
        elif format == MARCFormat.JSON:
            return self._parse_json(file_path)
        else:
            raise ValueError(f"Unsupported format: {format}")

    def _detect_format(self, file_path: Path) -> MARCFormat:
        """
        Auto-detect MARC file format.

        Args:
            file_path: Path to the file

        Returns:
            Detected MARCFormat
        """
        suffix = file_path.suffix.lower()

        if suffix in [".mrc", ".marc"]:
            return MARCFormat.BINARY
        elif suffix in [".xml", ".marcxml"]:
            return MARCFormat.XML
        elif suffix == ".json":
            return MARCFormat.JSON

        # Try to detect by content
        with open(file_path, "rb") as f:
            first_bytes = f.read(100)

        # Check for XML
        if first_bytes.strip().startswith(b"<?xml") or b"<record" in first_bytes:
            return MARCFormat.XML

        # Check for JSON
        if first_bytes.strip().startswith(b"{") or first_bytes.strip().startswith(b"["):
            return MARCFormat.JSON

        # Default to binary
        return MARCFormat.BINARY

    def _parse_binary(self, file_path: Path) -> List[MARCRecord]:
        """Parse binary MARC file."""
        records = []
        errors = 0

        # Detect encoding
        with open(file_path, "rb") as f:
            raw_data = f.read()

        encoding_result = chardet.detect(raw_data)
        encoding = encoding_result.get("encoding", "utf-8")

        try:
            with open(file_path, "rb") as f:
                reader = MARCReader(f, to_unicode=True, utf8_handling="ignore")

                for record in reader:
                    if record is None:
                        errors += 1
                        self.logger.warning(
                            "skipped_invalid_record",
                            file_path=str(file_path)
                        )
                        continue

                    records.append(MARCRecord(record))

        except Exception as e:
            self.logger.error(
                "error_parsing_binary_marc",
                file_path=str(file_path),
                error=str(e)
            )
            raise

        self.logger.info(
            "parsed_marc_file",
            file_path=str(file_path),
            records_parsed=len(records),
            errors=errors
        )

        return records

    def _parse_xml(self, file_path: Path) -> List[MARCRecord]:
        """Parse MARCXML file."""
        from pymarc import marcxml

        records = []

        try:
            with open(file_path, "rb") as f:
                marc_records = marcxml.parse_xml_to_array(f)

                for record in marc_records:
                    records.append(MARCRecord(record))

        except Exception as e:
            self.logger.error(
                "error_parsing_xml_marc",
                file_path=str(file_path),
                error=str(e)
            )
            raise

        self.logger.info(
            "parsed_marc_xml",
            file_path=str(file_path),
            records_parsed=len(records)
        )

        return records

    def _parse_json(self, file_path: Path) -> List[MARCRecord]:
        """Parse MARC JSON file."""
        records = []

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Handle both array and single object
            if isinstance(data, list):
                marc_dicts = data
            else:
                marc_dicts = [data]

            for marc_dict in marc_dicts:
                record = self._dict_to_record(marc_dict)
                if record:
                    records.append(MARCRecord(record))

        except Exception as e:
            self.logger.error(
                "error_parsing_json_marc",
                file_path=str(file_path),
                error=str(e)
            )
            raise

        self.logger.info(
            "parsed_marc_json",
            file_path=str(file_path),
            records_parsed=len(records)
        )

        return records

    def _dict_to_record(self, marc_dict: Dict[str, Any]) -> Optional[Record]:
        """
        Convert dictionary to pymarc Record.

        Args:
            marc_dict: Dictionary representation of MARC record

        Returns:
            pymarc Record object or None
        """
        try:
            from pymarc import Record, Field

            record = Record()

            # Set leader
            if "leader" in marc_dict:
                record.leader = marc_dict["leader"]

            # Process fields
            fields = marc_dict.get("fields", {})

            for tag, field_data in fields.items():
                if isinstance(field_data, str):
                    # Control field
                    record.add_field(Field(tag=tag, data=field_data))
                elif isinstance(field_data, dict):
                    # Data field
                    ind1 = field_data.get("ind1", " ")
                    ind2 = field_data.get("ind2", " ")
                    subfields = field_data.get("subfields", {})

                    # Convert subfields dict to list format
                    subfield_list = []
                    for code, value in subfields.items():
                        subfield_list.extend([code, value])

                    record.add_field(
                        Field(
                            tag=tag,
                            indicators=[ind1, ind2],
                            subfields=subfield_list
                        )
                    )

            return record

        except Exception as e:
            self.logger.error("error_converting_dict_to_record", error=str(e))
            return None
