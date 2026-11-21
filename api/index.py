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
AUDIO_CACHE = {}

AUDIUS_NODES = [
    "https://discoveryprovider.audius.co",
    "https://discoveryprovider2.audius.co",
    "https://discoveryprovider3.audius.co"
]

PIPED_INSTANCES = [
    "https://pipedapi.kavin.rocks",
    "https://pipedapi.adminforge.de",
    "https://pipedapi.leptons.xyz",
    "https://api.piped.private.coffee"
]

INV_INSTANCES = [
    "https://inv.nadeko.net",
    "https://yt.artemislena.eu",
    "https://invidious.nerdvpn.de",
    "https://invidious.jing.rocks"
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

def search_audius_tracks(query, limit=10):
    out = []
    node = random.choice(AUDIUS_NODES)
    try:
        r = requests.get(
            f"{node}/v1/tracks/search",
            params={"query": query, "limit": limit},
            timeout=3.2
        )
        if r.ok:
            for item in r.json().get("data", []):
                tid = item.get("id")
                if not tid:
                    continue
                dur = int(item.get("duration") or 0)
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

def search_jamendo_tracks(query, limit=8):
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
            timeout=3.0
        )
        if r.ok:
            for item in r.json().get("results", []):
                aud = item.get("audio")
                if not aud:
                    continue
                dur = int(item.get("duration") or 180)
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

def fallback_catalog(query, limit=18):
    results = search_audius_tracks(query, min(limit, 8))
    if len(results) < limit:
        try:
            offset = random.randint(0, 20)
            r = requests.get(
                "https://itunes.apple.com/search",
                params={"term": query, "media": "music", "entity": "song", "limit": limit, "offset": offset, "country": "ID"},
                timeout=3.5
            )
            if r.ok:
                for item in r.json().get("results", []):
                    ms = int(item.get("trackTimeMillis") or 0) // 1000
                    results.append({
                        "videoId": "",
                        "trackId": str(item.get("trackId", "")),
                        "title": item.get("trackName", "Unknown"),
                        "artist": item.get("artistName", "Unknown Artist"),
                        "duration": f"{ms // 60}:{ms % 60:02d}",
                        "cover": (item.get("artworkUrl100") or "").replace("100x100bb", "500x500bb"),
                        "previewUrl": item.get("previewUrl", "")
                    })
        except Exception:
            pass
    if len(results) < 5:
        results.extend(search_jamendo_tracks(query, 6))
    return results[:limit]

@app.route("/api/health")
def health():
    return jsonify({
        "status": "ok",
        "ytmusicapi": bool(yt),
        "soundstat": bool(SOUNDSTAT_KEY),
        "audius_nodes": len(AUDIUS_NODES)
    })

@app.route("/api/search")
def search():
    q = (request.args.get("q") or "").strip()
    limit = int(request.args.get("limit") or 18)
    if not q:
        return jsonify({"results": []})

    if yt:
        try:
            raw = yt.search(q, filter="songs", limit=limit)
            parsed = []
            for s in raw:
                vid = s.get("videoId")
                if not vid:
                    continue
                artists = ", ".join([a.get("name", "") for a in (s.get("artists") or []) if a.get("name")]) or "Unknown Artist"
                thumbs = s.get("thumbnails") or []
                cover = thumbs[-1].get("url", "") if thumbs else ""
                parsed.append({
                    "videoId": vid,
                    "trackId": vid,
                    "title": s.get("title", "Unknown"),
                    "artist": artists,
                    "duration": s.get("duration") or "3:30",
                    "cover": cover
                })
            if parsed:
                random.shuffle(parsed)
                return jsonify({"source": "ytmusicapi", "results": parsed})
        except Exception:
            pass

    return jsonify({"source": "fallback", "results": fallback_catalog(q, limit)})

@app.route("/api/audio")
def get_audio_url():
    vid = (request.args.get("videoId") or "").strip()
    title = (request.args.get("title") or "").strip()
    artist = (request.args.get("artist") or "").strip()
    q = f"{title} {artist}".strip()
    cache_key = vid or q.lower()

    if cache_key in AUDIO_CACHE:
        return jsonify(AUDIO_CACHE[cache_key])

    # 1. Audius Multi-Node
    if q:
        aud_hits = search_audius_tracks(q, 5)
        t_low = title.lower()
        for item in aud_hits:
            name = (item.get("title") or "").lower()
            if item.get("directAudio") and (not t_low or t_low[:4] in name or name[:4] in t_low):
                res = {"url": item["directAudio"], "source": "AUDIUS FULL"}
                AUDIO_CACHE[cache_key] = res
                return jsonify(res)

    # 2. Resolve videoId via ytmusicapi jika kosong
    if (not vid or len(vid) != 11) and yt and q:
        try:
            hits = yt.search(q, filter="songs", limit=2)
            if hits and hits[0].get("videoId"):
                vid = hits[0]["videoId"]
        except Exception:
            pass

    # 3. Invidious & Piped Multi-Instance
    if vid and len(vid) == 11:
        inv_pool = list(INV_INSTANCES)
        random.shuffle(inv_pool)
        for base in inv_pool[:3]:
            try:
                r = requests.get(f"{base}/api/v1/videos/{vid}", timeout=2.6)
                if r.ok:
                    for f in (r.json().get("adaptiveFormats") or []):
                        mime = f.get("type") or ""
                        if ("audio/mp4" in mime or "audio/webm" in mime) and f.get("url"):
                            res = {"url": f["url"], "source": "STREAM FULL", "videoId": vid}
                            AUDIO_CACHE[cache_key] = res
                            return jsonify(res)
            except Exception:
                continue

        piped_pool = list(PIPED_INSTANCES)
        random.shuffle(piped_pool)
        for base in piped_pool[:3]:
            try:
                r = requests.get(f"{base}/streams/{vid}", timeout=2.6)
                if r.ok:
                    for f in (r.json().get("audioStreams") or []):
                        if f.get("url"):
                            res = {"url": f["url"], "source": "STREAM FULL", "videoId": vid}
                            AUDIO_CACHE[cache_key] = res
                            return jsonify(res)
            except Exception:
                continue

    # 4. Jamendo Full Track Fallback
    if q:
        jam_hits = search_jamendo_tracks(q, 2)
        if jam_hits and jam_hits[0].get("directAudio"):
            res = {"url": jam_hits[0]["directAudio"], "source": "JAMENDO FULL"}
            AUDIO_CACHE[cache_key] = res
            return jsonify(res)

    # 5. iTunes Preview Terakhir
    if q:
        try:
            ir = requests.get(
                "https://itunes.apple.com/search",
                params={"term": q, "media": "music", "entity": "song", "limit": 1, "country": "ID"},
                timeout=2.4
            )
            if ir.ok:
                items = ir.json().get("results") or []
                if items and items[0].get("previewUrl"):
                    return jsonify({"url": items[0]["previewUrl"], "source": "PREVIEW CADANGAN"})
        except Exception:
            pass

    return jsonify({"error": "unavailable"}), 404

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

    return jsonify({"source": "fallback", "results": fallback_catalog(q or "global viral hits 2026", 16)})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
