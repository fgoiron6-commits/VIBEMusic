import requests
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from ytmusicapi import YTMusic

app = Flask(__name__, static_folder="public")
CORS(app)
yt = YTMusic()

def search_itunes_fallback(query, limit=15):
    url = "https://itunes.apple.com/search"
    params = {"term": query, "media": "music", "entity": "song", "limit": limit, "country": "ID"}
    res = requests.get(url, params=params, timeout=8).json()
    results = []
    for item in res.get("results", []):
        cover = item.get("artworkUrl100", "").replace("100x100bb", "500x500bb")
        ms = item.get("trackTimeMillis", 0)
        mins, secs = divmod(ms // 1000, 60)
        # Cari videoId YouTube ringan via Piped/Invidious atau pakai previewUrl
        results.append({
            "videoId": str(item.get("trackId")),
            "title": item.get("trackName", "Unknown"),
            "artist": item.get("artistName", "Unknown Artist"),
            "album": item.get("collectionName", "Single"),
            "duration": f"{mins}:{secs:02d}",
            "cover": cover,
            "audioUrl": item.get("previewUrl", "")
        })
    return results

def format_yt_tracks(raw_list):
    results = []
    for item in raw_list:
        video_id = item.get("videoId")
        if not video_id:
            continue
        thumbs = item.get("thumbnails", [])
        cover = thumbs[-1]["url"] if thumbs else ""
        cover = cover.replace("w120-h120", "w544-h544").replace("w60-h60", "w544-h544")
        artists = ", ".join([a["name"] for a in item.get("artists", [])])
        album_obj = item.get("album")
        album = album_obj.get("name", "Single") if isinstance(album_obj, dict) else "Single"
        results.append({
            "videoId": video_id,
            "title": item.get("title", "Unknown"),
            "artist": artists or "Unknown Artist",
            "album": album,
            "duration": item.get("duration", "3:30"),
            "cover": cover
        })
    return results

def safe_search(query, limit=15):
    try:
        raw = yt.search(query, filter="songs", limit=limit)
        formatted = format_yt_tracks(raw)
        if formatted:
            return formatted
    except Exception:
        pass
    return search_itunes_fallback(query, limit)

@app.route("/")
def index():
    return send_from_directory("public", "index.html")

@app.route("/api/home")
def home_feed():
    return jsonify({
        "quick_picks": safe_search("lagu pop indonesia terbaru hits", 12),
        "trending": safe_search("top hits indonesia viral", 10),
        "chill": safe_search("Tulus Nadin Amizah Hindia Daniel Caesar", 10)
    })

@app.route("/api/search")
def search():
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"results": []})
    return jsonify({"results": safe_search(query, 20)})

@app.route("/api/lyrics/<video_id>")
def lyrics(video_id):
    try:
        watch = yt.get_watch_playlist(videoId=video_id)
        lyrics_id = watch.get("lyrics")
        if lyrics_id:
            data = yt.get_lyrics(lyrics_id)
            if data.get("lyrics"):
                return jsonify({"lyrics": data["lyrics"]})
    except Exception:
        pass
    return jsonify({"lyrics": "Lirik tidak tersedia untuk lagu ini."})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
