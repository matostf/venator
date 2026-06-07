"""Local library storage: SQLite metadata + image files on disk.

Layout (all under the project's ``data/`` folder):
    data/library.db      SQLite database (metadata, tags, collections)
    data/images/<id>.*   full-resolution image files
    data/thumbs/<id>.*   small preview files

The database is the source of truth; ``file_path``/``thumb_path`` point at the
files on disk. Removing an image deletes both the row and the files.
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Iterable, Optional

# Where saved images and the database live. Defaults to a local ``data/`` folder,
# but can be pointed at a persistent volume in the cloud via the DATA_DIR env var
# (e.g. DATA_DIR=/data on Fly.io).
DATA_DIR = Path(os.environ.get("DATA_DIR") or (Path(__file__).resolve().parent.parent / "data"))
IMAGES_DIR = DATA_DIR / "images"
THUMBS_DIR = DATA_DIR / "thumbs"
DB_PATH = DATA_DIR / "library.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS images (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_ref      TEXT UNIQUE,          -- e.g. "met:436535", for dedup
    title           TEXT NOT NULL,
    source          TEXT,
    creator         TEXT,
    license         TEXT,
    attribution     TEXT,
    source_url      TEXT,
    full_image_url  TEXT,
    width           INTEGER,
    height          INTEGER,
    file_path       TEXT,
    thumb_path      TEXT,
    file_size       INTEGER,
    notes           TEXT,
    saved_at        TEXT                  -- ISO timestamp string
);

CREATE TABLE IF NOT EXISTS tags (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    name  TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS image_tags (
    image_id  INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
    tag_id    INTEGER NOT NULL REFERENCES tags(id)   ON DELETE CASCADE,
    PRIMARY KEY (image_id, tag_id)
);

CREATE TABLE IF NOT EXISTS collections (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT UNIQUE NOT NULL,
    description TEXT,
    created_at  TEXT
);

CREATE TABLE IF NOT EXISTS collection_images (
    collection_id  INTEGER NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    image_id       INTEGER NOT NULL REFERENCES images(id)      ON DELETE CASCADE,
    added_at       TEXT,
    PRIMARY KEY (collection_id, image_id)
);
"""


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    IMAGES_DIR.mkdir(exist_ok=True)
    THUMBS_DIR.mkdir(exist_ok=True)
    conn = get_conn()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


# --------------------------------------------------------------------------
# Tags
# --------------------------------------------------------------------------
def _get_or_create_tag(conn: sqlite3.Connection, name: str) -> int:
    name = name.strip()
    row = conn.execute("SELECT id FROM tags WHERE name = ?", (name,)).fetchone()
    if row:
        return row["id"]
    cur = conn.execute("INSERT INTO tags (name) VALUES (?)", (name,))
    return cur.lastrowid


def set_tags(image_id: int, tags: Iterable[str]) -> None:
    clean = [t.strip() for t in tags if t and t.strip()]
    conn = get_conn()
    try:
        conn.execute("DELETE FROM image_tags WHERE image_id = ?", (image_id,))
        for name in clean:
            tag_id = _get_or_create_tag(conn, name)
            conn.execute(
                "INSERT OR IGNORE INTO image_tags (image_id, tag_id) VALUES (?, ?)",
                (image_id, tag_id),
            )
        # Clean up tags that are no longer referenced by anything.
        conn.execute(
            "DELETE FROM tags WHERE id NOT IN (SELECT tag_id FROM image_tags)"
        )
        conn.commit()
    finally:
        conn.close()


def list_tags() -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            """
            SELECT t.name, COUNT(it.image_id) AS count
            FROM tags t
            LEFT JOIN image_tags it ON it.tag_id = t.id
            GROUP BY t.id
            ORDER BY t.name COLLATE NOCASE
            """
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# --------------------------------------------------------------------------
# Collections
# --------------------------------------------------------------------------
def create_collection(name: str, description: str = "", created_at: str = "") -> dict:
    conn = get_conn()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO collections (name, description, created_at) VALUES (?, ?, ?)",
            (name.strip(), description, created_at),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM collections WHERE name = ?", (name.strip(),)
        ).fetchone()
        return dict(row)
    finally:
        conn.close()


def list_collections() -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            """
            SELECT c.id, c.name, c.description, c.created_at,
                   COUNT(ci.image_id) AS count
            FROM collections c
            LEFT JOIN collection_images ci ON ci.collection_id = c.id
            GROUP BY c.id
            ORDER BY c.name COLLATE NOCASE
            """
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def delete_collection(collection_id: int) -> None:
    conn = get_conn()
    try:
        conn.execute("DELETE FROM collections WHERE id = ?", (collection_id,))
        conn.commit()
    finally:
        conn.close()


def add_to_collection(collection_id: int, image_id: int, added_at: str = "") -> None:
    conn = get_conn()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO collection_images (collection_id, image_id, added_at) VALUES (?, ?, ?)",
            (collection_id, image_id, added_at),
        )
        conn.commit()
    finally:
        conn.close()


def remove_from_collection(collection_id: int, image_id: int) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "DELETE FROM collection_images WHERE collection_id = ? AND image_id = ?",
            (collection_id, image_id),
        )
        conn.commit()
    finally:
        conn.close()


# --------------------------------------------------------------------------
# Images
# --------------------------------------------------------------------------
def _image_row_to_dict(conn: sqlite3.Connection, row: sqlite3.Row) -> dict:
    d = dict(row)
    tag_rows = conn.execute(
        """
        SELECT t.name FROM tags t
        JOIN image_tags it ON it.tag_id = t.id
        WHERE it.image_id = ?
        ORDER BY t.name COLLATE NOCASE
        """,
        (row["id"],),
    ).fetchall()
    d["tags"] = [r["name"] for r in tag_rows]
    coll_rows = conn.execute(
        """
        SELECT c.id, c.name FROM collections c
        JOIN collection_images ci ON ci.collection_id = c.id
        WHERE ci.image_id = ?
        ORDER BY c.name COLLATE NOCASE
        """,
        (row["id"],),
    ).fetchall()
    d["collections"] = [dict(r) for r in coll_rows]
    return d


