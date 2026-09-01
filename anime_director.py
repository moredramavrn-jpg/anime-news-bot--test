import os
import json
import uuid
import time
import urllib3
import telebot
import requests

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
GIGACHAT_AUTHORIZATION_KEY = os.getenv("GIGACHAT_AUTHORIZATION_KEY")

USED_PERSONS_FILE = "used_persons.json"

bot = telebot.TeleBot(TELEGRAM_TOKEN)

gigachat_access_token = None
gigachat_token_expires_at = 0

def get_gigachat_token():
    # ... (как раньше) ...
    pass

def giga_request(prompt, max_tokens=500):
    # ... (как раньше) ...
    pass

def load_used_persons():
    if os.path.exists(USED_PERSONS_FILE):
        with open(USED_PERSONS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_used_persons(persons):
    with open(USED_PERSONS_FILE, 'w', encoding='utf-8') as f:
        json.dump(persons, f, ensure_ascii=False)

def get_person():
    used = load_used_persons()
    if used:
        prompt = "Назови случайного известного режиссёра или мангаку аниме, которого нет в списке: " + ", ".join(used) + ".\nВыведи только имя."
    else:
        prompt = "Назови случайного известного режиссёра или мангаку аниме.\nВыведи только имя."
    return giga_request(prompt, max_tokens=50).strip()

def get_person_info(person):
    prompt = (
        f"Расскажи о {person}:\n"
        "1. Краткая биография (2-3 предложения).\n"
        "2. Ровно 3 лучшие работы с кратким описанием.\n"
        "Формат:\n"
        "Биография: <текст>\n"
        "Работы:\n"
        "- Название — описание\n"
        "- Название — описание\n"
        "- Название — описание"
    )
    return giga_request(prompt, max_tokens=700)

def parse_person_info(content):
    bio = ""
    works = []
    mode = None
    for line in content.split('\n'):
        line = line.strip()
        if line.startswith("Биография:"):
            bio = line.replace("Биография:", "").strip()
            mode = "bio"
        elif line.startswith("Работы:"):
            mode = "works"
        elif mode == "works" and line.startswith("- "):
            work = line[2:].strip()
            if work:
                works.append(work)
    return bio, works

def get_person_image_wikipedia(person):
    try:
        search_url = "https://ru.wikipedia.org/w/api.php"
        params = {
            "action": "query",
            "format": "json",
            "list": "search",
            "srsearch": person,
            "srlimit": 1
        }
        r = requests.get(search_url, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        search_results = data.get("query", {}).get("search", [])
        if not search_results:
            return ""
        page_title = search_results[0]["title"]

        image_params = {
            "action": "query",
            "format": "json",
            "titles": page_title,
            "prop": "pageimages",
            "piprop": "original"
        }
        r2 = requests.get(search_url, params=image_params, timeout=15)
        r2.raise_for_status()
        data2 = r2.json()
        pages = data2.get("query", {}).get("pages", {})
        for page_id, page in pages.items():
            original = page.get("original", {})
            if original:
                return original.get("source", "")
        return ""
    except Exception as e:
        print(f"Ошибка Википедии: {e}")
        return ""

def download_image(url):
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        return r.content
    except Exception as e:
        print(f"Ошибка скачивания: {e}")
        return None

def main():
    person = get_person()
    if not person:
        print("Не удалось получить имя")
        return

    info = get_person_info(person)
    bio, works = parse_person_info(info)

    header = "🎬 <b>Рубрика: о режиссёрах аниме</b>\n\n"
    name_line = f"<b>{person}</b>\n"
    separator = "┄┄┄ ✦ ┄┄┄\n"

    post = header + name_line + separator
    if bio:
        post += f"{bio}\n\n"
    if works:
        post += "<b>Среди лучших работ:</b>\n"
        for work in works[:3]:
            post += f"\n— {work}\n"
    post += "\n#аниме #режиссёр #мангака"

    photo_url = get_person_image_wikipedia(person)
    if photo_url:
        photo_bytes = download_image(photo_url)
        if photo_bytes:
            bot.send_photo(CHANNEL_ID, photo_bytes, caption=post[:1024], parse_mode='HTML')
            print("Пост с фото опубликован.")
        else:
            bot.send_message(CHANNEL_ID, post, parse_mode='HTML', disable_web_page_preview=True)
            print("Пост без фото опубликован.")
    else:
        bot.send_message(CHANNEL_ID, post, parse_mode='HTML', disable_web_page_preview=True)
        print("Пост без фото опубликован.")

    persons = load_used_persons()
    persons.append(person)
    save_used_persons(persons)

if __name__ == "__main__":
    main()
