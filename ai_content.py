import os
import re
import html
import uuid
import time
import random
import urllib3
import telebot
import requests

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
GIGACHAT_AUTHORIZATION_KEY = os.getenv("GIGACHAT_AUTHORIZATION_KEY")

bot = telebot.TeleBot(TELEGRAM_TOKEN)

gigachat_access_token = None
gigachat_token_expires_at = 0

TOP_ANIME_FILE = "top_anime.txt"
USED_ANIME_FILE = "used_anime.txt"

# Эмодзи для пунктов
ITEM_EMOJI = ["🌸", "⚡", "🔥", "💥", "🌟"]

# Стоп-слова, указывающие на спецвыпуски, фильмы и т.п.
BAD_SUBSTRINGS = [
    "спецвыпуск", "специальный", "фильм", "сезон", "часть", "ova", "ona",
    "спин-офф", "дополнение", "эпизод", "продолжение", "заключительная"
]

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

def clean_anime_title(title):
    """
    Возвращает базовое название аниме, отбрасывая подзаголовки.
    Пример: 'Вольный стиль! Вечное лето — Спецвыпуск' -> 'Вольный стиль! Вечное лето'
    Если строка сама является только спецвыпуском, вернёт пустую строку.
    """
    for sep in [':', '—', ' - ', ' – ']:
        if sep in title:
            title = title.split(sep)[0].strip()
            break

    if len(title) < 2:
        return ""

    lower_title = title.lower()
    for bad in BAD_SUBSTRINGS:
        if bad in lower_title:
            return ""

    return title.strip()

def load_top_anime():
    if not os.path.exists(TOP_ANIME_FILE):
        print(f"Файл {TOP_ANIME_FILE} не найден")
        return []

    raw_names = []
    with open(TOP_ANIME_FILE, 'r', encoding='utf-8') as f:
        raw_names = [line.strip() for line in f if line.strip()]

    cleaned = []
    seen = set()
    for name in raw_names:
        clean = clean_anime_title(name)
        if not clean:
            continue
        key = clean.lower()
        if key not in seen:
            seen.add(key)
            cleaned.append(clean)

    print(f"Загружено {len(cleaned)} аниме после фильтрации.")
    return cleaned

def load_used_anime():
    if not os.path.exists(USED_ANIME_FILE):
        return set()
    with open(USED_ANIME_FILE, 'r', encoding='utf-8') as f:
        return {line.strip().lower() for line in f if line.strip()}

def save_used_anime(anime_set):
    anime_list = list(anime_set)
    with open(USED_ANIME_FILE, 'w', encoding='utf-8') as f:
        for name in anime_list:
            f.write(name + '\n')

def generate_description(anime_name, token):
    prompt = f"Опиши аниме «{anime_name}» в 2-3 предложениях на русском языке. Не добавляй название, только описание."
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-Request-ID": str(uuid.uuid4()),
        "X-Session-ID": str(uuid.uuid4()),
        "User-Agent": "AnimeContentBot/1.0"
    }
    payload = {
        "model": "GigaChat-3-Ultra",
        "messages": [
            {"role": "system", "content": "Ты — редактор аниме-канала. Ты пишешь описания аниме."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.6,
        "max_tokens": 300
    }
    try:
        response = requests.post(
            "https://api.giga.chat/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=30,
            verify=False
        )
        response.raise_for_status()
        data = response.json()
        desc = data["choices"][0]["message"]["content"].strip()
        # Убираем возможное название в начале
        desc = re.sub(r'^«[^»]+»\s*[—\-:]\s*', '', desc)
        # Принудительно делаем первую букву строчной
        if desc:
            desc = desc[0].lower() + desc[1:]
        return desc
    except Exception as e:
        print(f"Ошибка генерации описания для '{anime_name}': {e}")
        return ""

def generate_recommendations():
    all_anime = load_top_anime()
    if not all_anime:
        print("Список аниме пуст")
        return None

    used_anime = load_used_anime()

    available = [a for a in all_anime if a.lower() not in used_anime]
    if len(available) < 5:
        print("Недостаточно новых аниме, начинаем использовать повторы")
        available = all_anime

    chosen = random.sample(available, 5)

    token = get_gigachat_token()
    if not token:
        print("Не удалось получить токен GigaChat")
        return None

    cards = []
    for idx, name in enumerate(chosen):
        desc = generate_description(name, token)
        if not desc:
            print(f"Не удалось получить описание для '{name}'")
            return None
        emoji = ITEM_EMOJI[idx % len(ITEM_EMOJI)]
        # Формат: эмодзи название — описание (с длинным тире)
        card = f"{emoji} <b>{name}</b> — {desc}"
        if idx < len(chosen) - 1:
            card += "\n────────────────"
        cards.append(card)

    used_anime.update(chosen)
    save_used_anime(used_anime)

    return '\n'.join(cards)

def send_recommendation_post(cards):
    header = "✨ <b>Рубрика: аниме, которые стоит посмотреть</b>"
    message = f"{header}\n\n{cards}\n\n#аниме #рекомендации #чтопосмотреть"
    try:
        bot.send_message(CHANNEL_ID, message, parse_mode='HTML', disable_web_page_preview=True)
        print("Рекомендации опубликованы.")
    except Exception as e:
        print(f"Ошибка отправки: {e}")

def main():
    cards = generate_recommendations()
    if cards:
        send_recommendation_post(cards)
    else:
        print("Не удалось сгенерировать рекомендации.")

if __name__ == "__main__":
    main()
