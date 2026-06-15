"""Pydantic models for reverse-search inputs/outputs."""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


SOURCE_STRATEGIES = ("direct", "multilingual", "subcategory_walk", "thematic_walk", "perceptual_hash")


class ReverseHint(BaseModel):
    author: Optional[str] = None
    period: Optional[str] = None
    region: Optional[str] = None


class ReverseQuery(BaseModel):
    description: str
    hints: ReverseHint = Field(default_factory=ReverseHint)
    max_results: int = 10


class ReverseCandidate(BaseModel):
    file_url: str
    thumbnail_url: str
    upload_url: str
    title: str
    author: Optional[str] = None
    license: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    source_strategy: str
    similarity_score: float = 0.0


class ReverseResponse(BaseModel):
    query: ReverseQuery
    candidates: List[ReverseCandidate]
    strategies_used: List[str] = Field(default_factory=list)


class NormalizeResponse(BaseModel):
    filename: str
    file_page_url: str
    upload_url: str
    thumbnail_url: str


class HashRequest(BaseModel):
    url: str


class DedupRequest(BaseModel):
    """Either pass `url` (server downloads + hashes) OR `phash` + `dhash` (caller
    pre-hashed). And either `manifest_path` (server reads JSON file) OR `manifest`
    (inline list of entries with `phash`)."""

    url: Optional[str] = None
    phash: Optional[str] = None
    dhash: Optional[str] = None
    manifest_path: Optional[str] = None
    manifest: Optional[List[dict]] = None
    threshold: int = 6
