"""
Structured logging configuration for OCLC WMS Matcher.

This module sets up structured logging using structlog with JSON output
for production environments and human-readable output for development.
"""

import logging
import sys
from typing import Any, Dict
import structlog
from structlog.types import EventDict, Processor

from .config import get_settings


def add_app_context(logger: Any, method_name: str, event_dict: EventDict) -> EventDict:
    """Add application context to log entries."""
    settings = get_settings()
    event_dict["app_name"] = settings.app_name
    event_dict["app_version"] = settings.app_version
    event_dict["environment"] = settings.app_env
    return event_dict


def configure_logging() -> None:
    """Configure structured logging for the application."""
    settings = get_settings()

    # Determine log level
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )

    # Shared processors for all configurations
    shared_processors: list[Processor] = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        add_app_context,
    ]

    # Environment-specific configuration
    if settings.app_env == "development" or settings.debug:
        # Development: Human-readable console output
        processors = shared_processors + [
            structlog.dev.ConsoleRenderer(colors=True)
        ]
    else:
        # Production: JSON output
        processors = shared_processors + [
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer()
        ]

    # Configure structlog
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """
    Get a configured logger instance.

    Args:
        name: Logger name (typically __name__ of the module)

    Returns:
        Configured structlog logger
    """
    return structlog.get_logger(name)


class LoggerAdapter:
    """Adapter for adding context to logger instances."""

    def __init__(self, logger: structlog.stdlib.BoundLogger, **initial_context: Any):
        """
        Initialize logger adapter with context.

        Args:
            logger: Structlog logger instance
            **initial_context: Initial context to bind to logger
        """
        self.logger = logger.bind(**initial_context)

    def bind(self, **context: Any) -> "LoggerAdapter":
        """
        Create new logger adapter with additional context.

        Args:
            **context: Additional context to bind

        Returns:
            New LoggerAdapter with combined context
        """
        return LoggerAdapter(self.logger, **context)

    def debug(self, event: str, **kwargs: Any) -> None:
        """Log debug message."""
        self.logger.debug(event, **kwargs)

    def info(self, event: str, **kwargs: Any) -> None:
        """Log info message."""
        self.logger.info(event, **kwargs)

    def warning(self, event: str, **kwargs: Any) -> None:
        """Log warning message."""
        self.logger.warning(event, **kwargs)

    def error(self, event: str, **kwargs: Any) -> None:
        """Log error message."""
        self.logger.error(event, **kwargs)

    def exception(self, event: str, **kwargs: Any) -> None:
        """Log exception with traceback."""
        self.logger.exception(event, **kwargs)

    def critical(self, event: str, **kwargs: Any) -> None:
        """Log critical message."""
        self.logger.critical(event, **kwargs)


# Initialize logging on module import
configure_logging()
