import os
import json
import re
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
        "2. Ровно 3 лучшие работы, КАЖДАЯ С НОВОЙ СТРОКИ и с тире в начале.\n"
        "Формат строго:\n"
        "Биография: <текст>\n"
        "Работы:\n"
        "- Название — описание\n"
        "- Название — описание\n"
        "- Название — описание\n"
        "Не пиши работы в одну строку."
    )
    result = giga_request(prompt, max_tokens=700)
    return result if result else ""

def parse_person_info(content):
    bio = ""
    works = []
    lines = content.split('\n')
    mode = None
    for line in lines:
        line = line.strip()
        if line.startswith("Биография:"):
            bio = line.replace("Биография:", "").strip()
            mode = "bio"
        elif line.startswith("Работы:"):
            mode = "works"
        elif mode == "works":
            if re.match(r'^[-–—•]', line):
                work = re.sub(r'^[-–—•]\s*', '', line)
                if work:
                    works.append(work)
            elif line and (' — ' in line or ' – ' in line):
                works.append(line)
    return bio, works

def truncate_post(text, max_len=900):
    if len(text) <= max_len:
        return text
    sentences = re.split(r'(?<=[.!?])\s+', text)
    result = ""
    for s in sentences:
        if len(result) + len(s) + 1 > max_len:
            break
        result = (result + " " + s).strip()
    return result

def get_commons_image(person):
    try:
        url = "https://commons.wikimedia.org/w/api.php"
        headers = {"User-Agent": "AnimeDirectorBot/1.0"}
        params = {
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrsearch": f"{person} portrait",
            "gsrlimit": 5,
            "prop": "imageinfo",
            "iiprop": "url",
            "iiurlwidth": 500
        }
        r = requests.get(url, params=params, headers=headers, timeout=15)
        r.raise_for_status()
        data = r.json()
        pages = data.get("query", {}).get("pages", {})
        for page_id, page in pages.items():
            imageinfo = page.get("imageinfo", [])
            if imageinfo:
                img_url = imageinfo[0].get("thumburl") or imageinfo[0].get("url")
                if img_url and re.search(r'\.(jpg|jpeg|png)', img_url, re.IGNORECASE):
                    return img_url
        return ""
    except Exception as e:
        print(f"Ошибка Commons: {e}")
        return ""

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
                "piprop": "thumbnail",
                "pithumbsize": 500
            }
            r2 = requests.get(url, params=image_params, headers=headers, timeout=15)
            r2.raise_for_status()
            data2 = r2.json()
            pages = data2.get("query", {}).get("pages", {})
            for page_id, page in pages.items():
                thumbnail = page.get("thumbnail", {})
                if thumbnail:
                    return thumbnail.get("source", "")
        return ""
    except Exception as e:
        print(f"Ошибка {lang} Википедии: {e}")
        return ""

def get_person_image(person):
    photo = get_commons_image(person)
    if photo:
        return photo
    photo = get_wiki_image(person, "en")
    if photo:
        return photo
    photo = get_wiki_image(person, "ru")
    if photo:
        return photo
    return ""

def download_image(url, retries=3):
    for attempt in range(retries):
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            r = requests.get(url, headers=headers, timeout=20)
            if r.status_code == 429:
                print(f"429, попытка {attempt+1}, ждём 5 сек...")
                time.sleep(5)
                continue
            r.raise_for_status()
            return r.content
        except Exception as e:
            print(f"Ошибка скачивания: {e}")
            time.sleep(3)
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

    caption = truncate_post(post, 900)

    photo_url = get_person_image(person)
    if photo_url:
        photo_bytes = download_image(photo_url)
        if photo_bytes:
            bot.send_photo(CHANNEL_ID, photo_bytes, caption=caption, parse_mode='HTML')
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
