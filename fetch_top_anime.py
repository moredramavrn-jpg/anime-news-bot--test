import requests
import time
import os
import re
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

TOP_ANIME_FILE = "top_anime.txt"

BAD_SUBSTRINGS = [
    "спецвыпуск", "специальный", "фильм", "сезон", "часть", "ova", "ona",
    "спин-офф", "дополнение", "эпизод", "продолжение", "заключительная",
    "special", "movie", "season", "part", "ova", "ona", "episode", "final"
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
    """Расширенная очистка названия: убирает подзаголовки, стоп-слова, числовые/римские окончания."""
    if not title:
        return None
    # 1. Убираем подзаголовки после двоеточия, тире и т.п.
    for sep in [':', '—', ' - ', ' – ']:
        if sep in title:
            title = title.split(sep)[0].strip()
            break
    title = ' '.join(title.split())  # убираем лишние пробелы
    if len(title) < 2:
        return None

    # 2. Проверяем на стоп-слова
    lower = title.lower()
    for bad in BAD_SUBSTRINGS:
        if bad in lower:
            return None

    # 3. Отбрасываем, если последнее слово — число или римская цифра (типа "Гинтама 7", "Fate 3", "Naruto II")
    words = title.split()
    if len(words) >= 2:
        last = words[-1].lower()
        if re.fullmatch(r'\d+', last) or re.fullmatch(r'[ivxlcdm]+', last):
            return None
        if last in ["season", "cour", "part", "special", "movie", "ova", "ona", "final"]:
            return None

    return title

def fetch_shikimori_released(pages=20, limit=50):
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
            print(f"Shikimori: страница {page} получена, всего {len(names)} названий")
            time.sleep(0.5)
        except Exception as e:
            print(f"Ошибка Shikimori на странице {page}: {e}")
    return names

def fetch_jikan_finished(pages=20, limit=25, filter_type="bypopularity"):
    names = []
    session = requests_retry_session()
    for page in range(1, pages + 1):
        url = "https://api.jikan.moe/v4/top/anime"
        params = {
            "limit": limit,
            "page": page,
            "filter": filter_type
        }
        try:
            r = session.get(url, params=params, headers=HEADERS, timeout=20)
            r.raise_for_status()
            data = r.json()
            for anime in data.get("data", []):
                if anime.get("status") != "Finished Airing":
                    continue
                title = anime.get("title_english") or anime.get("title")
                title = clean_title(title)
                if title:
                    names.append(title)
            print(f"Jikan ({filter_type}): страница {page} получена, всего {len(names)} названий")
            time.sleep(2)
        except Exception as e:
            print(f"Ошибка Jikan на странице {page} ({filter_type}): {e}")
    return names

def save_to_file(names):
    unique = list(dict.fromkeys(names))  # удаляем дубликаты
    with open(TOP_ANIME_FILE, 'w', encoding='utf-8') as f:
        for name in unique:
            f.write(name + '\n')
    print(f"Сохранено {len(unique)} аниме в {TOP_ANIME_FILE}")

def main():
    all_names = []

    print("Сбор с Shikimori (released)...")
    all_names.extend(fetch_shikimori_released(pages=20, limit=50))

    print("Сбор с MyAnimeList через Jikan (bypopularity)...")
    all_names.extend(fetch_jikan_finished(pages=20, limit=25, filter_type="bypopularity"))

    print("Сбор с MyAnimeList через Jikan (favorite)...")
    all_names.extend(fetch_jikan_finished(pages=20, limit=25, filter_type="favorite"))

    save_to_file(all_names)

if __name__ == "__main__":
    main()
