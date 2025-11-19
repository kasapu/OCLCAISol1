"""
WorldCat API Client.

This module provides a client for querying the WorldCat database
with intelligent caching, rate limiting, and multiple search strategies.
"""

import time
import hashlib
import json
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from enum import Enum
import redis
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ..utils.logging import get_logger
from ..utils.config import get_settings


logger = get_logger(__name__)


class SearchStrategy(Enum):
    """Available search strategies for WorldCat."""
    ISBN = "isbn"
    ISSN = "issn"
    OCLC_NUMBER = "oclc_number"
    TITLE_AUTHOR = "title_author"
    ADVANCED = "advanced"


class RateLimiter:
    """Simple rate limiter using token bucket algorithm."""

    def __init__(self, max_calls: int, period: int):
        """
        Initialize rate limiter.

        Args:
            max_calls: Maximum number of calls allowed
            period: Time period in seconds
        """
        self.max_calls = max_calls
        self.period = period
        self.calls = []

    def wait_if_needed(self) -> None:
        """Wait if rate limit would be exceeded."""
        now = time.time()

        # Remove calls outside the current period
        self.calls = [call_time for call_time in self.calls
                      if now - call_time < self.period]

        if len(self.calls) >= self.max_calls:
            # Need to wait
            sleep_time = self.period - (now - self.calls[0])
            if sleep_time > 0:
                logger.info(
                    "rate_limit_wait",
                    sleep_time=sleep_time,
                    max_calls=self.max_calls,
                    period=self.period
                )
                time.sleep(sleep_time)

            # Clean up old calls after waiting
            now = time.time()
            self.calls = [call_time for call_time in self.calls
                          if now - call_time < self.period]

        # Record this call
        self.calls.append(time.time())


