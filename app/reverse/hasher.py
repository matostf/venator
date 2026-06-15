"""Perceptual hashing for reverse-by-image and dedup.

Wraps `imagehash` (pHash + dHash via Pillow). The two hash families are
complementary:
  - pHash (perceptual): robust against compression and minor color shifts
  - dHash (difference): robust against gamma/contrast changes

Functions in this module accept either a URL or raw bytes and return
`ImageHashes` (both pHash and dHash). Distance comparisons follow the
`imagehash` convention: number of differing bits in a 64-bit hash, lower
is more similar. A common rule of thumb:
  - 0           → identical or trivially re-encoded
  - 1-4         → near-duplicate (crop, slight color change)
  - 5-10        → similar (same subject, different reproduction)
  - ≥ 12        → unrelated

Hashes serialize to 16-char hex strings via `str(imagehash.ImageHash)`.
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Optional

import httpx
import imagehash
from PIL import Image

from ..sources.base import USER_AGENT


@dataclass(frozen=True)
class ImageHashes:
    phash: str          # perceptual hash (hex)
    dhash: str          # difference hash (hex)
    width: int
    height: int

    def to_dict(self) -> dict:
        return {"phash": self.phash, "dhash": self.dhash, "width": self.width, "height": self.height}


def _hashes_from_pil(img: Image.Image) -> ImageHashes:
    """Compute both hashes from an already-loaded PIL image."""
    # Convert to RGB to avoid mode-conversion warnings on RGBA/CMYK inputs.
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    p = imagehash.phash(img)
    d = imagehash.dhash(img)
    return ImageHashes(phash=str(p), dhash=str(d), width=img.width, height=img.height)


def hash_from_bytes(data: bytes) -> ImageHashes:
    """Hash an image already in memory."""
    with Image.open(io.BytesIO(data)) as img:
        img.load()
        return _hashes_from_pil(img)


def hash_from_path(path: str) -> ImageHashes:
    """Hash an image from a local file."""
    with Image.open(path) as img:
        img.load()
        return _hashes_from_pil(img)


async def hash_from_url(client: httpx.AsyncClient, url: str, *, timeout: float = 60.0) -> ImageHashes:
    """Download an image and hash it. Uses the shared `USER_AGENT`.

    Follows redirects — necessary because Commons `Special:FilePath` URLs
    redirect to `upload.wikimedia.org` (302).
    """
    resp = await client.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=timeout,
        follow_redirects=True,
    )
    resp.raise_for_status()
    return hash_from_bytes(resp.content)


def hash_distance(hash_a: str, hash_b: str) -> int:
    """Hamming distance between two hex-string hashes. Lower = more similar."""
    h1 = imagehash.hex_to_hash(hash_a)
    h2 = imagehash.hex_to_hash(hash_b)
    return h1 - h2


def is_likely_duplicate(
    candidate: ImageHashes,
    reference_phash: str,
    *,
    threshold: int = 6,
) -> bool:
    """Tight default (6 bits) — false-positive rate is low for distinct works
    but catches re-uploads, crops, and re-encodings of the same artwork."""
    return hash_distance(candidate.phash, reference_phash) <= threshold


def closest_in_manifest(
    candidate: ImageHashes,
    manifest_hashes: list[dict],
    *,
    use_dhash_fallback: bool = True,
) -> Optional[dict]:
    """Find the manifest entry whose hash is closest to `candidate`.

    Args:
        candidate: hashes of the query image.
        manifest_hashes: list of {"id": ..., "phash": ..., "dhash": ...} entries.
        use_dhash_fallback: if pHash tied between multiple entries, break tie by dHash.

    Returns:
        Best-match entry with extra `"distance"` (pHash) and `"distance_dhash"` keys,
        or None if the manifest is empty.
    """
    if not manifest_hashes:
        return None

    scored = []
    for entry in manifest_hashes:
        ph = entry.get("phash")
        if not ph:
            continue
        d_phash = hash_distance(candidate.phash, ph)
        d_dhash = hash_distance(candidate.dhash, entry.get("dhash", ph)) if use_dhash_fallback else 999
        scored.append((d_phash, d_dhash, entry))

    if not scored:
        return None

    scored.sort(key=lambda x: (x[0], x[1]))
    d_p, d_d, best = scored[0]
    out = dict(best)
    out["distance"] = d_p
    out["distance_dhash"] = d_d
    return out
