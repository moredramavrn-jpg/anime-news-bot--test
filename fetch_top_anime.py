import requests
import re
import os

POPULAR_ANIME_FILE = "popular_anime.txt"
MAX_POPULAR = 100   # сколько популярных аниме сохранить

GRAPHQL_URL = "https://shikimori.one/api/graphql"
HEADERS = {
    "User-Agent": "AnimePopularFetcher/1.0",   # имя приложения, как требует Shikimori
    "Content-Type": "application/json",
    "Accept": "application/json"
}

def clean_title(title):
    """
    Убирает подзаголовки, сезоны, римские цифры и т.п.
    Двоеточие не используется для обрезки, так как может быть частью названия.
    """
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

    # Убираем номер сезона/части в конце: "3. Часть", "3 Season" и т.п.
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

    return ' '.join(title.split())

def fetch_popular_anime_graphql():
    """
    Получает топ популярных завершённых TV-сериалов через GraphQL Shikimori.
    Возвращает список очищенных названий.
    """
    query = """
    query ($page: Int, $limit: Int) {
      animes(page: $page, limit: $limit, order: popularity, kind: "tv", status: "released") {
        name
        russian
        english
      }
    }
    """

    variables = {
        "page": 1,
        "limit": MAX_POPULAR
    }

    try:
        response = requests.post(
            GRAPHQL_URL,
            json={"query": query, "variables": variables},
            headers=HEADERS,
            timeout=20
        )
        response.raise_for_status()
        data = response.json()

        if "errors" in data:
            print(f"Ошибки GraphQL: {data['errors']}")
            return []

        animes = data.get("data", {}).get("animes", [])
        names = []
        for anime in animes:
            name = anime.get("russian") or anime.get("english") or anime.get("name")
            name = clean_title(name)
            if name:
                names.append(name)
        return names

    except Exception as e:
        print(f"Ошибка получения данных с Shikimori GraphQL: {e}")
        return []

def save_to_file(names):
    """
    Сохраняет уникальные названия в popular_anime.txt.
    """
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
    print("Получение популярных аниме с Shikimori GraphQL...")
    names = fetch_popular_anime_graphql()
    if not names:
        print("Не удалось получить список")
        return
    save_to_file(names)

if __name__ == "__main__":
    main()
