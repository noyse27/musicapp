import os
import html
import logging
from flask import Flask, jsonify, request, send_file, abort, render_template
from flask_cors import CORS
import db
import scanner
import lastfm

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = Flask(__name__)

# Restrict CORS to origins defined via env var (space-separated).
# Default: deny all cross-origin requests (safe for local NAS use).
_cors_origins = os.environ.get("CORS_ORIGINS", "")
CORS(app, origins=_cors_origins.split() if _cors_origins else [])

MUSIC_ROOT = os.environ.get("MUSIC_ROOT", "/music")
MAX_DOWNLOAD_IDS = int(os.environ.get("MAX_DOWNLOAD_IDS", 500))


def _safe_path(path: str) -> str | None:
    """Resolve path and verify it stays within MUSIC_ROOT. Returns None if outside."""
    if not os.path.isabs(path):
        path = os.path.join(MUSIC_ROOT, path)
    real   = os.path.realpath(path)
    root   = os.path.realpath(MUSIC_ROOT)
    if not real.startswith(root + os.sep) and real != root:
        return None
    return real


def _int_arg(name: str, default: int, min_val: int = None, max_val: int = None) -> int:
    try:
        v = int(request.args.get(name, default))
    except (ValueError, TypeError):
        v = default
    if min_val is not None:
        v = max(min_val, v)
    if max_val is not None:
        v = min(max_val, v)
    return v


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/miniplayer")
def miniplayer():
    return render_template("miniplayer.html")


@app.get("/radio")
def radio_companion():
    return render_template("radio.html")


# ── Tracks ────────────────────────────────────────────────────────────────────

@app.get("/api/search")
def api_search():
    q           = request.args.get("q", "").strip()
    genre       = request.args.get("genre", "").strip() or None
    decade      = request.args.get("decade", "").strip() or None
    fmt         = request.args.get("format", "").strip() or None
    min_dur     = request.args.get("min_dur") or None
    max_dur     = request.args.get("max_dur") or None
    min_bitrate = request.args.get("min_bitrate") or None
    year_min    = request.args.get("year_min") or None
    year_max    = request.args.get("year_max") or None
    bpm_min     = request.args.get("bpm_min") or None
    bpm_max     = request.args.get("bpm_max") or None
    artist_letter = request.args.get("artist_letter") or None
    title_letter  = request.args.get("title_letter") or None
    page     = _int_arg("page",     1,   min_val=1)
    per_page = _int_arg("per_page", 50,  min_val=1, max_val=200)
    sort     = request.args.get("sort", "artist")

    try:
        if min_dur:     min_dur     = int(min_dur)
        if max_dur:     max_dur     = int(max_dur)
        if min_bitrate: min_bitrate = int(min_bitrate)
        if year_min:    year_min    = int(year_min)
        if year_max:    year_max    = int(year_max)
        if bpm_min:     bpm_min     = float(bpm_min)
        if bpm_max:     bpm_max     = float(bpm_max)
    except ValueError:
        return jsonify({"error": "invalid numeric parameter"}), 400

    total, tracks = db.search_tracks(
        query=q, genre=genre, decade=decade, fmt=fmt,
        min_dur=min_dur, max_dur=max_dur, min_bitrate=min_bitrate,
        year_min=year_min, year_max=year_max,
        bpm_min=bpm_min, bpm_max=bpm_max,
        artist_letter=artist_letter, title_letter=title_letter,
        page=page, per_page=per_page, sort=sort,
    )
    return jsonify({
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": max(1, (total + per_page - 1) // per_page),
        "results": tracks,
    })


# ── Genres / Stats ────────────────────────────────────────────────────────────

@app.get("/api/genres")
def api_genres():
    return jsonify(db.get_genres())


@app.get("/api/stats")
def api_stats():
    stats = db.get_stats()
    sc = scanner.status()
    stats["last_scan"] = sc.get("finished_at")
    return jsonify(stats)


# ── Cover art ─────────────────────────────────────────────────────────────────

@app.get("/api/cover/<hash_>")
def api_cover(hash_):
    data, mime = db.get_cover(hash_)
    if data is None:
        abort(404)
    import io
    resp = send_file(io.BytesIO(data), mimetype=mime, max_age=86400 * 365)
    resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    resp.headers["ETag"] = f'"{hash_}"'
    return resp


