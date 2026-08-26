import os
import re
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

ITEM_EMOJI = ["🌸", "⚡", "🔥", "💥", "🌟"]

def get_gigachat_token():
    # без изменений
    ...

def load_top_anime():
    if not os.path.exists(TOP_ANIME_FILE):
        print(f"Файл {TOP_ANIME_FILE} не найден")
        return []
    names = []
    with open(TOP_ANIME_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                names.append(line)
    return names

def load_used_anime():
    # без изменений
    ...

def save_used_anime(anime_set):
    # без изменений
    ...

def giga_request(prompt, token, max_tokens=300):
    # без изменений
    ...

def generate_anime_info(anime_name, token):
    """
    Запрашивает у GigaChat описание, жанр и количество серий.
    Возвращает кортеж (description, genres, episodes).
    """
    prompt = f"""Расскажи про аниме «{anime_name}»:
1. Дай описание в 2-3 предложениях.
2. Назови жанр(ы) через запятую.
3. Укажи общее количество серий (если точно неизвестно, поставь '?').

Выведи строго в формате:
Описание: <текст>
Жанр: <жанры>
Серии: <число или ?>

Не добавляй ничего лишнего."""
    content = giga_request(prompt, token, max_tokens=500)
    desc = ""
    genres = ""
    episodes = ""
    if "Описание:" in content:
        desc_part = content.split("Описание:")[1].split("\n")[0].strip()
        desc = desc_part
    if "Жанр:" in content:
        genres = content.split("Жанр:")[1].split("\n")[0].strip()
    if "Серии:" in content:
        episodes = content.split("Серии:")[1].strip()
    # Если что-то не распарсилось, используем отдельные запросы
    if not desc:
        desc = giga_request(f"Опиши аниме «{anime_name}» в 2-3 предложениях.", token, max_tokens=300)
    if not genres:
        genres = giga_request(f"Назови жанры аниме «{anime_name}» через запятую.", token, max_tokens=100)
    if not episodes:
        episodes = giga_request(f"Сколько всего серий в аниме «{anime_name}»? Если неизвестно, напиши '?'.", token, max_tokens=50)

    return desc, genres, episodes

def episodes_word(episodes):
    # без изменений
    ...

def generate_recommendations():
    all_anime = load_top_anime()
    if not all_anime:
        print("Список аниме пуст")
        return None

    used_anime = load_used_anime()

    available = [a for a in all_anime if a.lower() not in used_anime]
    if len(available) < 3:
        print("Недостаточно новых аниме, начинаем использовать повторы")
        available = all_anime

    chosen = random.sample(available, 3)

    token = get_gigachat_token()
    if not token:
        print("Не удалось получить токен GigaChat")
        return None

    cards = []
    for idx, name in enumerate(chosen):
        print(f"Обработка: {name}")
        desc, genres, episodes = generate_anime_info(name, token)

        if not desc:
            desc = "Описание отсутствует."
        genres_str = genres if genres else "жанр не указан"
        episodes_str = episodes_word(episodes) if episodes and episodes != "?" else "кол-во серий неизвестно"

        meta = f"{genres_str}, {episodes_str}"

        emoji = ITEM_EMOJI[idx % len(ITEM_EMOJI)]
        card = f"{emoji} <b>«{name}»</b> ({meta}) — {desc}"
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
