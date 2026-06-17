import os
import hashlib
import time
import requests

API_KEY    = os.environ.get("LASTFM_API_KEY", "")
API_SECRET = os.environ.get("LASTFM_API_SECRET", "")
API_ROOT   = "https://ws.audioscrobbler.com/2.0/"


def _sig(params: dict) -> str:
    """Last.fm API signature: sorted key+value string, no 'format', + secret, md5."""
    s = "".join(f"{k}{params[k]}" for k in sorted(params) if k != "format")
    s += API_SECRET
    return hashlib.md5(s.encode("utf-8")).hexdigest()


def _post(params: dict) -> dict:
    p = dict(params)          # never mutate caller's dict
    p["api_key"] = API_KEY
    p["format"]  = "json"
    p["api_sig"] = _sig(p)
    r = requests.post(API_ROOT, data=p, timeout=10)
    r.raise_for_status()
    return r.json()


def _get(params: dict) -> dict:
    p = dict(params)          # never mutate caller's dict
    p["api_key"] = API_KEY
    p["format"]  = "json"
    r = requests.get(API_ROOT, params=p, timeout=10)
    r.raise_for_status()
    return r.json()


def get_auth_url(callback_url: str) -> str:
    return (f"https://www.last.fm/api/auth/"
            f"?api_key={API_KEY}&cb={requests.utils.quote(callback_url, safe='')}")


def get_session(token: str) -> dict:
    """Exchange token for session key. Returns {"name": ..., "key": ...}."""
    data = _post({"method": "auth.getSession", "token": token})
    return data.get("session", {})


def scrobble(session_key: str, artist: str, title: str, timestamp: int = None) -> dict:
    if timestamp is None:
        timestamp = int(time.time())
    return _post({
        "method":    "track.scrobble",
        "sk":        session_key,
        "artist":    artist,
        "track":     title,
        "timestamp": timestamp,
    })


def love(session_key: str, artist: str, title: str) -> dict:
    return _post({"method": "track.love", "sk": session_key,
                  "artist": artist, "track": title})


def unlove(session_key: str, artist: str, title: str) -> dict:
    return _post({"method": "track.unlove", "sk": session_key,
                  "artist": artist, "track": title})


def get_track_info(session_key: str, artist: str, title: str) -> dict:
    """Returns track info including userloved (0 or 1)."""
    try:
        data = _get({"method": "track.getInfo", "sk": session_key,
                     "artist": artist, "track": title, "username": ""})
        return data.get("track", {})
    except Exception:
        return {}
