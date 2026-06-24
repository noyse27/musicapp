import sqlite3
import os
from contextlib import contextmanager

DB_PATH = os.environ.get("DB_PATH", "/data/adolar.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def db():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS tracks (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                path        TEXT    NOT NULL UNIQUE,
                title       TEXT,
                artist      TEXT,
                album       TEXT,
                genre       TEXT,
                year        INTEGER,
                track_no    INTEGER,
                duration    INTEGER,
                bitrate     INTEGER,
                size        INTEGER,
                cover_hash  TEXT,
                mtime       REAL,
                indexed_at  REAL DEFAULT (unixepoch())
            );

            CREATE TABLE IF NOT EXISTS covers (
                hash        TEXT PRIMARY KEY,
                data        BLOB NOT NULL,
                mime        TEXT NOT NULL DEFAULT 'image/jpeg'
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS tracks_fts USING fts5(
                title,
                artist,
                album,
                genre,
                content='tracks',
                content_rowid='id'
            );

            CREATE TRIGGER IF NOT EXISTS tracks_ai AFTER INSERT ON tracks BEGIN
                INSERT INTO tracks_fts(rowid, title, artist, album, genre)
                VALUES (new.id, new.title, new.artist, new.album, new.genre);
            END;

            CREATE TRIGGER IF NOT EXISTS tracks_ad AFTER DELETE ON tracks BEGIN
                INSERT INTO tracks_fts(tracks_fts, rowid, title, artist, album, genre)
                VALUES ('delete', old.id, old.title, old.artist, old.album, old.genre);
            END;

            CREATE TRIGGER IF NOT EXISTS tracks_au AFTER UPDATE ON tracks BEGIN
                INSERT INTO tracks_fts(tracks_fts, rowid, title, artist, album, genre)
                VALUES ('delete', old.id, old.title, old.artist, old.album, old.genre);
                INSERT INTO tracks_fts(rowid, title, artist, album, genre)
                VALUES (new.id, new.title, new.artist, new.album, new.genre);
            END;

            CREATE INDEX IF NOT EXISTS idx_tracks_artist ON tracks(artist);
            CREATE INDEX IF NOT EXISTS idx_tracks_album  ON tracks(album);
            CREATE INDEX IF NOT EXISTS idx_tracks_genre  ON tracks(genre);
            CREATE INDEX IF NOT EXISTS idx_tracks_year   ON tracks(year);

            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT
            );
        """)
        # Migrations (safe to run repeatedly)
        for migration in [
            "ALTER TABLE tracks ADD COLUMN play_count INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE tracks ADD COLUMN bpm REAL",
        ]:
            try:
                conn.execute(migration)
            except Exception:
                pass


def search_tracks(query="", genre=None, decade=None, fmt=None,
                  min_dur=None, max_dur=None, min_bitrate=None,
                  year_min=None, year_max=None,
                  artist_letter=None, title_letter=None,
                  page=1, per_page=50, sort="artist"):
    params = []
    conditions = []

    if query:
        conditions.append(
            "t.id IN (SELECT rowid FROM tracks_fts WHERE tracks_fts MATCH ?)"
        )
        params.append(query + "*")

    if genre:
        conditions.append("t.genre = ?")
        params.append(genre)
    if decade:
        try:
            d = int(decade)
            conditions.append("t.year >= ? AND t.year <= ?")
            params += [d, d + 9]
        except ValueError:
            pass
    if fmt:
        ext = "." + fmt.lower()
        conditions.append("LOWER(t.path) LIKE ?")
        params.append("%" + ext)
    if min_dur is not None:
        conditions.append("t.duration >= ?")
        params.append(int(min_dur))
    if max_dur is not None:
        conditions.append("t.duration <= ?")
        params.append(int(max_dur))
    if min_bitrate is not None:
        conditions.append("t.bitrate >= ?")
        params.append(int(min_bitrate))
    if year_min is not None:
        conditions.append("t.year >= ?")
        params.append(int(year_min))
    if year_max is not None:
        conditions.append("t.year <= ?")
        params.append(int(year_max))

    def _letter_cond(col, letter):
        if letter == "0–9":
            return f"SUBSTR(UPPER({col}),1,1) BETWEEN '0' AND '9'"
        elif letter == "#":
            return (f"(SUBSTR(UPPER({col}),1,1) NOT BETWEEN 'A' AND 'Z' "
                    f"AND SUBSTR(UPPER({col}),1,1) NOT BETWEEN '0' AND '9')")
        else:
            return f"SUBSTR(UPPER({col}),1,1) = ?"

    if artist_letter:
        cond = _letter_cond("t.artist", artist_letter)
        conditions.append(cond)
        if artist_letter not in ("0–9", "#"):
            params.append(artist_letter.upper())
    if title_letter:
        cond = _letter_cond("t.title", title_letter)
        conditions.append(cond)
        if title_letter not in ("0–9", "#"):
            params.append(title_letter.upper())

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    sort_map = {
        "artist": "t.artist, t.album, t.track_no",
        "title":  "t.title",
        "album":  "t.album, t.track_no",
        "year":   "t.year DESC, t.artist",
        "duration": "t.duration DESC",
    }
    order = sort_map.get(sort, sort_map["artist"])
    offset = (page - 1) * per_page

    with db() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM tracks t {where}", params
        ).fetchone()[0]

        rows = conn.execute(
            f"""SELECT t.id, t.path, t.title, t.artist, t.album, t.genre,
                       t.year, t.track_no, t.duration, t.bitrate, t.size, t.cover_hash
                FROM tracks t {where}
                ORDER BY {order}
                LIMIT ? OFFSET ?""",
            params + [per_page, offset],
        ).fetchall()

    def fmt_duration(s):
        if not s:
            return "0:00"
        m, sec = divmod(int(s), 60)
        return f"{m}:{sec:02d}"

    def file_format(path):
        import os
        return os.path.splitext(path)[1].lstrip(".").upper() if path else "MP3"

    tracks = []
    for r in rows:
        d = dict(r)
        d["duration_fmt"] = fmt_duration(d["duration"])
        d["format"] = file_format(d["path"])
        d["has_cover"] = bool(d["cover_hash"])
        tracks.append(d)

    return total, tracks


def get_genres():
    with db() as conn:
        rows = conn.execute(
            "SELECT DISTINCT genre FROM tracks WHERE genre IS NOT NULL AND genre != '' ORDER BY genre"
        ).fetchall()
    return [r[0] for r in rows]


def get_stats():
    with db() as conn:
        total = conn.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]
        size_row = conn.execute("SELECT SUM(size) FROM tracks").fetchone()
        size_gb = round((size_row[0] or 0) / 1_073_741_824, 1)
    return {"total_tracks": total, "total_size_gb": size_gb}


def get_random_tracks(count=25, exclude_ids=None):
    excl = exclude_ids or []
    with db() as conn:
        rows = conn.execute(
            f"""SELECT id, path, title, artist, album, genre, year, track_no,
                       duration, bitrate, size, cover_hash
                FROM tracks
                {"WHERE id NOT IN (" + ",".join("?"*len(excl)) + ")" if excl else ""}
                ORDER BY RANDOM() LIMIT ?""",
            excl + [count],
        ).fetchall()
    import os

    def _fmt(s):
        if not s: return "0:00"
        m, sec = divmod(int(s), 60)
        return f"{m}:{sec:02d}"

    def _file_format(path):
        return os.path.splitext(path)[1].lstrip(".").upper() if path else "MP3"

    tracks = []
    for r in rows:
        d = dict(r)
        d["duration_fmt"] = _fmt(d["duration"])
        d["format"] = _file_format(d["path"])
        d["has_cover"] = bool(d["cover_hash"])
        tracks.append(d)
    return tracks


def update_bpm(track_id: int, bpm: float) -> bool:
    """Store BPM for a track. Returns True if the track was found and updated."""
    with db() as conn:
        cur = conn.execute(
            "UPDATE tracks SET bpm=? WHERE id=? AND (bpm IS NULL OR bpm=0)",
            (bpm, track_id)
        )
        return cur.rowcount > 0


def get_scanner_status():
    with db() as conn:
        total = conn.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]
    return {"total_tracks": total}


def upsert_track(data: dict):
    data.setdefault("play_count", 0)
    with db() as conn:
        conn.execute("""
            INSERT INTO tracks (path, title, artist, album, genre, year, track_no,
                                duration, bitrate, size, cover_hash, mtime, play_count)
            VALUES (:path, :title, :artist, :album, :genre, :year, :track_no,
                    :duration, :bitrate, :size, :cover_hash, :mtime, :play_count)
            ON CONFLICT(path) DO UPDATE SET
                title=excluded.title, artist=excluded.artist, album=excluded.album,
                genre=excluded.genre, year=excluded.year, track_no=excluded.track_no,
                duration=excluded.duration, bitrate=excluded.bitrate, size=excluded.size,
                cover_hash=excluded.cover_hash, mtime=excluded.mtime,
                indexed_at=unixepoch(),
                play_count=MAX(play_count, excluded.play_count)
        """, data)


def save_cover(hash_: str, data: bytes, mime: str = "image/jpeg"):
    with db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO covers (hash, data, mime) VALUES (?, ?, ?)",
            (hash_, data, mime),
        )


def increment_play_count(track_id: int):
    """Increments play_count by 1 in DB, returns (new_count, path)."""
    with db() as conn:
        conn.execute(
            "UPDATE tracks SET play_count = play_count + 1 WHERE id = ?", (track_id,)
        )
        row = conn.execute(
            "SELECT play_count, path FROM tracks WHERE id = ?", (track_id,)
        ).fetchone()
    return (row["play_count"], row["path"]) if row else (0, None)


def set_play_count(track_id: int, count: int):
    with db() as conn:
        conn.execute(
            "UPDATE tracks SET play_count = ? WHERE id = ?", (count, track_id)
        )


def get_setting(key: str, default=None):
    with db() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(key: str, value: str):
    with db() as conn:
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)", (key, value))


def del_setting(key: str):
    with db() as conn:
        conn.execute("DELETE FROM settings WHERE key=?", (key,))


def get_cover(hash_: str):
    with db() as conn:
        row = conn.execute(
            "SELECT data, mime FROM covers WHERE hash = ?", (hash_,)
        ).fetchone()
    return (row["data"], row["mime"]) if row else (None, None)
