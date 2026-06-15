"""Reverse image search on Wikimedia Commons.

Two public entry points:
  - `run_reverse(query)`  — async; returns `ReverseResponse` with ranked candidates
  - `normalize_url(url)`  — sync; returns canonical filename + URL forms, or None
"""
from .commons_normalize import normalize as normalize_url
from .models import (
    NormalizeResponse,
    ReverseCandidate,
    ReverseHint,
    ReverseQuery,
    ReverseResponse,
)
from .triangulate import run as run_reverse

__all__ = [
    "NormalizeResponse",
    "ReverseCandidate",
    "ReverseHint",
    "ReverseQuery",
    "ReverseResponse",
    "normalize_url",
    "run_reverse",
]
