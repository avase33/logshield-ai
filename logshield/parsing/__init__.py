"""Structural log parsing: masking + Drain-style templating."""

from .masking import mask, extract_variables
from .drain import DrainParser, ParseResult

__all__ = ["mask", "extract_variables", "DrainParser", "ParseResult"]
