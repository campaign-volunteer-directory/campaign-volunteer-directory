#!/usr/bin/env python3
"""Content-addressed media store for scraped Discord data.

Identical attachments (the same meme posted in five channels) are stored
ONCE: bytes live at media/blobs/<sha256>.<ext>, and a SQLite ledger tracks
every message reference to it.

Schema:
    blobs(hash PK, path, size, kind, ext, first_channel, first_ts, refs)
    refs(channel, msg_id, url, hash, PK(channel, msg_id, url))

Thread-safety: sqlite connections are per-call (opened, used, closed), so
parallel scraper processes can share the DB safely.
"""
import hashlib
import json
import sqlite3
import urllib.request
from pathlib import Path

MAX_BYTES = 50 * 1024 * 1024

SCHEMA = """
CREATE TABLE IF NOT EXISTS blobs (
    hash TEXT PRIMARY KEY,
    path TEXT NOT NULL,
    size INTEGER NOT NULL,
    kind TEXT NOT NULL,
    ext TEXT NOT NULL,
    first_channel TEXT,
    first_ts TEXT,
    refs INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS refs (
    channel TEXT NOT NULL,
    msg_id TEXT NOT NULL,
    url TEXT NOT NULL,
    hash TEXT NOT NULL,
    PRIMARY KEY (channel, msg_id, url)
);
"""


class MediaStore:
    def __init__(self, db_path, blob_root):
        self.db_path = Path(db_path)
        self.blob_root = Path(blob_root)
        self.blob_root.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.executescript(SCHEMA)

    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def known_url(self, channel, msg_id, url):
        """Hash + blob path already recorded for this URL? Returns (hash, path) or None."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT hash FROM refs WHERE url = ? LIMIT 1", (url,)).fetchone()
        if not row:
            return None
        blob = self.blob_path(row[0])
        if blob.exists():
            return row[0], str(blob)
        return None

    def lookup_hash(self, digest):
        """Existing blob for this content hash? Returns path or None."""
        blob = self.blob_path(digest)
        return str(blob) if blob else None

    def blob_path(self, digest, ext=""):
        return self.blob_root / f"{digest}.{ext}" if ext else next(
            (p for p in self.blob_root.glob(f"{digest}.*")), None)

    def add(self, channel, msg_id, url, digest, size, kind, ext, path, first_ts):
        """Record a blob (creating/updating if the hash is new) + a reference."""
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO blobs (hash, path, size, kind, ext, first_channel, first_ts, refs) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 1) "
                "ON CONFLICT(hash) DO UPDATE SET refs = refs + 1",
                (digest, path, size, kind, ext, channel, first_ts))
            conn.execute(
                "INSERT OR IGNORE INTO refs (channel, msg_id, url, hash) VALUES (?, ?, ?, ?)",
                (channel, msg_id, url, digest))

    def stats(self):
        with self._conn() as conn:
            blobs = conn.execute("SELECT COUNT(*), COALESCE(SUM(size), 0) FROM blobs").fetchone()
            refs = conn.execute("SELECT COUNT(*) FROM refs").fetchone()
            top = conn.execute(
                "SELECT hash, refs, size FROM blobs ORDER BY refs DESC LIMIT 5").fetchall()
        return {"blobs": blobs[0], "bytes": blobs[1], "refs": refs[0],
                "top": [{"refs": r, "size": s, "hash": h[:10]} for h, r, s in top]}


def fetch_bytes(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = resp.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError(f"file too big: {len(data)} bytes")
    return data


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def ext_of(url):
    return url.split("?")[0].rsplit(".", 1)[-1].split("/")[0][:6] or "bin"


def kind_of(url):
    ext = ext_of(url)
    if ext in ("png", "jpg", "jpeg", "gif", "webp"):
        return "image"
    if ext in ("mp4", "webm", "mov"):
        return "video"
    return "file"
