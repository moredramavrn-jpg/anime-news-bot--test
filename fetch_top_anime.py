import requests

url = "https://shikimori.one/api/animes"
params = {
    "order": "ranked",
    "kind": "tv,movie,ova,ona,special",
    "status": "released",
    "rating": "g,pg,pg_13,r,pg_13,r_plus",  # без хентая
    "limit": 50,
    "page": 1,
}

headers = {"User-Agent": "AnimeTopFetcher/1.0"}

names = []
for page in range(1, 21):  # 20 страниц по 50 = до 1000
    params["page"] = page
    resp = requests.get(url, params=params, headers=headers)
    resp.raise_for_status()
    data = resp.json()
    if not data:
        break
    for anime in data:
        ru = anime.get("russian") or anime.get("name") or anime.get("english") or ""
        if ru:
            names.append(ru)

with open("top_anime.txt", "w", encoding="utf-8") as f:
    for name in names[:1000]:
        f.write(name + "\n")

print(f"Сохранено {len(names[:1000])} аниме в top_anime.txt")
