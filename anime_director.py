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
    global gigachat_access_token, gigachat_token_expires_at

    if gigachat_access_token and time.time() < gigachat_token_expires_at - 30:
        return gigachat_access_token

    url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
        "RqUID": str(uuid.uuid4()),
        "Authorization": f"Basic {GIGACHAT_AUTHORIZATION_KEY}"
    }
    data = {"scope": "GIGACHAT_API_PERS"}
    try:
        r = requests.post(url, headers=headers, data=data, timeout=15, verify=False)
        r.raise_for_status()
        token_data = r.json()
        gigachat_access_token = token_data.get("access_token")
        expires_at = token_data.get("expires_at")
        if expires_at:
            gigachat_token_expires_at = expires_at / 1000 if expires_at > 10**12 else expires_at
        else:
            gigachat_token_expires_at = time.time() + 1800
        return gigachat_access_token
    except Exception as e:
        print(f"Ошибка токена: {e}")
        return None

def giga_request(prompt, max_tokens=500):
    token = get_gigachat_token()
    if not token:
        return ""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-Request-ID": str(uuid.uuid4()),
        "X-Session-ID": str(uuid.uuid4()),
        "User-Agent": "AnimeDirectorBot/1.0"
    }
    payload = {
        "model": "GigaChat-3-Ultra",
        "messages": [
            {"role": "system", "content": "Ты — эксперт по аниме."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.5,
        "max_tokens": max_tokens
    }
    try:
        r = requests.post("https://api.giga.chat/v1/chat/completions",
                          headers=headers,
                          json=payload,
                          timeout=30,
                          verify=False)
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"Ошибка GigaChat: {e}")
        return ""

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
    result = giga_request(prompt, max_tokens=50)
    return result.strip() if result else ""

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
    result = giga_request(prompt, max_tokens=700)
    return result if result else ""

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

def get_wiki_image(person, lang):
    try:
        time.sleep(1)
        url = f"https://{lang}.wikipedia.org/w/api.php"
        headers = {"User-Agent": "AnimeDirectorBot/1.0"}
        params = {
            "action": "query",
            "format": "json",
            "list": "search",
            "srsearch": person,
            "srlimit": 5
        }
        r = requests.get(url, params=params, headers=headers, timeout=15)
        r.raise_for_status()
        data = r.json()
        results = data.get("query", {}).get("search", [])
        for res in results:
            page_title = res.get("title", "")
            time.sleep(1)
            image_params = {
                "action": "query",
                "format": "json",
                "titles": page_title,
                "prop": "pageimages",
                "piprop": "original"
            }
            r2 = requests.get(url, params=image_params, headers=headers, timeout=15)
            r2.raise_for_status()
            data2 = r2.json()
            pages = data2.get("query", {}).get("pages", {})
            for page_id, page in pages.items():
                original = page.get("original", {})
                if original:
                    return original.get("source", "")
        return ""
    except Exception as e:
        print(f"Ошибка {lang} Википедии: {e}")
        return ""

def get_anilist_image(person):
    query = """
    query ($search: String) {
      Staff(search: $search) {
        image {
          large
        }
      }
    }
    """
    variables = {"search": person}
    headers = {"Content-Type": "application/json", "User-Agent": "AnimeDirectorBot/1.0"}
    try:
        r = requests.post("https://graphql.anilist.co",
                          json={"query": query, "variables": variables},
                          headers=headers,
                          timeout=15)
        r.raise_for_status()
        data = r.json()
        return data.get("data", {}).get("Staff", {}).get("image", {}).get("large", "")
    except Exception as e:
        print(f"Ошибка AniList: {e}")
        return ""

def get_person_image(person):
    photo = get_wiki_image(person, "en")
    if photo:
        return photo
    photo = get_wiki_image(person, "ru")
    if photo:
        return photo
    photo = get_anilist_image(person)
    if photo:
        return photo
    return ""

def download_image(url):
    try:
        time.sleep(2)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        r = requests.get(url, headers=headers, timeout=20)
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

    photo_url = get_person_image(person)
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
