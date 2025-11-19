"""
Enrichment API Clients.

This module provides clients for various data enrichment sources:
- Open Library API
- Google Books API
- AI services (OpenAI/Anthropic)
"""

from typing import Dict, List, Optional, Any
import requests
from abc import ABC, abstractmethod
import openai
import anthropic

from ..utils.logging import get_logger
from ..utils.config import get_settings


logger = get_logger(__name__)


class EnrichmentClient(ABC):
    """Base class for enrichment clients."""

    @abstractmethod
    def enrich_by_isbn(self, isbn: str) -> Optional[Dict[str, Any]]:
        """Enrich record using ISBN."""
        pass

    @abstractmethod
    def enrich_by_title(self, title: str, author: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Enrich record using title and optional author."""
        pass


class OpenLibraryClient(EnrichmentClient):
    """Client for Open Library API."""

    def __init__(self, base_url: Optional[str] = None):
        """
        Initialize Open Library client.

        Args:
            base_url: Base URL for API (defaults to config)
        """
        settings = get_settings()
        self.base_url = base_url or settings.open_library_api_url
        self.session = requests.Session()
        self.logger = get_logger(__name__)

    def enrich_by_isbn(self, isbn: str) -> Optional[Dict[str, Any]]:
        """
        Enrich record using ISBN via Open Library.

        Args:
            isbn: ISBN to lookup

        Returns:
            Enriched data or None
        """
        try:
            # Clean ISBN
            isbn = isbn.replace("-", "").replace(" ", "").strip()

            url = f"https://openlibrary.org/api/books"
            params = {
                "bibkeys": f"ISBN:{isbn}",
                "format": "json",
                "jscmd": "data"
            }

            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()

            data = response.json()
            key = f"ISBN:{isbn}"

            if key in data:
                book_data = data[key]
                enriched = self._parse_open_library_response(book_data)

                self.logger.info(
                    "open_library_enrichment_success",
                    isbn=isbn,
                    title=enriched.get("title")
                )

                return enriched

            self.logger.info("open_library_no_data", isbn=isbn)
            return None

        except Exception as e:
            self.logger.error(
                "open_library_enrichment_failed",
                isbn=isbn,
                error=str(e)
            )
            return None

    def enrich_by_title(
        self,
        title: str,
        author: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Enrich record using title search via Open Library.

        Args:
            title: Book title
            author: Author name (optional)

        Returns:
            Enriched data or None
        """
        try:
            url = "https://openlibrary.org/search.json"
            params = {"title": title, "limit": 1}

            if author:
                params["author"] = author

            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()

            data = response.json()

            if data.get("docs") and len(data["docs"]) > 0:
                book_data = data["docs"][0]
                enriched = self._parse_search_response(book_data)

                self.logger.info(
                    "open_library_search_success",
                    title=title,
                    author=author
                )

                return enriched

            self.logger.info("open_library_search_no_results", title=title)
            return None

        except Exception as e:
            self.logger.error(
                "open_library_search_failed",
                title=title,
                error=str(e)
            )
            return None

    def _parse_open_library_response(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse Open Library API response."""
        return {
            "title": data.get("title"),
            "authors": [author.get("name") for author in data.get("authors", [])],
            "publishers": [pub.get("name") for pub in data.get("publishers", [])],
            "publish_date": data.get("publish_date"),
            "isbn": data.get("identifiers", {}).get("isbn_13", []),
            "subjects": data.get("subjects", []),
            "cover_url": data.get("cover", {}).get("large"),
            "source": "open_library"
        }

    def _parse_search_response(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse Open Library search response."""
        return {
            "title": data.get("title"),
            "authors": data.get("author_name", []),
            "publishers": data.get("publisher", []),
            "publish_date": data.get("first_publish_year"),
            "isbn": data.get("isbn", []),
            "subjects": data.get("subject", []),
            "source": "open_library"
        }


class GoogleBooksClient(EnrichmentClient):
    """Client for Google Books API."""

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Google Books client.

        Args:
            api_key: Google Books API key (defaults to config)
        """
        settings = get_settings()
        self.api_key = api_key or settings.google_books_api_key
        self.base_url = "https://www.googleapis.com/books/v1"
        self.session = requests.Session()
        self.logger = get_logger(__name__)

    def enrich_by_isbn(self, isbn: str) -> Optional[Dict[str, Any]]:
        """
        Enrich record using ISBN via Google Books.

        Args:
            isbn: ISBN to lookup

        Returns:
            Enriched data or None
        """
        try:
            # Clean ISBN
            isbn = isbn.replace("-", "").replace(" ", "").strip()

            url = f"{self.base_url}/volumes"
            params = {"q": f"isbn:{isbn}"}

            if self.api_key:
                params["key"] = self.api_key

            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()

            data = response.json()

            if data.get("totalItems", 0) > 0:
                book_data = data["items"][0]["volumeInfo"]
                enriched = self._parse_google_books_response(book_data)

                self.logger.info(
                    "google_books_enrichment_success",
                    isbn=isbn,
                    title=enriched.get("title")
                )

                return enriched

            self.logger.info("google_books_no_data", isbn=isbn)
            return None

        except Exception as e:
            self.logger.error(
                "google_books_enrichment_failed",
                isbn=isbn,
                error=str(e)
            )
            return None

    def enrich_by_title(
        self,
        title: str,
        author: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Enrich record using title search via Google Books.

        Args:
            title: Book title
            author: Author name (optional)

        Returns:
            Enriched data or None
        """
        try:
            query = f"intitle:{title}"
            if author:
                query += f" inauthor:{author}"

            url = f"{self.base_url}/volumes"
            params = {"q": query, "maxResults": 1}

            if self.api_key:
                params["key"] = self.api_key

            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()

            data = response.json()

            if data.get("totalItems", 0) > 0:
                book_data = data["items"][0]["volumeInfo"]
                enriched = self._parse_google_books_response(book_data)

                self.logger.info(
                    "google_books_search_success",
                    title=title,
                    author=author
                )

                return enriched

            self.logger.info("google_books_search_no_results", title=title)
            return None

        except Exception as e:
            self.logger.error(
                "google_books_search_failed",
                title=title,
                error=str(e)
            )
            return None

    def _parse_google_books_response(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse Google Books API response."""
        # Extract ISBNs
        isbns = []
        for identifier in data.get("industryIdentifiers", []):
            if identifier.get("type") in ["ISBN_10", "ISBN_13"]:
                isbns.append(identifier.get("identifier"))

        return {
            "title": data.get("title"),
            "subtitle": data.get("subtitle"),
            "authors": data.get("authors", []),
            "publishers": [data.get("publisher")] if data.get("publisher") else [],
            "publish_date": data.get("publishedDate"),
            "isbn": isbns,
            "page_count": data.get("pageCount"),
            "categories": data.get("categories", []),
            "description": data.get("description"),
            "language": data.get("language"),
            "source": "google_books"
        }


class AIEnrichmentClient:
    """Client for AI-powered enrichment using LLMs."""

    def __init__(
        self,
        openai_api_key: Optional[str] = None,
        anthropic_api_key: Optional[str] = None
    ):
        """
        Initialize AI enrichment client.

        Args:
            openai_api_key: OpenAI API key (defaults to config)
            anthropic_api_key: Anthropic API key (defaults to config)
        """
        settings = get_settings()

        self.openai_api_key = openai_api_key or settings.openai_api_key
        self.anthropic_api_key = anthropic_api_key or settings.anthropic_api_key

        # Initialize clients
        if self.openai_api_key:
            openai.api_key = self.openai_api_key

        if self.anthropic_api_key:
            self.anthropic_client = anthropic.Anthropic(
                api_key=self.anthropic_api_key
            )

        self.logger = get_logger(__name__)

    def extract_metadata_from_partial_title(
        self,
        partial_title: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Extract metadata from partial or incomplete title using AI.

        Args:
            partial_title: Incomplete or partial title
            context: Additional context (author, year, etc.)

        Returns:
            Extracted metadata
        """
        try:
            prompt = self._build_extraction_prompt(partial_title, context)

            # Use OpenAI if available
            if self.openai_api_key:
                response = openai.ChatCompletion.create(
                    model="gpt-4",
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a librarian expert at extracting bibliographic metadata."
                        },
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.3,
                    max_tokens=500
                )

                result_text = response.choices[0].message.content

                self.logger.info(
                    "ai_extraction_success",
                    partial_title=partial_title,
                    provider="openai"
                )

                return self._parse_ai_response(result_text)

            # Fall back to Anthropic
            elif self.anthropic_api_key:
                message = self.anthropic_client.messages.create(
                    model="claude-3-sonnet-20240229",
                    max_tokens=500,
                    messages=[{"role": "user", "content": prompt}]
                )

                result_text = message.content[0].text

                self.logger.info(
                    "ai_extraction_success",
                    partial_title=partial_title,
                    provider="anthropic"
                )

                return self._parse_ai_response(result_text)

            else:
                self.logger.warning("no_ai_api_keys_configured")
                return {}

        except Exception as e:
            self.logger.error(
                "ai_extraction_failed",
                partial_title=partial_title,
                error=str(e)
            )
            return {}

    def generate_subject_headings(
        self,
        title: str,
        description: Optional[str] = None
    ) -> List[str]:
        """
        Generate subject headings based on title and description.

        Args:
            title: Book title
            description: Book description (optional)

        Returns:
            List of suggested subject headings
        """
        try:
            prompt = f"""
Generate appropriate Library of Congress subject headings for the following book:

Title: {title}
{f'Description: {description}' if description else ''}

Provide 3-5 subject headings in standard LC format.
Return only the subject headings, one per line.
"""

            if self.openai_api_key:
                response = openai.ChatCompletion.create(
                    model="gpt-4",
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a librarian expert at assigning Library of Congress subject headings."
                        },
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.3,
                    max_tokens=200
                )

                result_text = response.choices[0].message.content
                subjects = [s.strip() for s in result_text.split("\n") if s.strip()]

                self.logger.info(
                    "ai_subject_generation_success",
                    title=title,
                    subjects_count=len(subjects)
                )

                return subjects

            elif self.anthropic_api_key:
                message = self.anthropic_client.messages.create(
                    model="claude-3-sonnet-20240229",
                    max_tokens=200,
                    messages=[{"role": "user", "content": prompt}]
                )

                result_text = message.content[0].text
                subjects = [s.strip() for s in result_text.split("\n") if s.strip()]

                self.logger.info(
                    "ai_subject_generation_success",
                    title=title,
                    subjects_count=len(subjects)
                )

                return subjects

            return []

        except Exception as e:
            self.logger.error(
                "ai_subject_generation_failed",
                title=title,
                error=str(e)
            )
            return []

    def suggest_classification(
        self,
        title: str,
        subjects: List[str]
    ) -> Optional[str]:
        """
        Suggest classification number based on title and subjects.

        Args:
            title: Book title
            subjects: Subject headings

        Returns:
            Suggested classification number
        """
        try:
            subjects_str = ", ".join(subjects) if subjects else "None provided"

            prompt = f"""
Based on the following book information, suggest an appropriate Library of Congress classification number:

Title: {title}
Subjects: {subjects_str}

Provide only the classification number (e.g., "QA76.73.P98" or "PS3566.R68").
"""

            if self.openai_api_key:
                response = openai.ChatCompletion.create(
                    model="gpt-4",
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a librarian expert at Library of Congress classification."
                        },
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.2,
                    max_tokens=50
                )

                classification = response.choices[0].message.content.strip()

                self.logger.info(
                    "ai_classification_success",
                    title=title,
                    classification=classification
                )

                return classification

            elif self.anthropic_api_key:
                message = self.anthropic_client.messages.create(
                    model="claude-3-sonnet-20240229",
                    max_tokens=50,
                    messages=[{"role": "user", "content": prompt}]
                )

                classification = message.content[0].text.strip()

                self.logger.info(
                    "ai_classification_success",
                    title=title,
                    classification=classification
                )

                return classification

            return None

        except Exception as e:
            self.logger.error(
                "ai_classification_failed",
                title=title,
                error=str(e)
            )
            return None

    def _build_extraction_prompt(
        self,
        partial_title: str,
        context: Optional[Dict[str, Any]]
    ) -> str:
        """Build prompt for metadata extraction."""
        prompt = f"""
Extract and infer bibliographic metadata from the following incomplete information:

Title (partial): {partial_title}
"""

        if context:
            if context.get("author"):
                prompt += f"\nAuthor: {context['author']}"
            if context.get("year"):
                prompt += f"\nYear: {context['year']}"
            if context.get("publisher"):
                prompt += f"\nPublisher: {context['publisher']}"

        prompt += """

Please provide:
1. Complete title (if inferrable)
2. Subtitle (if present)
3. Edition (if mentioned)
4. Likely subject area

Format as JSON with keys: title, subtitle, edition, subject_area
"""

        return prompt

    def _parse_ai_response(self, response_text: str) -> Dict[str, Any]:
        """Parse AI response into structured data."""
        import json
        import re

        try:
            # Try to find JSON in the response
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())

            # Fall back to empty dict
            return {}

        except json.JSONDecodeError:
            self.logger.warning("failed_to_parse_ai_response", response=response_text)
            return {}
