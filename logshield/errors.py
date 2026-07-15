"""Exception hierarchy for LogShield-AI."""

from __future__ import annotations


class LogShieldError(Exception):
    """Base class for all LogShield errors."""


class ConfigError(LogShieldError):
    """Invalid configuration."""


class ParseError(LogShieldError):
    """Failed to parse a log line."""


class StorageError(LogShieldError):
    """Persistence failure."""


class StreamError(LogShieldError):
    """Streaming/queue transport failure."""
