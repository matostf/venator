"""Dedup glue: hash a query image, compare against a manifest, return matches.

The "manifest" is a list of dicts with at least a `phash` field. Each project
keeps its own — `acervo-didatico-historia/MANIFESTO.json` is the canonical
example; other projects (slide decks, brand assets) can adopt the same
schema and reuse this module via the CLI / HTTP endpoint.

This module is intentionally thin: hashing logic lives in `hasher.py`, and
the public surface is just two coroutines for the two input shapes (URL or
local path).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import httpx

from .hasher import ImageHashes, closest_in_manifest, hash_from_path, hash_from_url


DEFAULT_THRESHOLD = 6


def _normalize_manifest(raw: Any) -> list[dict]:
    """Accept the manifest in several common shapes and flatten to a list of
    dicts each having at least `phash`. Returns empty list on bad input."""
    if isinstance(raw, list):
        return [e for e in raw if isinstance(e, dict) and e.get("phash")]
    if isinstance(raw, dict):
        # Common patterns: {"images": [...]} or {"items": [...]} or
        # {"slug1": {...}, "slug2": {...}}.
        for key in ("images", "items", "entries", "obras"):
            if isinstance(raw.get(key), list):
                return [e for e in raw[key] if isinstance(e, dict) and e.get("phash")]
        # Treat dict-of-dicts as a manifest where keys become an `id` field.
        out = []
        for k, v in raw.items():
            if isinstance(v, dict) and v.get("phash"):
                entry = dict(v)
                entry.setdefault("id", k)
                out.append(entry)
        return out
    return []


def load_manifest(manifest_path: str | Path) -> list[dict]:
    p = Path(manifest_path).expanduser().resolve()
    if not p.exists():
        raise FileNotFoundError(f"manifest not found: {p}")
    return _normalize_manifest(json.loads(p.read_text()))


def dedup_against(
    candidate: ImageHashes,
    manifest_entries: list[dict],
    *,
    threshold: int = DEFAULT_THRESHOLD,
) -> dict:
    """Compare candidate hash against the manifest. Returns a structured verdict.

    {
      "is_duplicate": bool,            ← distance ≤ threshold
      "threshold": int,
      "candidate_hashes": {phash, dhash, width, height},
      "best_match": {... entry ..., distance, distance_dhash} | None,
      "near_matches": [ ... top 3 with distance ≤ threshold + 4 ...],
    }
    """
    best = closest_in_manifest(candidate, manifest_entries)
    is_dup = bool(best and best.get("distance", 999) <= threshold)

    # Collect a few near-misses for human inspection.
    from .hasher import hash_distance

    scored = []
    for entry in manifest_entries:
        ph = entry.get("phash")
        if not ph:
            continue
        d = hash_distance(candidate.phash, ph)
        scored.append((d, entry))
    scored.sort(key=lambda x: x[0])
    near = [
        {**e, "distance": d}
        for d, e in scored[:5]
        if d <= threshold + 4
    ]

    return {
        "is_duplicate": is_dup,
        "threshold": threshold,
        "candidate_hashes": candidate.to_dict(),
        "best_match": best,
        "near_matches": near,
    }


async def dedup_url(
    url: str,
    manifest_entries: list[dict],
    *,
    threshold: int = DEFAULT_THRESHOLD,
    client: Optional[httpx.AsyncClient] = None,
) -> dict:
    own = client is None
    if own:
        client = httpx.AsyncClient()
    try:
        candidate = await hash_from_url(client, url)
        return dedup_against(candidate, manifest_entries, threshold=threshold)
    finally:
        if own:
            await client.aclose()


def dedup_path(
    path: str | Path,
    manifest_entries: list[dict],
    *,
    threshold: int = DEFAULT_THRESHOLD,
) -> dict:
    candidate = hash_from_path(str(path))
    return dedup_against(candidate, manifest_entries, threshold=threshold)