# ── Audio streaming ───────────────────────────────────────────────────────────

@app.get("/api/stream/<int:track_id>")
def api_stream(track_id):
    with db.db() as conn:
        row = conn.execute(
            "SELECT path FROM tracks WHERE id = ?", (track_id,)
        ).fetchone()
    if row is None:
        abort(404)

    path = _safe_path(row["path"])
    if path is None or not os.path.isfile(path):
        abort(404)

    range_header = request.headers.get("Range")
    size = os.path.getsize(path)
    mime = _guess_mime(path)

    if range_header:
        byte1, byte2 = _parse_range(range_header, size)
        if byte1 is None:
            return "", 416  # Range Not Satisfiable
        length = byte2 - byte1 + 1

        def generate():
            with open(path, "rb") as f:
                f.seek(byte1)
                remaining = length
                while remaining:
                    chunk = f.read(min(65536, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk

        from flask import Response
        headers = {
            "Content-Range": f"bytes {byte1}-{byte2}/{size}",
            "Accept-Ranges": "bytes",
            "Content-Length": length,
            "Content-Type": mime,
        }
        return Response(generate(), 206, headers=headers)

    return send_file(path, mimetype=mime, conditional=True)


def _guess_mime(path):
    ext = os.path.splitext(path)[1].lower()
    return {
        ".mp3": "audio/mpeg", ".flac": "audio/flac",
        ".m4a": "audio/mp4",  ".ogg": "audio/ogg",
        ".opus": "audio/ogg", ".aac": "audio/aac",
        ".wav": "audio/wav",
    }.get(ext, "application/octet-stream")


def _parse_range(header: str, size: int):
    """Returns (byte1, byte2) or (None, None) on invalid range."""
    try:
        ranges = header.replace("bytes=", "").split("-")
        byte1 = int(ranges[0]) if ranges[0] else 0
        byte2 = int(ranges[1]) if ranges[1] else size - 1
        byte2 = min(byte2, size - 1)
        if byte1 < 0 or byte1 > byte2 or byte1 >= size:
            return None, None
        return byte1, byte2
    except (ValueError, IndexError):
        return None, None


# ── Download / ZIP ────────────────────────────────────────────────────────────

@app.post("/api/download")
def api_download():
    import zipfile, io, time
    ids = request.json.get("ids", [])
    if not ids:
        return jsonify({"error": "no ids"}), 400
    if len(ids) > MAX_DOWNLOAD_IDS:
        return jsonify({"error": f"too many ids (max {MAX_DOWNLOAD_IDS})"}), 400

    # Ensure all IDs are integers to prevent injection
    try:
        ids = [int(i) for i in ids]
    except (ValueError, TypeError):
        return jsonify({"error": "invalid ids"}), 400

    with db.db() as conn:
        rows = conn.execute(
            f"SELECT id, path, title, artist FROM tracks WHERE id IN ({','.join('?'*len(ids))})",
            ids
        ).fetchall()

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
        for row in rows:
            path = _safe_path(row["path"])
            if path is None or not os.path.isfile(path):
                continue
            artist  = (row["artist"] or "Unbekannt").replace("/", "-")
            title   = (row["title"]  or os.path.basename(path)).replace("/", "-")
            ext     = os.path.splitext(path)[1]
            arcname = f"{artist} - {title}{ext}"
            zf.write(path, arcname)

    buf.seek(0)
    filename = f"adolar_{int(time.time())}.zip"
    return send_file(buf, mimetype="application/zip",
                     as_attachment=True, download_name=filename)


# ── Play count ───────────────────────────────────────────────────────────────

@app.post("/api/track/<int:track_id>/bpm")
def api_track_bpm(track_id):
    """Accept a BPM value from an external tool (e.g. Adolar Disco)."""
    data = request.get_json(silent=True) or {}
    bpm = data.get("bpm")
    if bpm is None or not isinstance(bpm, (int, float)) or bpm <= 0:
        return jsonify({"error": "bpm must be a positive number"}), 400
    updated = db.update_bpm(track_id, round(float(bpm), 2))
    return jsonify({"ok": True, "updated": updated})


@app.post("/api/track/<int:track_id>/played")
def api_track_played(track_id):
    new_count, raw_path = db.increment_play_count(track_id)
    if raw_path is None:
        abort(404)

    path = _safe_path(raw_path)
    if path and os.path.isfile(path):
        # Read current tag value and take MAX to protect against external changes
        tag_count  = _read_play_count_tag(path)
        new_count  = max(tag_count, new_count - 1) + 1  # MAX(tag, db_before) + 1
        db.set_play_count(track_id, new_count)
        _write_play_count_tag(path, new_count)

    return jsonify({"play_count": new_count})


def _read_play_count_tag(path: str) -> int:
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext == ".mp3":
            from mutagen.id3 import ID3
            tags = ID3(path)
            pcnt = tags.get("PCNT")
            return int(pcnt.count) if pcnt else 0
        elif ext == ".flac":
            from mutagen.flac import FLAC
            tags = FLAC(path)
            raw = tags.get("play_count")
            return int(raw[0]) if raw else 0
        elif ext == ".m4a":
            from mutagen.mp4 import MP4
            tags = MP4(path)
            raw = tags.get("----:com.apple.iTunes:play_count")
            return int(raw[0]) if raw else 0
    except Exception:
        pass
    return 0


def _write_play_count_tag(path: str, count: int):
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext == ".mp3":
            from mutagen.id3 import ID3, PCNT
            tags = ID3(path)
            tags["PCNT"] = PCNT(count=count)
            tags.save(path)
        elif ext == ".flac":
            from mutagen.flac import FLAC
            tags = FLAC(path)
            tags["play_count"] = [str(count)]
            tags.save()
        elif ext == ".m4a":
            from mutagen.mp4 import MP4
            tags = MP4(path)
            tags["----:com.apple.iTunes:play_count"] = [str(count).encode()]
            tags.save()
        # ogg/opus/wav: skip — no standard play count field
    except Exception as e:
        logging.getLogger(__name__).warning("Could not write play count tag to %s: %s", path, e)


# ── Radio / Random ────────────────────────────────────────────────────────────

@app.get("/api/random")
def api_random():
    count   = min(int(request.args.get("count", 25)), 100)
    exclude = [int(x) for x in request.args.getlist("exclude") if x.isdigit()]
    return jsonify(db.get_random_tracks(count, exclude))


# ── Last.fm ───────────────────────────────────────────────────────────────────

@app.get("/api/lastfm/status")
def api_lastfm_status():
    sk       = db.get_setting("lastfm_session_key")
    username = db.get_setting("lastfm_username")
    return jsonify({"connected": bool(sk), "username": username})


@app.get("/api/lastfm/auth")
def api_lastfm_auth():
    callback = request.host_url.rstrip("/") + "/api/lastfm/callback"
    url = lastfm.get_auth_url(callback)
    from flask import redirect
    return redirect(url)


@app.get("/api/lastfm/callback")
def api_lastfm_callback():
    token = request.args.get("token")
    if not token:
        return "Kein Token erhalten.", 400
    try:
        session = lastfm.get_session(token)
        db.set_setting("lastfm_session_key", session["key"])
        db.set_setting("lastfm_username",    session["name"])
    except Exception as e:
        return f"Last.fm Auth fehlgeschlagen: {html.escape(str(e))}", 500

    username = html.escape(db.get_setting("lastfm_username") or "")
    return f"""<html><body style="font-family:sans-serif;padding:40px;background:#30302E;color:#ECECEC">
        <h2 style="color:#7F77DD">&#10003; Last.fm verbunden!</h2>
        <p>Du bist als <strong>{username}</strong> eingeloggt.</p>
        <p><a href="/" style="color:#7F77DD">Zur&#252;ck zur App</a></p>
    </body></html>"""


@app.post("/api/lastfm/disconnect")
def api_lastfm_disconnect():
    db.del_setting("lastfm_session_key")
    db.del_setting("lastfm_username")
    return jsonify({"ok": True})


@app.post("/api/lastfm/nowplaying")
def api_lastfm_nowplaying():
    sk = db.get_setting("lastfm_session_key")
    if not sk:
        return jsonify({"error": "not connected"}), 401
    body   = request.json or {}
    artist = body.get("artist", "")
    title  = body.get("title", "")
    if not artist or not title:
        return jsonify({"error": "missing artist/title"}), 400
    try:
        lastfm.now_playing(sk, artist, title, duration=body.get("duration"))
        return jsonify({"ok": True})
    except Exception:
        logging.getLogger(__name__).exception("Last.fm now_playing failed")
        return jsonify({"error": "Last.fm request failed"}), 500


@app.post("/api/lastfm/scrobble")
def api_lastfm_scrobble():
    sk = db.get_setting("lastfm_session_key")
    if not sk:
        return jsonify({"error": "not connected"}), 401
    body   = request.json or {}
    artist = body.get("artist", "")
    title  = body.get("title", "")
    if not artist or not title:
        return jsonify({"error": "missing artist/title"}), 400
    try:
        lastfm.scrobble(sk, artist, title)
        return jsonify({"ok": True})
    except Exception:
        logging.getLogger(__name__).exception("Last.fm scrobble failed")
        return jsonify({"error": "Last.fm request failed"}), 500


@app.post("/api/lastfm/love")
def api_lastfm_love():
    sk = db.get_setting("lastfm_session_key")
    if not sk:
        return jsonify({"error": "not connected"}), 401
    body   = request.json or {}
    action = body.get("action", "love")
    artist = body.get("artist", "")
    title  = body.get("title", "")
    if not artist or not title:
        return jsonify({"error": "missing artist/title"}), 400
    try:
        if action == "love":
            lastfm.love(sk, artist, title)
        else:
            lastfm.unlove(sk, artist, title)
        return jsonify({"ok": True, "loved": action == "love"})
    except Exception:
        logging.getLogger(__name__).exception("Last.fm love/unlove failed")
        return jsonify({"error": "Last.fm request failed"}), 500


@app.get("/api/lastfm/loved")
def api_lastfm_loved():
    sk = db.get_setting("lastfm_session_key")
    if not sk:
        return jsonify({"loved": False})
    artist = request.args.get("artist", "")
    title  = request.args.get("title", "")
    try:
        info = lastfm.get_track_info(sk, artist, title)
        loved = str(info.get("userloved", "0")) == "1"
        return jsonify({"loved": loved})
    except Exception:
        return jsonify({"loved": False})


# ── Scanner ───────────────────────────────────────────────────────────────────

@app.post("/api/scan/start")
def api_scan_start():
    if not os.path.isdir(MUSIC_ROOT):
        return jsonify({"error": f"MUSIC_ROOT not found: {MUSIC_ROOT}"}), 400
    scanner.run_scan(MUSIC_ROOT)
    return jsonify({"status": "started"})


@app.post("/api/scan/bpm-tags")
def api_bpm_tags():
    """Read BPM from file tags (TBPM etc.) and update DB — fast, no audio analysis."""
    import threading
    def _worker():
        updated = 0
        try:
            from db import get_connection
            conn = get_connection()
            rows = conn.execute("SELECT id, path FROM tracks").fetchall()
            conn.close()
            for row in rows:
                try:
                    bpm = scanner._read_bpm_tag(row["path"])
                    if bpm and bpm > 0:
                        c = get_connection()
                        c.execute("UPDATE tracks SET bpm=? WHERE id=?", (bpm, row["id"]))
                        c.commit()
                        c.close()
                        updated += 1
                except Exception:
                    pass
        except Exception as e:
            import logging; logging.getLogger(__name__).error("bpm-tags: %s", e)
    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    return jsonify({"status": "started", "updated": 0, "note": "running in background"})


@app.post("/api/scan/bpm")
def api_bpm_scan():
    """Trigger background BPM analysis for tracks without BPM.
    Optional JSON body: {"limit": 500} to cap the number analysed."""
    data = request.get_json(silent=True) or {}
    limit = int(data.get("limit", 0))
    scanner.run_bpm_scan(limit)
    return jsonify({"status": "started", "limit": limit or "unlimited"})


@app.get("/api/scan/status")
def api_scan_status():
    s = scanner.status()
    s.update(db.get_scanner_status())
    return jsonify(s)


# ── Bootstrap ─────────────────────────────────────────────────────────────────

db.init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
