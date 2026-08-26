import requests
import time
import os
import re
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

TOP_ANIME_FILE = "top_anime.txt"
POPULAR_ANIME_FILE = "popular_anime.txt"
EXCLUDE_FILE = "exclude.txt"   # файл с названиями для исключения (если нужен)
MAX_ANIME = 2000
MAX_POPULAR = 150              # количество популярных аниме для загадок
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

def load_exclude_list():
    exclude = set()
    if os.path.exists(EXCLUDE_FILE):
        with open(EXCLUDE_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                name = line.strip().lower()
                if name:
                    exclude.add(name)
    return exclude

def clean_title(title, exclude_set):
    if not title:
        return None

    for sep in [':', '—', ' - ', ' – ']:
        if sep in title:
            title = title.split(sep)[0].strip()
            break

    # убираем номер сезона/сиквела в конце (арабские цифры)
    title = re.sub(r'(\s|-)\d+$', '', title).strip()

    # убираем римские цифры в конце
    title = re.sub(
        r'(?:\s|-)M{0,4}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})$',
        '',
        title,
        flags=re.IGNORECASE
    ).strip()

    # убираем обозначения кроссоверов/спецвыпусков
    title = re.sub(r'\s*[xх]\s*UT\s*$', '', title, flags=re.IGNORECASE).strip()

    if len(title) < 2:
        return None

    lower = title.lower()
    if lower in exclude_set:
        return None

    for bad in BAD_SUBSTRINGS:
        if bad in lower:
            return None

    title = ' '.join(title.split())
    return title

def fetch_shikimori_released(total_pages=TOTAL_PAGES, limit=LIMIT_PER_PAGE, exclude_set=None):
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

    if exclude_set is None:
        exclude_set = set()

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
                name = clean_title(name, exclude_set)
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

def save_popular(names, max_popular=MAX_POPULAR):
    """Сохраняет первые max_popular названий (по рейтингу Shikimori)."""
    unique = []
    seen = set()
    for name in names:
        key = name.lower()
        if key not in seen:
            seen.add(key)
            unique.append(name)
            if len(unique) >= max_popular:
                break

    with open(POPULAR_ANIME_FILE, 'w', encoding='utf-8') as f:
        for name in unique:
            f.write(name + '\n')
    print(f"Сохранено {len(unique)} популярных аниме в {POPULAR_ANIME_FILE}")

def main():
    exclude_set = load_exclude_list()
    print(f"Загружено исключений: {len(exclude_set)}")

    print(f"=== Сбор с Shikimori (до {TOTAL_PAGES} страниц) ===")
    names = fetch_shikimori_released(total_pages=TOTAL_PAGES, limit=LIMIT_PER_PAGE, exclude_set=exclude_set)
    print(f"Shikimori: собрано {len(names)} названий до дедупликации")

    save_to_file(names)      # полный список
    save_popular(names)      # первые популярные

if __name__ == "__main__":
    main()
