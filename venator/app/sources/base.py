"""Shared types and helpers for image sources."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class ImageResult:
    """A single image result, normalized across every source."""

    id: str                      # globally unique id, e.g. "met:436535"
    source: str                  # human-readable source name
    title: str
    thumbnail: str               # small/medium preview url
    full_image: str              # highest-resolution download url available
    source_url: str              # page on the source site (for context/credit)
    license: str                 # license/rights short name
    creator: Optional[str] = None
    width: Optional[int] = None  # pixel width of full image, if known
    height: Optional[int] = None # pixel height of full image, if known

    @property
    def attribution(self) -> str:
        """A ready-to-paste credit line for slides/handouts."""
        parts = [self.title or "Untitled"]
        if self.creator:
            parts.append(f"by {self.creator}")
        parts.append(f"— {self.source}")
        if self.license:
            parts.append(f"({self.license})")
        return " ".join(parts)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["attribution"] = self.attribution
        return d


# A shared, descriptive User-Agent. Several APIs (notably Wikimedia) require one.
# Wikimedia's User-Agent policy requires a descriptive agent with a real contact:
# https://foundation.wikimedia.org/wiki/Policy:Wikimedia_Foundation_User-Agent_Policy
USER_AGENT = (
    "venator/0.1 (open-licence image discovery for history teaching; "
    "https://github.com/matostf/venator; contact: matostf@gmail.com)"
)


class MissingKeyError(RuntimeError):
    """Raised by a source when its required API key is not configured.

    The search layer catches this and surfaces a friendly note instead of
    treating the source as an error.
    """
