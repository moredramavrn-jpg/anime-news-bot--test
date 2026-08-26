import requests
import time
import os

# Файл для сохранения списка
TOP_ANIME_FILE = "top_anime.txt"

# Стоп-слова для фильтрации спецвыпусков, фильмов, OVA и т.п.
BAD_SUBSTRINGS = [
    "спецвыпуск", "специальный", "фильм", "сезон", "часть", "ova", "ona",
    "спин-офф", "дополнение", "эпизод", "продолжение", "заключительная",
    "special", "movie", "season", "part", "ova", "ona", "episode", "final"
]

def clean_title(title):
    """
    Очищает название от подзаголовков, стоп-слов и лишних символов.
    Возвращает None, если название не подходит.
    """
    if not title:
        return None
    # Убираем подзаголовки после двоеточия, тире и т.п.
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
    # Убираем лишние пробелы
    title = ' '.join(title.split())
    return title

def fetch_shikimori_released(pages=2, limit=50):
    """
    Получает вышедшие аниме с Shikimori.
    Возвращает список названий.
    """
    names = []
    for page in range(1, pages + 1):
        url = "https://shikimori.one/api/animes"
        params = {
            "status": "released",
            "order": "ranked",
            "limit": limit,
            "page": page
        }
        try:
            r = requests.get(url, params=params, timeout=15)
            r.raise_for_status()
            data = r.json()
            for anime in data:
                # Приоритет русскому названию, затем английскому, затем оригинальному
                name = anime.get("russian") or anime.get("english") or anime.get("name")
                name = clean_title(name)
                if name:
                    names.append(name)
            print(f"Shikimori: получено страниц {page}")
            time.sleep(1)  # задержка
        except Exception as e:
            print(f"Ошибка Shikimori: {e}")
    return names

def fetch_jikan_finished(pages=2, limit=25):
    """
    Получает вышедшие аниме через Jikan API (MyAnimeList).
    Возвращает список названий.
    """
    names = []
    for page in range(1, pages + 1):
        url = "https://api.jikan.moe/v4/top/anime"
        params = {
            "limit": limit,
            "page": page,
            "filter": "bypopularity"  # можно изменить на "favorite" или не указывать
        }
        try:
            r = requests.get(url, params=params, timeout=15)
            r.raise_for_status()
            data = r.json()
            for anime in data.get("data", []):
                # Проверяем статус "Finished Airing"
                status = anime.get("status", "")
                if status != "Finished Airing":
                    continue
                # Берём английское название, иначе оригинальное
                title = anime.get("title_english") or anime.get("title")
                title = clean_title(title)
                if title:
                    names.append(title)
            print(f"Jikan: получена страница {page}")
            time.sleep(2)  # Jikan имеет ограничение 3 запроса/сек, лучше подождать
        except Exception as e:
            print(f"Ошибка Jikan: {e}")
    return names

def fetch_myanimelist_finished_via_jikan(pages=2, limit=25):
    """
    Дублирует Jikan, но с явным указанием, что это MyAnimeList.
    Можно использовать для резервирования или другого фильтра.
    """
    # По сути тот же Jikan, но можно добавить другие параметры
    return fetch_jikan_finished(pages, limit)

def save_to_file(names):
    """
    Сохраняет список уникальных названий в файл.
    """
    unique = list(dict.fromkeys(names))  # удаляем дубликаты, сохраняя порядок
    with open(TOP_ANIME_FILE, 'w', encoding='utf-8') as f:
        for name in unique:
            f.write(name + '\n')
    print(f"Сохранено {len(unique)} аниме в {TOP_ANIME_FILE}")

def main():
    all_names = []

    print("Сбор с Shikimori...")
    shiki = fetch_shikimori_released(pages=2)
    all_names.extend(shiki)

    print("Сбор с MyAnimeList (Jikan)...")
    jikan = fetch_jikan_finished(pages=2)
    all_names.extend(jikan)

    print("Сбор с Jikan (резервный)...")
    # Можно вызвать ещё раз с другим параметром, например, по рейтингу
    jikan2 = fetch_jikan_finished(pages=1, limit=25)
    all_names.extend(jikan2)

    # Дополнительная фильтрация уже проведена в clean_title
    save_to_file(all_names)

if __name__ == "__main__":
    main()
