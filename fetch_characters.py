import requests
import time
import os

CHARACTERS_FILE = "characters.txt"
JIKAN_URL = "https://api.jikan.moe/v4/top/characters"
LIMIT = 500   # сколько персонажей сохранить

def fetch_characters():
    characters = []
    page = 1
    while len(characters) < LIMIT:
        params = {
            "page": page,
            "limit": min(25, LIMIT - len(characters))
        }
        try:
            r = requests.get(JIKAN_URL, params=params, timeout=15)
            r.raise_for_status()
            data = r.json()
            for item in data.get("data", []):
                name = item.get("name")
                # Ищем первое аниме, в котором участвует персонаж
                anime_name = ""
                if item.get("anime") and len(item["anime"]) > 0:
                    anime_name = item["anime"][0]["anime"]["title"]
                image_url = item.get("images", {}).get("jpg", {}).get("image_url", "")
                if name and image_url:
                    characters.append({
                        "name": name,
                        "anime": anime_name,
                        "image_url": image_url
                    })
            if not data.get("data"):
                break
            page += 1
            time.sleep(1)   # Jikan ограничивает запросы
        except Exception as e:
            print(f"Ошибка получения персонажей: {e}")
            break
    return characters[:LIMIT]

def save_characters(characters):
    with open(CHARACTERS_FILE, 'w', encoding='utf-8') as f:
        for ch in characters:
            f.write(f"{ch['name']}|{ch['anime']}|{ch['image_url']}\n")
    print(f"Сохранено {len(characters)} персонажей в {CHARACTERS_FILE}")

def main():
    print("Получаю популярных персонажей с Jikan...")
    chars = fetch_characters()
    if chars:
        save_characters(chars)
    else:
        print("Не удалось получить персонажей")

if __name__ == "__main__":
    main()
