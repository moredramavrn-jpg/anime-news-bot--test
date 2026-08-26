import requests
import re

url = "https://shikimori.one/api/animes"
params = {
    "order": "ranked",
    "kind": "tv,movie,ova,ona,special",
    "status": "released",
    "rating": "g,pg,pg_13,r,pg_13,r_plus",
    "limit": 50,
    "page": 1,
}

headers = {"User-Agent": "AnimeTopFetcher/1.0"}

# Слова, которые указывают на сиквел/фильм/спешл/часть
BAD_SUBSTRINGS = [
    "фильм", "спешл", "специальный", "ova", "ona", "сезон", "часть",
    "2", "3", "4", "5", "6", "7", "8", "9", "0",
    "продолжение", "заключительная", "спин-офф", "дополнение", "эпизод"
]

def is_bad_title(title):
    """Проверяет, является ли название не базовым (сиквел, фильм и т.п.)."""
    lower = title.lower()
    # Убираем названия, содержащие подозрительные слова
    for bad in BAD_SUBSTRINGS:
        if bad in lower:
            return True
    return False

def clean_title(title):
    """
    Оставляет только базовое название.
    Например: 'Магическая битва: Смертельная миграция' -> 'Магическая битва'
    """
    if ':' in title:
        title = title.split(':')[0].strip()
    if '.' in title:
        # Отрезаем часть после точки, если она короткая (типа "Фильм", "2")
        parts = title.split('.')
        if len(parts) > 1 and len(parts[-1].strip()) < 20:
            title = '.'.join(parts[:-1]).strip()
    return title

names = []
seen_base_names = set()

for page in range(1, 21):
    params["page"] = page
    resp = requests.get(url, params=params, headers=headers)
    resp.raise_for_status()
    data = resp.json()
    if not data:
        break
    for anime in data:
        ru = anime.get("russian") or anime.get("name") or anime.get("english") or ""
        if not ru:
            continue
        ru = ru.strip()
        if is_bad_title(ru):
            continue
        ru = clean_title(ru)
        if len(ru) < 3:
            continue
        key = ru.lower()
        if key not in seen_base_names:
            seen_base_names.add(key)
            names.append(ru)

with open("top_anime.txt", "w", encoding="utf-8") as f:
    for name in names[:1000]:
        f.write(name + "\n")

print(f"Сохранено {len(names[:1000])} аниме в top_anime.txt")
