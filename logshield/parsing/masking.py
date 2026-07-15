"""Structural variable masking.

Translates chaotic, unstructured log messages into uniform templates by replacing
volatile *parameters* (IPs, timestamps, UUIDs, hex ids, numbers, paths, URLs, …)
with typed placeholders, while extracting the concrete values by type. This is the
"structural regex extraction" layer: it turns

    2023-08-01T12:04:11Z connection to 10.0.4.7:8080 failed after 3 retries (err=0x1F)

into the template

    <TIMESTAMP> connection to <IP>:<PORT> failed after <NUM> retries (err=<HEX>)

plus ``{"IP": ["10.0.4.7"], "NUM": ["3"], "HEX": ["0x1F"], ...}``.

Ordering matters: more specific patterns are applied before more general ones so a
timestamp isn't shredded into individual numbers.
"""

from __future__ import annotations

import re

# Ordered list of (placeholder, compiled regex). Order = specificity, high first.
_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("TIMESTAMP", re.compile(r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?\b")),
    ("TIMESTAMP", re.compile(r"\b\d{2}:\d{2}:\d{2}(?:\.\d+)?\b")),
    ("UUID", re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")),
    ("MAC", re.compile(r"\b(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}\b")),
    ("URL", re.compile(r"\bhttps?://[^\s\"']+")),
    ("IP", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
    ("PATH", re.compile(r"(?:/[\w.\-]+){2,}/?")),
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("HEX", re.compile(r"\b0x[0-9a-fA-F]+\b")),
    ("HEX", re.compile(r"\b[0-9a-fA-F]{12,}\b")),          # long hex ids / hashes
    ("DURATION", re.compile(r"\b\d+(?:\.\d+)?(?:ms|s|us|ns|m|h)\b")),
    ("SIZE", re.compile(r"\b\d+(?:\.\d+)?(?:B|KB|MB|GB|TB|KiB|MiB|GiB)\b")),
    ("NUM", re.compile(r"\b\d+(?:\.\d+)?\b")),
]

# port after IP, e.g. <IP>:8080 -> <IP>:<PORT>
_PORT = re.compile(r"(<IP>):\d+\b")


def mask(line: str) -> str:
    t = line
    for placeholder, pat in _PATTERNS:
        t = pat.sub(f"<{placeholder}>", t)
    t = _PORT.sub(r"\1:<PORT>", t)
    # collapse redundant whitespace so templates are stable
    return re.sub(r"\s+", " ", t).strip()


def extract_variables(line: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    remaining = line
    for placeholder, pat in _PATTERNS:
        found = pat.findall(remaining)
        if found:
            # findall may return tuples for grouped patterns; normalise to str
            vals = [f if isinstance(f, str) else next((x for x in f if x), "") for f in found]
            out.setdefault(placeholder, []).extend(vals)
            remaining = pat.sub(" ", remaining)
    return out
