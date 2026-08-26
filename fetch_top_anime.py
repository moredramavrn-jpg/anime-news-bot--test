import requests
import time
import os
import re
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

TOP_ANIME_FILE = "top_anime.txt"

# Стоп-слова для фильтрации нежелательных тайтлов
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
    """
    Очищает название: убирает подзаголовки, сезоны, спецвыпуски.
    Пример: 'Гинтама 7' -> 'Гинтама', 'Вольный стиль! Вечное лето — Спецвыпуск' -> 'Вольный стиль! Вечное лето'
    Возвращает None, если название не подходит.
    """
    if not title:
        return None

    # Убираем подзаголовки после двоеточия, длинного тире и т.п.
    for sep in [':', '—', ' - ', ' – ']:
        if sep in title:
            title = title.split(sep)[0].strip()
            break

    # Убираем номер сезона/сиквела в конце (например, "Гинтама 7" -> "Гинтама")
    title = re.sub(r'(\s|-)\d+$', '', title).strip()

    if len(title) < 2:
        return None

    lower = title.lower()
    for bad in BAD_SUBSTRINGS:
        if bad in lower:
            return None

    # Убираем лишние пробелы
    title = ' '.join(title.split())
    return title

def fetch_shikimori_released(total_pages=20, limit=50):
    """
    Собирает вышедшие аниме с Shikimori.
    Возвращает список названий.
    """
    names = []
    session = requests_retry_session()
    url = "https://shikimori.one/api/animes"
    params = {
        "order": "ranked",
        "kind": "tv,movie,ova,ona,special",  # все типы
        "status": "released",
        "rating": "g,pg,pg_13,r,r_plus",     # все рейтинги
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
                print(f"Shikimori: страница {page} пуста, прекращаем.")
                break
            for anime in data:
                name = anime.get("russian") or anime.get("english") or anime.get("name")
                name = clean_title(name)
                if name:
                    names.append(name)
            print(f"Shikimori: получена страница {page} ({len(data)} записей)")
            time.sleep(1)  # щадящая задержка
        except Exception as e:
            print(f"Ошибка Shikimori на странице {page}: {e}")
            # Пробуем следующую страницу после ошибки
            time.sleep(2)
            continue
    return names

def fetch_jikan_finished(pages=3, limit=25):
    """
    Дополнительный сбор с MyAnimeList через Jikan API.
    Возвращает список названий только со статусом 'Finished Airing'.
    """
    names = []
    session = requests_retry_session()
    url = "https://api.jikan.moe/v4/top/anime"
    params = {
        "limit": limit,
        "page": 1,
        "filter": "bypopularity"
    }
    for page in range(1, pages + 1):
        params["page"] = page
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
            print(f"Jikan: получена страница {page}")
            time.sleep(2)  # Jikan имеет жёсткие лимиты
        except Exception as e:
            print(f"Ошибка Jikan на странице {page}: {e}")
            time.sleep(3)
            continue
    return names

def save_to_file(names, max_count=1000):
    """
    Сохраняет уникальные названия в файл, ограничивая количество max_count.
    """
    # Удаляем дубликаты, сохраняя порядок
    unique = []
    seen = set()
    for name in names:
        key = name.lower()
        if key not in seen:
            seen.add(key)
            unique.append(name)
            if len(unique) >= max_count:
                break

    with open(TOP_ANIME_FILE, 'w', encoding='utf-8') as f:
        for name in unique:
            f.write(name + '\n')
    print(f"Сохранено {len(unique)} аниме в {TOP_ANIME_FILE}")

def main():
    all_names = []

    print("=== Сбор с Shikimori ===")
    shiki_names = fetch_shikimori_released(total_pages=20, limit=50)
    all_names.extend(shiki_names)
    print(f"Shikimori: всего {len(shiki_names)} названий")

    print("\n=== Сбор с MyAnimeList (Jikan) ===")
    jikan_names = fetch_jikan_finished(pages=3, limit=25)
    all_names.extend(jikan_names)
    print(f"Jikan: всего {len(jikan_names)} названий")

    print("\n=== Сохранение результата ===")
    save_to_file(all_names, max_count=1000)

if __name__ == "__main__":
    main()
