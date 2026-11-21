from flask import Flask, request, jsonify
from flask_cors import CORS
from ytmusicapi import YTMusic
import requests

app = Flask(__name__)
CORS(app)

try:
    yt = YTMusic()
except Exception:
    yt = None

def fallback_catalog(query, limit=15):
    results = []
    # 1. Cadangan Audius (Full Track langsung)
    try:
        r = requests.get(
            "https://discoveryprovider.audius.co/v1/tracks/search",
            params={"query": query, "limit": min(limit, 10)},
            timeout=3.5
        )
        if r.ok:
            for item in r.json().get("data", []):
                tid = item.get("id")
                if not tid:
                    continue
                dur = int(item.get("duration") or 0)
                art = (item.get("artwork") or {}).get("480x480") or (item.get("artwork") or {}).get("150x150") or ""
                results.append({
                    "videoId": "",
                    "trackId": str(tid),
                    "title": item.get("title", "Unknown"),
                    "artist": (item.get("user") or {}).get("name", "Unknown Artist"),
                    "duration": f"{dur // 60}:{dur % 60:02d}",
                    "cover": art,
                    "directAudio": f"https://discoveryprovider.audius.co/v1/tracks/{tid}/stream"
                })
    except Exception:
        pass

    # 2. Cadangan iTunes (Metadata & Sampul HD)
    if len(results) < limit:
        try:
            r = requests.get(
                "https://itunes.apple.com/search",
                params={"term": query, "media": "music", "entity": "song", "limit": limit, "country": "ID"},
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
    return results[:limit]

@app.route("/api/search")
def search():
    q = (request.args.get("q") or "").strip()
    limit = int(request.args.get("limit") or 18)
    if not q:
        return jsonify({"results": []})

    # Jalur Utama: ytmusicapi
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
                return jsonify({"source": "ytmusicapi", "results": parsed})
        except Exception:
            pass

    # Jalur Cadangan otomatis jika IP cloud dibatasi YouTube
    return jsonify({"source": "fallback", "results": fallback_catalog(q, limit)})

@app.route("/api/related")
def related():
    vid = (request.args.get("videoId") or "").strip()
    q = (request.args.get("q") or "").strip()
    if yt and vid and len(vid) == 11:
        try:
            watch = yt.get_watch_playlist(videoId=vid, limit=15)
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
                return jsonify({"source": "ytmusicapi", "results": parsed})
        except Exception:
            pass
    return jsonify({"source": "fallback", "results": fallback_catalog(q or "indie pop mix", 15)})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