class WorldCatCache:
    """Redis-based cache for WorldCat API responses."""

    def __init__(self, redis_client: redis.Redis, ttl: int = 3600):
        """
        Initialize cache.

        Args:
            redis_client: Redis client instance
            ttl: Time-to-live for cache entries in seconds
        """
        self.redis = redis_client
        self.ttl = ttl
        self.logger = get_logger(__name__)

    def _make_key(self, query_type: str, query_params: Dict[str, Any]) -> str:
        """
        Generate cache key from query parameters.

        Args:
            query_type: Type of query
            query_params: Query parameters

        Returns:
            Cache key string
        """
        # Sort params for consistent hashing
        param_str = json.dumps(query_params, sort_keys=True)
        hash_obj = hashlib.sha256(f"{query_type}:{param_str}".encode())
        return f"worldcat:{hash_obj.hexdigest()}"

    def get(self, query_type: str, query_params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Get cached response.

        Args:
            query_type: Type of query
            query_params: Query parameters

        Returns:
            Cached response or None
        """
        try:
            key = self._make_key(query_type, query_params)
            cached = self.redis.get(key)

            if cached:
                self.logger.debug("cache_hit", query_type=query_type)
                return json.loads(cached)

            self.logger.debug("cache_miss", query_type=query_type)
            return None

        except Exception as e:
            self.logger.warning("cache_get_error", error=str(e))
            return None

    def set(self, query_type: str, query_params: Dict[str, Any], response: Dict[str, Any]) -> None:
        """
        Cache a response.

        Args:
            query_type: Type of query
            query_params: Query parameters
            response: Response to cache
        """
        try:
            key = self._make_key(query_type, query_params)
            self.redis.setex(
                key,
                self.ttl,
                json.dumps(response)
            )
            self.logger.debug("cache_set", query_type=query_type)

        except Exception as e:
            self.logger.warning("cache_set_error", error=str(e))

    def clear(self) -> None:
        """Clear all WorldCat cache entries."""
        try:
            # Find all worldcat keys
            keys = self.redis.keys("worldcat:*")
            if keys:
                self.redis.delete(*keys)
                self.logger.info("cache_cleared", keys_deleted=len(keys))
        except Exception as e:
            self.logger.warning("cache_clear_error", error=str(e))


class WorldCatClient:
    """Client for WorldCat Search API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        base_url: Optional[str] = None,
        redis_client: Optional[redis.Redis] = None
    ):
        """
        Initialize WorldCat client.

        Args:
            api_key: WorldCat API key (defaults to config)
            api_secret: WorldCat API secret (defaults to config)
            base_url: Base URL for API (defaults to config)
            redis_client: Redis client for caching (creates new if None)
        """
        settings = get_settings()

        self.api_key = api_key or settings.worldcat_api_key
        self.api_secret = api_secret or settings.worldcat_api_secret
        self.base_url = base_url or settings.worldcat_base_url

        # Initialize Redis for caching
        if redis_client is None:
            redis_client = redis.from_url(settings.redis_url)
        self.cache = WorldCatCache(redis_client, ttl=settings.redis_cache_ttl)

        # Initialize rate limiter
        self.rate_limiter = RateLimiter(
            max_calls=settings.worldcat_rate_limit,
            period=settings.worldcat_rate_period
        )

        # Initialize HTTP session with retry logic
        self.session = self._create_session()

        self.logger = get_logger(__name__)

    def _create_session(self) -> requests.Session:
        """
        Create requests session with retry logic.

        Returns:
            Configured requests Session
        """
        session = requests.Session()

        # Configure retries
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"]
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        return session

    def _make_request(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        use_cache: bool = True
    ) -> Dict[str, Any]:
        """
        Make API request with rate limiting and caching.

        Args:
            endpoint: API endpoint
            params: Query parameters
            use_cache: Whether to use caching

        Returns:
            API response

        Raises:
            requests.RequestException: On API errors
        """
        params = params or {}

        # Check cache first
        if use_cache:
            cached = self.cache.get(endpoint, params)
            if cached is not None:
                return cached

        # Apply rate limiting
        self.rate_limiter.wait_if_needed()

        # Make request
        url = f"{self.base_url}/{endpoint}"

        # Add authentication
        params["wskey"] = self.api_key

        try:
            self.logger.debug(
                "worldcat_api_request",
                endpoint=endpoint,
                params={k: v for k, v in params.items() if k != "wskey"}
            )

            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()

            result = response.json()

            # Cache successful response
            if use_cache:
                self.cache.set(endpoint, params, result)

            return result

        except requests.RequestException as e:
            self.logger.error(
                "worldcat_api_error",
                endpoint=endpoint,
                error=str(e)
            )
            raise

    def search_by_isbn(self, isbn: str) -> List[Dict[str, Any]]:
        """
        Search WorldCat by ISBN.

        Args:
            isbn: ISBN to search for

        Returns:
            List of matching records
        """
        try:
            # Clean ISBN
            isbn = isbn.replace("-", "").replace(" ", "").strip()

            result = self._make_request(
                "search",
                params={"query": f"isbn:{isbn}", "limit": 10}
            )

            records = self._parse_search_results(result)

            self.logger.info(
                "isbn_search_completed",
                isbn=isbn,
                results_found=len(records)
            )

            return records

        except Exception as e:
            self.logger.error("isbn_search_failed", isbn=isbn, error=str(e))
            return []

    def search_by_issn(self, issn: str) -> List[Dict[str, Any]]:
        """
        Search WorldCat by ISSN.

        Args:
            issn: ISSN to search for

        Returns:
            List of matching records
        """
        try:
            result = self._make_request(
                "search",
                params={"query": f"issn:{issn}", "limit": 10}
            )

            records = self._parse_search_results(result)

            self.logger.info(
                "issn_search_completed",
                issn=issn,
                results_found=len(records)
            )

            return records

        except Exception as e:
            self.logger.error("issn_search_failed", issn=issn, error=str(e))
            return []

    def search_by_oclc_number(self, oclc_number: str) -> Optional[Dict[str, Any]]:
        """
        Search WorldCat by OCLC control number.

        Args:
            oclc_number: OCLC number to search for

        Returns:
            Matching record or None
        """
        try:
            result = self._make_request(
                f"bib/data/{oclc_number}",
                params={}
            )

            self.logger.info(
                "oclc_number_search_completed",
                oclc_number=oclc_number,
                found=result is not None
            )

            return result

        except requests.HTTPError as e:
            if e.response.status_code == 404:
                self.logger.info(
                    "oclc_number_not_found",
                    oclc_number=oclc_number
                )
                return None
            raise

        except Exception as e:
            self.logger.error(
                "oclc_number_search_failed",
                oclc_number=oclc_number,
                error=str(e)
            )
            return None

    def search_by_title_author(
        self,
        title: str,
        author: Optional[str] = None,
        year: Optional[int] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Search WorldCat by title and author.

        Args:
            title: Title to search for
            author: Author name (optional)
            year: Publication year (optional)
            limit: Maximum number of results

        Returns:
            List of matching records
        """
        try:
            # Build query
            query_parts = [f'ti:"{title}"']

            if author:
                query_parts.append(f'au:"{author}"')

            if year:
                query_parts.append(f'yr:{year}')

            query = " AND ".join(query_parts)

            result = self._make_request(
                "search",
                params={"query": query, "limit": limit}
            )

            records = self._parse_search_results(result)

            self.logger.info(
                "title_author_search_completed",
                title=title,
                author=author,
                year=year,
                results_found=len(records)
            )

            return records

        except Exception as e:
            self.logger.error(
                "title_author_search_failed",
                title=title,
                author=author,
                error=str(e)
            )
            return []

    def advanced_search(
        self,
        query_params: Dict[str, Any],
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Perform advanced search with custom parameters.

        Args:
            query_params: Dictionary of search parameters
            limit: Maximum number of results

        Returns:
            List of matching records
        """
        try:
            # Build query string from params
            query_parts = []

            for field, value in query_params.items():
                if value:
                    query_parts.append(f'{field}:"{value}"')

            query = " AND ".join(query_parts)

            result = self._make_request(
                "search",
                params={"query": query, "limit": limit}
            )

            records = self._parse_search_results(result)

            self.logger.info(
                "advanced_search_completed",
                query_params=query_params,
                results_found=len(records)
            )

            return records

        except Exception as e:
            self.logger.error(
                "advanced_search_failed",
                query_params=query_params,
                error=str(e)
            )
            return []

    def _parse_search_results(self, response: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Parse search results from API response.

        Args:
            response: API response

        Returns:
            List of parsed records
        """
        records = []

        # The actual structure depends on WorldCat API response format
        # This is a simplified version
        if "entries" in response:
            for entry in response["entries"]:
                records.append(self._parse_entry(entry))
        elif "entry" in response:
            records.append(self._parse_entry(response["entry"]))

        return records

    def _parse_entry(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse a single entry from search results.

        Args:
            entry: Entry from API response

        Returns:
            Parsed record data
        """
        # Extract key fields from entry
        # This is a simplified version - actual implementation
        # would need to handle WorldCat's specific response format
        return {
            "oclc_number": entry.get("oclcNumber"),
            "title": entry.get("title"),
            "author": entry.get("creator"),
            "publisher": entry.get("publisher"),
            "year": entry.get("date"),
            "isbn": entry.get("isbn", []),
            "issn": entry.get("issn", []),
            "format": entry.get("format"),
            "language": entry.get("language"),
            "raw_data": entry
        }

    def batch_search(
        self,
        queries: List[Dict[str, Any]],
        strategy: SearchStrategy = SearchStrategy.ISBN
    ) -> List[Dict[str, Any]]:
        """
        Perform batch search for multiple queries.

        Args:
            queries: List of query dictionaries
            strategy: Search strategy to use

        Returns:
            List of results (one per query)
        """
        results = []

        for query in queries:
            if strategy == SearchStrategy.ISBN:
                result = self.search_by_isbn(query.get("isbn", ""))
            elif strategy == SearchStrategy.ISSN:
                result = self.search_by_issn(query.get("issn", ""))
            elif strategy == SearchStrategy.OCLC_NUMBER:
                result = self.search_by_oclc_number(query.get("oclc_number", ""))
            elif strategy == SearchStrategy.TITLE_AUTHOR:
                result = self.search_by_title_author(
                    title=query.get("title", ""),
                    author=query.get("author"),
                    year=query.get("year")
                )
            else:
                result = self.advanced_search(query)

            results.append({
                "query": query,
                "results": result
            })

        return results
