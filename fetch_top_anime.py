import requests
import time
import os
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

TOP_ANIME_FILE = "top_anime.txt"

BAD_SUBSTRINGS = [
    "спецвыпуск", "специальный", "фильм", "сезон", "часть", "ova", "ona",
    "спин-офф", "дополнение", "эпизод", "продолжение", "заключительная",
    "special", "movie", "season", "part", "ova", "ona", "episode", "final"
]

# Общие заголовки, чтобы API не блокировали запросы
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
    """Создаёт сессию requests с повторными попытками при ошибках."""
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
    if len(title) < 2:
        return None
    lower = title.lower()
    for bad in BAD_SUBSTRINGS:
        if bad in lower:
            return None
    title = ' '.join(title.split())
    return title

def fetch_shikimori_released(pages=2, limit=50):
    names = []
    session = requests_retry_session()
    for page in range(1, pages + 1):
        url = "https://shikimori.one/api/animes"
        params = {
            "status": "released",
            "order": "ranked",
            "limit": limit,
            "page": page
        }
        try:
            r = session.get(url, params=params, headers=HEADERS, timeout=20)
            r.raise_for_status()
            data = r.json()
            for anime in data:
                name = anime.get("russian") or anime.get("english") or anime.get("name")
                name = clean_title(name)
                if name:
                    names.append(name)
            print(f"Shikimori: получена страница {page}")
            time.sleep(1)
        except Exception as e:
            print(f"Ошибка Shikimori на странице {page}: {e}")
    return names

def fetch_jikan_finished(pages=2, limit=25):
    names = []
    session = requests_retry_session()
    for page in range(1, pages + 1):
        url = "https://api.jikan.moe/v4/top/anime"
        params = {
            "limit": limit,
            "page": page,
            "filter": "bypopularity"
        }
        try:
            r = session.get(url, params=params, headers=HEADERS, timeout=20)
            r.raise_for_status()
            data = r.json()
            for anime in data.get("data", []):
                status = anime.get("status", "")
                if status != "Finished Airing":
                    continue
                title = anime.get("title_english") or anime.get("title")
                title = clean_title(title)
                if title:
                    names.append(title)
            print(f"Jikan: получена страница {page}")
            time.sleep(2)
        except Exception as e:
            print(f"Ошибка Jikan на странице {page}: {e}")
    return names

def fetch_myanimelist_finished_via_jikan(pages=2, limit=25):
    # Дополнительный вызов с другим фильтром (например, по рейтингу)
    names = []
    session = requests_retry_session()
    url = "https://api.jikan.moe/v4/top/anime"
    params = {
        "limit": limit,
        "page": 1,
        "filter": "favorite"  # или "airing", но мы потом отфильтруем по статусу
    }
    try:
        r = session.get(url, params=params, headers=HEADERS, timeout=20)
        r.raise_for_status()
        data = r.json()
        for anime in data.get("data", []):
            if anime.get("status") == "Finished Airing":
                title = anime.get("title_english") or anime.get("title")
                title = clean_title(title)
                if title:
                    names.append(title)
        print("MyAnimeList (Jikan favorite): получены данные")
    except Exception as e:
        print(f"Ошибка MyAnimeList (Jikan favorite): {e}")
    return names

def save_to_file(names):
    unique = list(dict.fromkeys(names))
    with open(TOP_ANIME_FILE, 'w', encoding='utf-8') as f:
        for name in unique:
            f.write(name + '\n')
    print(f"Сохранено {len(unique)} аниме в {TOP_ANIME_FILE}")

def main():
    all_names = []

    print("Сбор с Shikimori...")
    all_names.extend(fetch_shikimori_released(pages=2))

    print("Сбор с MyAnimeList (Jikan)...")
    all_names.extend(fetch_jikan_finished(pages=2))

    print("Дополнительный сбор с MyAnimeList (Jikan, фильтр favorite)...")
    all_names.extend(fetch_myanimelist_finished_via_jikan(pages=1, limit=25))

    save_to_file(all_names)

if __name__ == "__main__":
    main()
