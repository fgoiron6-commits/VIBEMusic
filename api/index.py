import os
import random
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from ytmusicapi import YTMusic

app = Flask(__name__)
CORS(app)

SOUNDSTAT_KEY = os.environ.get("SOUNDSTAT_API_KEY", "")
JAMENDO_CLIENT_ID = os.environ.get("JAMENDO_CLIENT_ID", "56d30c95")

RELATED_CACHE = {}
RESOLVE_CACHE = {}

AUDIUS_NODES = [
    "https://discoveryprovider.audius.co",
    "https://discoveryprovider2.audius.co",
    "https://discoveryprovider3.audius.co"
]

try:
    yt = YTMusic()
except Exception:
    yt = None

@app.after_request
def add_no_cache_headers(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return response

def search_audius_tracks(query, limit=12):
    out = []
    node = random.choice(AUDIUS_NODES)
    try:
        r = requests.get(
            f"{node}/v1/tracks/search",
            params={"query": query, "limit": limit},
            timeout=3.5
        )
        if r.ok:
            for item in r.json().get("data", []):
                tid = item.get("id")
                dur = int(item.get("duration") or 0)
                if not tid or dur < 60:
                    continue
                art = (item.get("artwork") or {}).get("480x480") or (item.get("artwork") or {}).get("150x150") or ""
                out.append({
                    "videoId": "",
                    "trackId": str(tid),
                    "title": item.get("title", "Unknown"),
                    "artist": (item.get("user") or {}).get("name", "Unknown Artist"),
                    "duration": f"{dur // 60}:{dur % 60:02d}",
                    "cover": art,
                    "directAudio": f"{node}/v1/tracks/{tid}/stream"
                })
    except Exception:
        pass
    return out

def search_jamendo_tracks(query, limit=10):
    out = []
    try:
        r = requests.get(
            "https://api.jamendo.com/v3.0/tracks/",
            params={
                "client_id": JAMENDO_CLIENT_ID,
                "format": "json",
                "limit": limit,
                "search": query,
                "audioformat": "mp32"
            },
            timeout=3.2
        )
        if r.ok:
            for item in r.json().get("results", []):
                aud = item.get("audio")
                dur = int(item.get("duration") or 180)
                if not aud or dur < 60:
                    continue
                out.append({
                    "videoId": "",
                    "trackId": f"jam_{item.get('id', '')}",
                    "title": item.get("name", "Unknown"),
                    "artist": item.get("artist_name", "Jamendo Artist"),
                    "duration": f"{dur // 60}:{dur % 60:02d}",
                    "cover": item.get("album_image") or item.get("image") or "",
                    "directAudio": aud
                })
    except Exception:
        pass
    return out

def full_catalog_fallback(query, limit=20):
    results = search_audius_tracks(query, limit)
    if len(results) < limit:
        results.extend(search_jamendo_tracks(query, limit - len(results)))
    return results[:limit]

@app.route("/api/search")
def search():
    q = (request.args.get("q") or "").strip()
    limit = int(request.args.get("limit") or 20)
    if not q:
        return jsonify({"results": []})

    results = []
    seen = set()

    # 1. Utamakan ytmusicapi TANPA diacak agar hasil teratas paling akurat
    if yt:
        try:
            raw = yt.search(q, filter="songs", limit=limit)
            for s in raw:
                vid = s.get("videoId")
                title = s.get("title")
                if not vid or len(vid) != 11 or not title:
                    continue
                artists = ", ".join([a.get("name", "") for a in (s.get("artists") or []) if a.get("name")]) or "Unknown Artist"
                key = f"{title.lower()}::{artists.lower()}"
                if key in seen:
                    continue
                seen.add(key)
                thumbs = s.get("thumbnails") or []
                cover = thumbs[-1].get("url", "") if thumbs else ""
                results.append({
                    "videoId": vid,
                    "trackId": vid,
                    "title": title,
                    "artist": artists,
                    "duration": s.get("duration") or "3:30",
                    "cover": cover
                })
        except Exception:
            pass

    # 2. Lengkapi dengan iTunes Metadata (untuk artis major seperti Daniel Caesar, dll) - TANPA previewUrl
    if len(results) < limit:
        try:
            ir = requests.get(
                "https://itunes.apple.com/search",
                params={"term": q, "media": "music", "entity": "song", "limit": limit, "country": "ID"},
                timeout=3.2
            )
            if ir.ok:
                for item in ir.json().get("results", []):
                    title = item.get("trackName")
                    artist = item.get("artistName")
                    if not title or not artist:
                        continue
                    key = f"{title.lower()}::{artist.lower()}"
                    if key in seen:
                        continue
                    seen.add(key)
                    ms = int(item.get("trackTimeMillis") or 210000) // 1000
                    results.append({
                        "videoId": "",
                        "trackId": f"it_{item.get('trackId', '')}",
                        "title": title,
                        "artist": artist,
                        "duration": f"{ms // 60}:{ms % 60:02d}",
                        "cover": (item.get("artworkUrl100") or "").replace("100x100bb", "500x500bb")
                    })
        except Exception:
            pass

    # 3. Tambah Audius jika masih kurang
    if len(results) < limit:
        for a in search_audius_tracks(q, limit - len(results)):
            key = f"{a['title'].lower()}::{a['artist'].lower()}"
            if key not in seen:
                seen.add(key)
                results.append(a)

    return jsonify({"source": "unified-search", "results": results[:limit]})

@app.route("/api/resolve")
def resolve_full_track():
    title = (request.args.get("title") or "").strip()
    artist = (request.args.get("artist") or "").strip()
    if not title:
        return jsonify({"error": "missing title"}), 400

    cache_key = f"{title.lower()}::{artist.lower()}"
    if cache_key in RESOLVE_CACHE:
        return jsonify(RESOLVE_CACHE[cache_key])

    q = f"{title} {artist}".strip()
    best_vid = ""
    direct_audio = ""

    if yt:
        try:
            hits = yt.search(q, filter="songs", limit=3)
            for h in hits:
                vid = h.get("videoId")
                if vid and len(vid) == 11:
                    best_vid = vid
                    break
        except Exception:
            pass

    aud_hits = search_audius_tracks(q, 5)
    t_low = title.lower()
    for item in aud_hits:
        name = (item.get("title") or "").lower()
        if item.get("directAudio") and (t_low[:5] in name or name[:5] in t_low):
            direct_audio = item["directAudio"]
            break

    res = {"videoId": best_vid, "directAudio": direct_audio}
    if best_vid or direct_audio:
        RESOLVE_CACHE[cache_key] = res
    return jsonify(res)

@app.route("/api/related")
def related():
    vid = (request.args.get("videoId") or "").strip()
    q = (request.args.get("q") or "").strip()
    cache_key = vid or q.lower()
    if cache_key in RELATED_CACHE:
        items = list(RELATED_CACHE[cache_key])
        random.shuffle(items)
        return jsonify({"source": "cache", "results": items})

    if SOUNDSTAT_KEY and q:
        try:
            sr = requests.get(
                "https://soundstat.info/api/v1/tracks",
                params={"q": q, "limit": 1},
                headers={"X-API-Key": SOUNDSTAT_KEY},
                timeout=3.2
            )
            if sr.ok:
                items = sr.json().get("tracks") or sr.json().get("results") or []
                if items and items[0].get("id"):
                    tid = items[0]["id"]
                    rr = requests.get(
                        f"https://soundstat.info/api/v1/tracks/{tid}/recommendations",
                        params={"limit": 16},
                        headers={"X-API-Key": SOUNDSTAT_KEY},
                        timeout=3.2
                    )
                    if rr.ok:
                        rec_list = rr.json().get("tracks") or rr.json().get("recommendations") or []
                        parsed_ss = []
                        for t in rec_list:
                            title = t.get("name") or t.get("title")
                            artists = ", ".join([a.get("name", "") for a in (t.get("artists") or [])]) or t.get("artist", "")
                            if title:
                                parsed_ss.append({
                                    "videoId": "",
                                    "trackId": str(t.get("id", "")),
                                    "title": title,
                                    "artist": artists or "Unknown Artist",
                                    "duration": "3:30",
                                    "cover": t.get("image") or t.get("cover") or ""
                                })
                        if parsed_ss:
                            RELATED_CACHE[cache_key] = parsed_ss
                            return jsonify({"source": "soundstat", "results": parsed_ss})
        except Exception:
            pass

    if yt and vid and len(vid) == 11:
        try:
            watch = yt.get_watch_playlist(videoId=vid, limit=18)
            tracks = watch.get("tracks") or []
            parsed = []
            for t in tracks[1:]:
                tvid = t.get("videoId")
                if not tvid:
                    continue
                artists = ", ".join([a.get("name", "") for a in (t.get("artists") or []) if a.get("name")]) or "Unknown Artist"
                thumbs = t.get("thumbnail") or []
                cover = thumbs[-1].get("url", "") if thumbs else ""
                parsed.append({
                    "videoId": tvid,
                    "trackId": tvid,
                    "title": t.get("title", "Unknown"),
                    "artist": artists,
                    "duration": t.get("length") or "3:30",
                    "cover": cover
                })
            if parsed:
                RELATED_CACHE[cache_key] = parsed
                return jsonify({"source": "ytmusicapi", "results": parsed})
        except Exception:
            pass

    return jsonify({"source": "full-fallback", "results": full_catalog_fallback(q or "top hits 2026", 16)})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
