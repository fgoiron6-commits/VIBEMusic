from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from ytmusicapi import YTMusic

app = Flask(__name__, static_folder="public")
CORS(app)
yt = YTMusic()

def format_tracks(raw_list):
    results = []
    for item in raw_list:
        video_id = item.get("videoId")
        if not video_id:
            continue
        thumbs = item.get("thumbnails", [])
        cover = thumbs[-1]["url"] if thumbs else ""
        # Tingkatkan resolusi thumbnail YouTube jika memungkinkan
        if "w120-h120" in cover:
            cover = cover.replace("w120-h120", "w544-h544")
        elif "w60-h60" in cover:
            cover = cover.replace("w60-h60", "w544-h544")
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

@app.route("/")
def index():
    return send_from_directory("public", "index.html")

@app.route("/api/home")
def home_feed():
    try:
        quick_picks = format_tracks(yt.search("lagu pop indonesia terbaru hits", filter="songs", limit=12))
        trending = format_tracks(yt.search("top hits indonesia viral", filter="songs", limit=10))
        chill = format_tracks(yt.search("Tulus Nadin Amizah Hindia Daniel Caesar", filter="songs", limit=10))
        return jsonify({
            "quick_picks": quick_picks,
            "trending": trending,
            "chill": chill
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/search")
def search():
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"results": []})
    try:
        raw = yt.search(query, filter="songs", limit=20)
        return jsonify({"results": format_tracks(raw)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/lyrics/<video_id>")
def lyrics(video_id):
    try:
        watch = yt.get_watch_playlist(videoId=video_id)
        lyrics_id = watch.get("lyrics")
        if not lyrics_id:
            return jsonify({"lyrics": "Lirik tidak tersedia untuk lagu ini."})
        data = yt.get_lyrics(lyrics_id)
        return jsonify({"lyrics": data.get("lyrics", "Lirik kosong.")})
    except Exception:
        return jsonify({"lyrics": "Gagal memuat lirik."})

if __name__ == "__main__":
    print("YT Music Clone Server aktif di http://127.0.0.1:5000")
    app.run(host="0.0.0.0", port=5000)
