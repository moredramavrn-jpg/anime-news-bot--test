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
        print(f"Ошибка получения токена GigaChat: {e}")
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
                          headers=headers, json=payload, timeout=30, verify=False)
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
    return giga_request(prompt, max_tokens=50).strip()

def get_person_info(person):
    prompt = (
        f"Расскажи о {person}:\n"
        "1. Краткая биография (2-3 предложения).\n"
        "2. 3-4 лучшие работы с кратким описанием (по одной строке на каждую).\n"
        "Формат:\n"
        "Биография: <текст>\n"
        "Работы:\n"
        "- Название — описание\n"
        "- Название — описание\n"
        "- Название — описание"
    )
    content = giga_request(prompt, max_tokens=700)
    return content

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
        elif mode == "works" and line.startswith("- "):
            work = line[2:].strip()
            if work:
                works.append(work)

    return bio, works

def main():
    person = get_person()
    if not person:
        print("Не удалось получить имя")
        return

    info = get_person_info(person)
    if not info:
        print("Не удалось получить информацию")
        return

    bio, works = parse_person_info(info)

    header = "🎬 <b>Рубрика: о режиссёрах аниме</b>\n\n"
    name_line = f"🎬 <b>{person}</b>\n"
    separator = "┄┄┄ ✦ ┄┄┄\n"

    post = header + name_line + separator

    if bio:
        post += f"{bio}\n\n"

    if works:
        post += "<b>Среди лучших работ:</b>\n\n"
        for work in works[:4]:
            post += f"— {work}\n"

    post += "\n#аниме #режиссёр #мангака"

    bot.send_message(CHANNEL_ID, post, parse_mode='HTML', disable_web_page_preview=True)

    persons = load_used_persons()
    persons.append(person)
    save_used_persons(persons)

    print("Пост опубликован.")

if __name__ == "__main__":
    main()
