from ytmusicapi import YTMusic

yt = YTMusic()

while True:
    query = input("\nCari lagu (atau ketik 'exit' untuk keluar): ").strip()
    if query.lower() == "exit":
        break
    if not query:
        continue

    hasil = yt.search(query, filter="songs", limit=5)
    print(f"\nHasil untuk '{query}':")
    print("-" * 40)

    for i, lagu in enumerate(hasil, 1):
        judul = lagu.get("title")
        artis = ", ".join([a["name"] for a in lagu.get("artists", [])])
        durasi = lagu.get("duration", "-")
        video_id = lagu.get("videoId")
        print(f"{i}. {judul} - {artis} [{durasi}]")
        print(f"   Link: https://music.youtube.com/watch?v={video_id}")
