"""Normalize any Wikimedia Commons URL to canonical forms.

Accepts:
  - commons.wikimedia.org/wiki/File:<name>
  - commons.wikimedia.org/wiki/Special:FilePath/<name>?...
  - upload.wikimedia.org/wikipedia/commons/<a>/<ab>/<name>
  - upload.wikimedia.org/wikipedia/commons/thumb/<a>/<ab>/<name>/<size>-<name>

Returns canonical filename + the three useful URL forms (page, file path, thumb).
"""
from __future__ import annotations

import re
import urllib.parse
from typing import Optional

# Order matters: file page first (most specific), then Special:FilePath, then upload paths.
_RE_FILE_PAGE = re.compile(r"commons\.wikimedia\.org/wiki/File:([^?#]+)")
_RE_FILEPATH = re.compile(r"commons\.wikimedia\.org/wiki/Special:FilePath/([^?#]+)")
_RE_UPLOAD_THUMB = re.compile(
    r"upload\.wikimedia\.org/wikipedia/commons/thumb/[^/]+/[^/]+/([^/?#]+)/[^?#]+"
)
_RE_UPLOAD_FILE = re.compile(r"upload\.wikimedia\.org/wikipedia/commons/[^/]+/[^/]+/([^?#]+)")


def extract_filename(url: str) -> Optional[str]:
    """Return the decoded Commons filename, or None if URL is not a Commons file URL."""
    if not url:
        return None
    for rx in (_RE_FILE_PAGE, _RE_FILEPATH, _RE_UPLOAD_THUMB, _RE_UPLOAD_FILE):
        m = rx.search(url)
        if m:
            return urllib.parse.unquote(m.group(1))
    return None


def file_page_url(filename: str) -> str:
    return "https://commons.wikimedia.org/wiki/File:" + urllib.parse.quote(filename, safe="()")


def file_path_url(filename: str) -> str:
    """`Special:FilePath` URL — Wikimedia redirects this to the actual file on upload.wikimedia.org."""
    return "https://commons.wikimedia.org/wiki/Special:FilePath/" + urllib.parse.quote(filename, safe="()")


def thumbnail_url(filename: str, width: int = 800) -> str:
    return f"{file_path_url(filename)}?width={width}"


def normalize(url: str, *, thumb_width: int = 800) -> Optional[dict]:
    fn = extract_filename(url)
    if not fn:
        return None
    return {
        "filename": fn,
        "file_page_url": file_page_url(fn),
        "upload_url": file_path_url(fn),
        "thumbnail_url": thumbnail_url(fn, width=thumb_width),
    }
