"""Reverse image search on Wikimedia Commons.

Public entry points:
  - `run_reverse(query)`  — async; returns `ReverseResponse` with ranked candidates
  - `normalize_url(url)`  — sync; returns canonical filename + URL forms, or None
  - `hash_from_url` / `hash_from_path` / `hash_from_bytes` — perceptual hashing
  - `dedup_url` / `dedup_path` — compare image hash against a manifest
"""
from .commons_normalize import normalize as normalize_url
from .dedup import (
    DEFAULT_THRESHOLD,
    dedup_against,
    dedup_path,
    dedup_url,
    load_manifest,
)
from .hasher import (
    ImageHashes,
    hash_distance,
    hash_from_bytes,
    hash_from_path,
    hash_from_url,
    is_likely_duplicate,
)
from .models import (
    DedupRequest,
    HashRequest,
    NormalizeResponse,
    ReverseCandidate,
    ReverseHint,
    ReverseQuery,
    ReverseResponse,
)
from .triangulate import run as run_reverse

__all__ = [
    "DEFAULT_THRESHOLD",
    "DedupRequest",
    "HashRequest",
    "ImageHashes",
    "NormalizeResponse",
    "ReverseCandidate",
    "ReverseHint",
    "ReverseQuery",
    "ReverseResponse",
    "dedup_against",
    "dedup_path",
    "dedup_url",
    "hash_distance",
    "hash_from_bytes",
    "hash_from_path",
    "hash_from_url",
    "is_likely_duplicate",
    "load_manifest",
    "normalize_url",
    "run_reverse",
]
