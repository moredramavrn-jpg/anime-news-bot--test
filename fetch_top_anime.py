import requests
import time
import os
import re
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

TOP_ANIME_FILE = "top_anime.txt"
MAX_ANIME = 2000
TOTAL_PAGES = 80
LIMIT_PER_PAGE = 50

BAD_SUBSTRINGS = [
    "спецвыпуск", "специальный", "фильм", "сезон", "часть", "ova", "ona",
    "спин-офф", "дополнение", "эпизод", "продолжение", "заключительная",
    "special", "movie", "season", "part", "episode", "final"
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept": "application/json"
}

def requests_retry_session(...):  # без изменений
    ...

def clean_title(title):
    ...  # без изменений

def fetch_shikimori_released(total_pages=TOTAL_PAGES, limit=LIMIT_PER_PAGE):
    names = []
    session = requests_retry_session()
    url = "https://shikimori.one/api/animes"
    params = {
        "order": "ranked",
        "kind": "tv,movie,ova,ona,special",
        "status": "released",
        "rating": "g,pg,pg_13,r,r_plus",
        "limit": limit,
        "page": 1,
    }

    for page in range(1, total_pages + 1):
        params["page"] = page
        try:
            r = session.get(url, params=params, headers=HEADERS, timeout=20)
            r.raise_for_status()
            data = r.json()
            if not data:
                print(f"Shikimori: страница {page} пуста, останавливаемся.")
                break
            for anime in data:
                name = anime.get("russian") or anime.get("english") or anime.get("name")
                name = clean_title(name)
                if name:
                    names.append(name)
            print(f"Shikimori: получена страница {page} ({len(data)} записей)")
            time.sleep(1)
        except Exception as e:
            print(f"Ошибка Shikimori на странице {page}: {e}")
            time.sleep(2)
            continue
    return names

def save_to_file(names):
    unique = []
    seen = set()
    for name in names:
        key = name.lower()
        if key not in seen:
            seen.add(key)
            unique.append(name)
            if len(unique) >= MAX_ANIME:
                break

    with open(TOP_ANIME_FILE, 'w', encoding='utf-8') as f:
        for name in unique:
            f.write(name + '\n')
    print(f"Сохранено {len(unique)} аниме в {TOP_ANIME_FILE}")

def main():
    print(f"=== Сбор с Shikimori (до {TOTAL_PAGES} страниц) ===")
    names = fetch_shikimori_released()
    print(f"Shikimori: собрано {len(names)} названий до дедупликации")
    save_to_file(names)

if __name__ == "__main__":
    main()
