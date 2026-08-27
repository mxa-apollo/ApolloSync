"""Central logging configuration for Apollo Sync.

Only :func:`get_logger` is public. Modules request their own named logger and
share one lazily configured handler stack managed by this module.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from threading import RLock

from .config import Config as _Config
from .utils import logs_directory

__all__ = ["get_logger"]

_LOGGER_NAMESPACE = "apollosync"
_LOG_FILE_NAME = "apollosync.log"
_MAX_LOG_BYTES = 1_024 * 1_024
_BACKUP_COUNT = 5
_HANDLER_MARKER = "_apollosync_handler"
_CONFIGURATION_LOCK = RLock()
_is_configured = False


def get_logger(name: str) -> logging.Logger:
    """Return a configured Apollo Sync logger for *name*.

    The first call configures a shared ``RotatingFileHandler`` at
    ``logs/apollosync.log`` using the log level in ``config.json``. If that
    configuration cannot be created, a UTF-8-safe console handler is used
    instead. Later calls reuse the existing configuration without adding
    duplicate handlers.

    Args:
        name: Usually the calling module's ``__name__`` value.

    Examples:
        >>> logger = get_logger(__name__)
        >>> logger.info("Watching playlists")

    Returns:
        A standard-library :class:`logging.Logger` scoped to Apollo Sync.
    """
    _configure_once()
    logger_name = name.strip() if isinstance(name, str) else "application"
    if not logger_name:
        logger_name = "application"
    return logging.getLogger(f"{_LOGGER_NAMESPACE}.{logger_name}")


def _configure_once() -> None:
    """Configure the shared application logger exactly once per process."""
    global _is_configured

    with _CONFIGURATION_LOCK:
        if _is_configured:
            return

        application_logger = logging.getLogger(_LOGGER_NAMESPACE)
        if _has_application_handler(application_logger):
            _is_configured = True
            return

        try:
            level = _Config.load().log_level
            handler = _create_file_handler()
        except Exception:
            # Logging must not prevent the application from starting. Avoid
            # reporting this failure through logging because it is unavailable.
            level = logging.INFO
            handler = _create_console_handler()

        handler.setFormatter(_create_formatter())
        setattr(handler, _HANDLER_MARKER, True)
        application_logger.setLevel(level)
        application_logger.addHandler(handler)
        application_logger.propagate = False
        _is_configured = True


def _create_file_handler() -> RotatingFileHandler:
    """Create the rotating UTF-8 application log file handler."""
    log_directory = logs_directory()
    log_directory.mkdir(parents=True, exist_ok=True)
    return RotatingFileHandler(
        log_directory / _LOG_FILE_NAME,
        maxBytes=_MAX_LOG_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
        errors="backslashreplace",
        delay=True,
    )


def _create_console_handler() -> logging.StreamHandler[object]:
    """Create the safe fallback handler used when file logging is unavailable."""
    return logging.StreamHandler(sys.stderr)


def _create_formatter() -> logging.Formatter:
    """Return the common timestamp, level, module, and message formatter."""
    return logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(module)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _has_application_handler(application_logger: logging.Logger) -> bool:
    """Return whether this process already configured the application logger."""
    return any(getattr(handler, _HANDLER_MARKER, False) for handler in application_logger.handlers)
