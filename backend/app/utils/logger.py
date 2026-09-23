"""Centralized logging configuration for CodeAtlas AI.

This module configures a single, shared logging setup used across the
entire backend. Every module should obtain its logger via `get_logger`
rather than configuring `logging` independently, ensuring consistent
formatting, log levels, and output destinations throughout the
application.
"""

import logging
import sys
from pathlib import Path

from app.config import get_settings

_LOG_FORMAT = (
    "%(asctime)s | %(levelname)s | %(name)s | %(funcName)s:%(lineno)d | %(message)s"
)
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Tracks whether the root application logger has already been configured,
# preventing duplicate handlers on repeated get_logger() calls.
_is_configured = False


def _create_console_handler(level: int) -> logging.Handler:
    """Build a console handler that writes formatted records to stdout."""
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))
    return handler


def _create_file_handler(log_file: Path, level: int) -> logging.Handler | None:
    """Build a UTF-8 file handler, returning None if it cannot be created.

    Ensures the parent directory exists before opening the log file. Any
    failure to create the directory or open the file is treated as
    non-fatal: the caller falls back to console-only logging instead of
    crashing the application.
    """
    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(log_file, encoding="utf-8")
        handler.setLevel(level)
        handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))
        return handler
    except OSError:
        return None


def _configure_root_logger() -> None:
    """Configure the shared application logger exactly once per process.

    Reads `LOG_LEVEL` and `LOG_FILE` from the application settings and
    attaches a console handler plus, when possible, a file handler to the
    `codeatlas` root logger. Safe to call multiple times; configuration
    is only applied on the first invocation.
    """
    global _is_configured
    if _is_configured:
        return

    settings = get_settings()
    level = logging.getLevelName(settings.LOG_LEVEL)

    root_logger = logging.getLogger("codeatlas")
    root_logger.setLevel(level)
    root_logger.propagate = False

    root_logger.addHandler(_create_console_handler(level))

    file_handler = _create_file_handler(settings.LOG_FILE, level)
    if file_handler is not None:
        root_logger.addHandler(file_handler)
    else:
        root_logger.warning(
            "Unable to open log file at %s; continuing with console logging only.",
            settings.LOG_FILE,
        )

    _is_configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a configured logger namespaced under the shared application logger.

    Args:
        name: Typically the caller's `__name__`, used to identify the
            source module in log output.

    Returns:
        A `logging.Logger` instance that writes to both console and file
        (when available), using the application's shared configuration.
    """
    _configure_root_logger()
    return logging.getLogger(f"codeatlas.{name}")