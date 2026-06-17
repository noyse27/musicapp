import os
import hashlib
import threading
import time
import logging
from mutagen import File as MutagenFile
from mutagen.id3 import ID3NoHeaderError
from db import upsert_track, save_cover, init_db

log = logging.getLogger(__name__)

_status = {
    "running": False,
    "progress": 0,
    "total": 0,
    "current_file": "",
    "errors": 0,
    "started_at": None,
    "finished_at": None,
}
_lock = threading.Lock()


def status():
    with _lock:
        return dict(_status)


def _update(**kw):
    with _lock:
        _status.update(kw)


def _tag_str(tags, *keys):
    for key in keys:
        val = tags.get(key)
        if val:
            return str(val[0]).strip() or None
    return None


def _tag_int(tags, *keys):
    raw = _tag_str(tags, *keys)
    if raw:
        try:
            return int(raw.split("/")[0])
        except ValueError:
            pass
    return None


def _extract_cover(audio):
    """Return (hash, bytes, mime) or (None, None, None)."""
    tags = audio.tags
    if tags is None:
        return None, None, None

    # ID3 APIC
    for key in tags.keys():
        if key.startswith("APIC"):
            pic = tags[key]
            data = pic.data
            mime = pic.mime or "image/jpeg"
            h = hashlib.sha1(data).hexdigest()
            return h, data, mime

    # MP4 / FLAC / Ogg cover
    for attr in ("covr", "METADATA_BLOCK_PICTURE", "metadata_block_picture"):
        val = tags.get(attr)
        if val:
            pic = val[0]
            if hasattr(pic, "data"):
                data = pic.data
                mime = getattr(pic, "mime", "image/jpeg") or "image/jpeg"
            else:
                data = bytes(pic)
                mime = "image/jpeg"
            h = hashlib.sha1(data).hexdigest()
            return h, data, mime

    return None, None, None


def _scan_file(path: str) -> dict | None:
    try:
        stat = os.stat(path)
        audio = MutagenFile(path, easy=False)
        if audio is None:
            return None

        tags = audio.tags or {}

        # Try easy tags for common fields
        easy = MutagenFile(path, easy=True)
        etags = easy.tags if easy and easy.tags else {}

        def pick(*keys):
            for k in keys:
                v = etags.get(k) or tags.get(k)
                if v:
                    return str(v[0]).strip() or None
            return None

        def pick_int(*keys):
            raw = pick(*keys)
            if raw:
                try:
                    return int(str(raw).split("/")[0])
                except ValueError:
                    pass
            return None

        cover_hash, cover_data, cover_mime = _extract_cover(audio)
        if cover_hash and cover_data:
            save_cover(cover_hash, cover_data, cover_mime)

        info = audio.info
        duration = int(getattr(info, "length", 0))
        bitrate = int(getattr(info, "bitrate", 0) / 1000) if hasattr(info, "bitrate") else 0

        # Read existing play count from tag
        play_count = 0
        try:
            pcnt = tags.get("PCNT")                          # MP3 ID3
            if pcnt is not None:
                play_count = int(pcnt.count)
            else:
                raw = (tags.get("play_count")                # FLAC Vorbis
                       or tags.get("----:com.apple.iTunes:play_count"))  # M4A
                if raw:
                    play_count = int(str(raw[0]).strip())
        except Exception:
            pass

        return {
            "path": path,
            "title": pick("title", "TIT2"),
            "artist": pick("artist", "TPE1", "TPE2"),
            "album": pick("album", "TALB"),
            "genre": pick("genre", "TCON"),
            "year": pick_int("date", "TDRC", "TYER"),
            "track_no": pick_int("tracknumber", "TRCK"),
            "duration": duration,
            "bitrate": bitrate,
            "size": stat.st_size,
            "cover_hash": cover_hash,
            "mtime": stat.st_mtime,
            "play_count": play_count,
        }
    except Exception as e:
        log.warning("Failed to scan %s: %s", path, e)
        return None


def _collect_mp3s(root: str):
    extensions = {".mp3", ".flac", ".m4a", ".ogg", ".opus", ".aac", ".wav"}
    for dirpath, _, filenames in os.walk(root):
        for fname in filenames:
            if os.path.splitext(fname)[1].lower() in extensions:
                yield os.path.join(dirpath, fname)


def run_scan(music_root: str):
    if _status["running"]:
        return

    def _worker():
        _update(running=True, progress=0, total=0, errors=0,
                started_at=time.time(), finished_at=None, current_file="")
        try:
            files = list(_collect_mp3s(music_root))
            _update(total=len(files))
            for i, path in enumerate(files):
                _update(current_file=path, progress=i + 1)
                data = _scan_file(path)
                if data:
                    upsert_track(data)
                else:
                    with _lock:
                        _status["errors"] += 1
        except Exception as e:
            log.error("Scanner error: %s", e)
        finally:
            _update(running=False, finished_at=time.time(), current_file="")

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