def find_by_ref(source_ref: str) -> Optional[dict]:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM images WHERE source_ref = ?", (source_ref,)
        ).fetchone()
        return _image_row_to_dict(conn, row) if row else None
    finally:
        conn.close()


def get_image(image_id: int) -> Optional[dict]:
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM images WHERE id = ?", (image_id,)).fetchone()
        return _image_row_to_dict(conn, row) if row else None
    finally:
        conn.close()


def list_saved_refs() -> list[str]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT source_ref FROM images WHERE source_ref IS NOT NULL"
        ).fetchall()
        return [r["source_ref"] for r in rows]
    finally:
        conn.close()


def list_images(
    tag: Optional[str] = None,
    collection_id: Optional[int] = None,
    q: Optional[str] = None,
) -> list[dict]:
    conn = get_conn()
    try:
        where = []
        params: list = []
        joins = ""
        if tag:
            joins += (
                " JOIN image_tags fit ON fit.image_id = i.id"
                " JOIN tags ft ON ft.id = fit.tag_id AND ft.name = ?"
            )
            params.append(tag)
        if collection_id:
            joins += " JOIN collection_images fci ON fci.image_id = i.id AND fci.collection_id = ?"
            params.append(collection_id)
        if q:
            where.append("(i.title LIKE ? OR i.creator LIKE ? OR i.source LIKE ?)")
            like = f"%{q}%"
            params.extend([like, like, like])

        sql = f"SELECT i.* FROM images i{joins}"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY i.saved_at DESC, i.id DESC"

        rows = conn.execute(sql, params).fetchall()
        return [_image_row_to_dict(conn, r) for r in rows]
    finally:
        conn.close()


def save_image(
    meta: dict,
    full_bytes: bytes,
    full_ext: str,
    thumb_bytes: Optional[bytes],
    thumb_ext: Optional[str],
    tags: Iterable[str],
    collection_ids: Iterable[int],
    saved_at: str,
) -> dict:
    """Insert metadata, write files to disk, attach tags/collections.

    If an image with the same ``source_ref`` already exists, no new file is
    written — the existing row's tags/collections are augmented instead.
    """
    source_ref = meta.get("id")

    conn = get_conn()
    try:
        existing = None
        if source_ref:
            existing = conn.execute(
                "SELECT id FROM images WHERE source_ref = ?", (source_ref,)
            ).fetchone()

        if existing:
            image_id = existing["id"]
        else:
            cur = conn.execute(
                """
                INSERT INTO images
                    (source_ref, title, source, creator, license, attribution,
                     source_url, full_image_url, width, height, saved_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_ref,
                    meta.get("title") or "Untitled",
                    meta.get("source"),
                    meta.get("creator"),
                    meta.get("license"),
                    meta.get("attribution"),
                    meta.get("source_url"),
                    meta.get("full_image"),
                    meta.get("width"),
                    meta.get("height"),
                    saved_at,
                ),
            )
            image_id = cur.lastrowid

            # Write files now that we have an id for the filename.
            full_name = f"{image_id}{full_ext}"
            full_path = IMAGES_DIR / full_name
            full_path.write_bytes(full_bytes)

            thumb_rel = None
            if thumb_bytes:
                thumb_name = f"{image_id}{thumb_ext or '.jpg'}"
                (THUMBS_DIR / thumb_name).write_bytes(thumb_bytes)
                thumb_rel = f"thumbs/{thumb_name}"

            conn.execute(
                "UPDATE images SET file_path = ?, thumb_path = ?, file_size = ? WHERE id = ?",
                (f"images/{full_name}", thumb_rel, len(full_bytes), image_id),
            )

        # Attach tags (merge with any existing).
        for name in tags:
            name = (name or "").strip()
            if not name:
                continue
            tag_id = _get_or_create_tag(conn, name)
            conn.execute(
                "INSERT OR IGNORE INTO image_tags (image_id, tag_id) VALUES (?, ?)",
                (image_id, tag_id),
            )

        for cid in collection_ids:
            conn.execute(
                "INSERT OR IGNORE INTO collection_images (collection_id, image_id, added_at) VALUES (?, ?, ?)",
                (cid, image_id, saved_at),
            )

        conn.commit()
        row = conn.execute("SELECT * FROM images WHERE id = ?", (image_id,)).fetchone()
        return _image_row_to_dict(conn, row)
    finally:
        conn.close()


def set_notes(image_id: int, notes: str) -> None:
    conn = get_conn()
    try:
        conn.execute("UPDATE images SET notes = ? WHERE id = ?", (notes, image_id))
        conn.commit()
    finally:
        conn.close()


def delete_image(image_id: int) -> bool:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT file_path, thumb_path FROM images WHERE id = ?", (image_id,)
        ).fetchone()
        if not row:
            return False
        for rel in (row["file_path"], row["thumb_path"]):
            if rel:
                p = DATA_DIR / rel
                try:
                    p.unlink(missing_ok=True)
                except OSError:
                    pass
        conn.execute("DELETE FROM images WHERE id = ?", (image_id,))
        # Drop now-orphaned tags.
        conn.execute("DELETE FROM tags WHERE id NOT IN (SELECT tag_id FROM image_tags)")
        conn.commit()
        return True
    finally:
        conn.close()
