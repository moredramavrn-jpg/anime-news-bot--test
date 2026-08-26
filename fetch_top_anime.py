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

def requests_retry_session(
    retries=3,
    backoff_factor=1,
    status_forcelist=(500, 502, 503, 504),
    session=None,
):
    session = session or requests.Session()
    retry = Retry(
        total=retries,
        read=retries,
        connect=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

def clean_title(title):
    if not title:
        return None
    for sep in [':', '—', ' - ', ' – ']:
        if sep in title:
            title = title.split(sep)[0].strip()
            break
    title = re.sub(r'(\s|-)\d+$', '', title).strip()
    if len(title) < 2:
        return None
    lower = title.lower()
    for bad in BAD_SUBSTRINGS:
        if bad in lower:
            return None
    title = ' '.join(title.split())
    return title

def fetch_shikimori_released(total_pages=TOTAL_PAGES, limit=LIMIT_PER_PAGE):
    """
    Собирает вышедшие аниме с Shikimori.
    Возвращает список кортежей: (название, жанры, количество серий)
    """
    anime_data = []
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
                if not name:
                    continue

                # Жанры
                genres = []
                for g in anime.get("genres", []):
                    genre_name = g.get("russian") or g.get("name")
                    if genre_name:
                        genres.append(genre_name)
                genres_str = ", ".join(genres)

                # Количество серий (эпизодов)
                episodes = anime.get("episodes")
                if episodes is None:
                    episodes_str = "?"   # если неизвестно, можно оставить "?"
                else:
                    episodes_str = str(episodes)

                anime_data.append((name, genres_str, episodes_str))

            print(f"Shikimori: получена страница {page} ({len(data)} записей)")
            time.sleep(1)
        except Exception as e:
            print(f"Ошибка Shikimori на странице {page}: {e}")
            time.sleep(2)
            continue
    return anime_data

def save_to_file(anime_data):
    """
    Сохраняет уникальные записи в файл в формате:
    Название|Жанры|Количество серий
    """
    unique = []
    seen = set()
    for name, genres, episodes in anime_data:
        key = name.lower()
        if key not in seen:
            seen.add(key)
            unique.append((name, genres, episodes))
            if len(unique) >= MAX_ANIME:
                break

    with open(TOP_ANIME_FILE, 'w', encoding='utf-8') as f:
        for name, genres, episodes in unique:
            f.write(f"{name}|{genres}|{episodes}\n")
    print(f"Сохранено {len(unique)} аниме в {TOP_ANIME_FILE}")

def main():
    print(f"=== Сбор с Shikimori (до {TOTAL_PAGES} страниц) ===")
    anime_data = fetch_shikimori_released()
    print(f"Shikimori: собрано {len(anime_data)} записей до дедупликации")
    save_to_file(anime_data)

if __name__ == "__main__":
    main()
