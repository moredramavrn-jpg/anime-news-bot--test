import requests
import re

POPULAR_ANIME_FILE = "popular_anime.txt"
MAX_POPULAR = 100

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept": "application/json"
}

# Стоп-слова, которые указывают на фильмы, спецвыпуски, OVA и т.п.
BAD_SUBSTRINGS = [
    "спецвыпуск", "специальный", "фильм", "сезон", "часть", "ova", "ona",
    "спин-офф", "дополнение", "эпизод", "продолжение", "заключительная",
    "special", "movie", "season", "part", "episode", "final", "решающая игра"
]

def clean_title(title):
    if not title:
        return None

    # Обрезаем по "!! " (например, "Волейбол!! Решающая игра на свалке" -> "Волейбол!!")
    if '!! ' in title:
        title = title.split('!! ')[0] + '!!'

    # Убираем подзаголовки после длинного тире или дефиса с пробелами
    for sep in ['—', ' - ', ' – ']:
        if sep in title:
            title = title.split(sep)[0].strip()
            break

    # Убираем конструкцию "3. Часть", "3 Season" и т.п.
    title = re.sub(
        r'\s+\d+\.?\s*(?:часть|сезон|part|season|special|спецвыпуск)\s*$',
        '',
        title,
        flags=re.IGNORECASE
    ).strip()

    # Пропускаем названия с числом и точкой (например, "Евангелион 3.0+1.01")
    if re.search(r'\d\.\d', title):
        return None

    # Убираем просто номер сезона/сиквела в конце (арабские цифры)
    title = re.sub(r'(\s|-)\d+$', '', title).strip()

    # Убираем римские цифры в конце
    title = re.sub(
        r'(?:\s|-)M{0,4}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})$',
        '',
        title,
        flags=re.IGNORECASE
    ).strip()

    # Убираем обозначения кроссоверов/спецвыпусков
    title = re.sub(r'\s*[xх]\s*UT\s*$', '', title, flags=re.IGNORECASE).strip()

    if len(title) < 2:
        return None

    lower = title.lower()
    for bad in BAD_SUBSTRINGS:
        if bad in lower:
            return None

    return ' '.join(title.split())

def fetch_popular_from_shikimori():
    url = "https://shikimori.one/api/animes"
    params = {
        "order": "popularity",
        "kind": "tv",
        "status": "released",
        "limit": MAX_POPULAR,
        "page": 1
    }

    try:
        response = requests.get(url, params=params, headers=HEADERS, timeout=20)
        response.raise_for_status()
        data = response.json()
        names = []
        for anime in data:
            # Дополнительно убеждаемся, что формат именно TV
            if anime.get("kind") != "tv":
                continue
            name = anime.get("russian") or anime.get("english") or anime.get("name")
            name = clean_title(name)
            if name:
                names.append(name)
        return names
    except Exception as e:
        print(f"Ошибка получения данных с Shikimori: {e}")
        return []

def save_to_file(names):
    unique = []
    seen = set()
    for name in names:
        key = name.lower()
        if key not in seen:
            seen.add(key)
            unique.append(name)
            if len(unique) >= MAX_POPULAR:
                break

    with open(POPULAR_ANIME_FILE, 'w', encoding='utf-8') as f:
        for name in unique:
            f.write(name + '\n')
    print(f"Сохранено {len(unique)} популярных аниме в {POPULAR_ANIME_FILE}")

def main():
    print("Получение популярных аниме с Shikimori...")
    names = fetch_popular_from_shikimori()
    if not names:
        print("Не удалось получить список")
        return
    save_to_file(names)

if __name__ == "__main__":
    main()
