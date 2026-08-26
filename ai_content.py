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

def load_top_anime():
    if not os.path.exists(TOP_ANIME_FILE):
        print(f"Файл {TOP_ANIME_FILE} не найден")
        return []
    with open(TOP_ANIME_FILE, 'r', encoding='utf-8') as f:
        return [line.strip() for line in f if line.strip()]

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

def extract_section(text, name, next_name=None):
    """Извлекает описание для аниме с указанным названием."""
    # Ищем название в тексте (регистронезависимо)
    pos = text.lower().find(name.lower())
    if pos == -1:
        return ""
    start = pos + len(name)
    if next_name:
        next_pos = text.lower().find(next_name.lower(), start)
        if next_pos != -1:
            section = text[start:next_pos]
        else:
            section = text[start:]
    else:
        section = text[start:]
    # Убираем возможные тире, двоеточия и пробелы в начале
    section = section.strip()
    section = re.sub(r'^[—\-:]\s*', '', section)
    # Оставляем до 2-3 предложений
    sentences = re.split(r'(?<=[.!?])\s+', section)
    desc = ' '.join(sentences[:3])
    if desc:
        desc = desc[0].upper() + desc[1:]
    return desc

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
    anime_list = ", ".join(chosen)

    token = get_gigachat_token()
    if not token:
        print("Не удалось получить токен GigaChat")
        return None

    prompt = f"""Напиши краткие описания для следующих аниме: {anime_list}.

Для каждого аниме дай описание из 2-3 предложений на русском языке.
Не используй эмодзи, номера или маркированные списки.
Просто напиши описания подряд, разделяя их пустой строкой.

Выведи результат в формате:
Название аниме
Описание

Название аниме
Описание
...
"""
    system_msg = "Ты — редактор аниме-канала. Ты пишешь описания аниме точно по названиям из списка."

    for attempt in range(3):
        try:
            response = requests.post(
                "https://api.giga.chat/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "X-Request-ID": str(uuid.uuid4()),
                    "X-Session-ID": str(uuid.uuid4()),
                    "User-Agent": "AnimeContentBot/1.0"
                },
                json={
                    "model": "GigaChat-3-Ultra",
                    "messages": [
                        {"role": "system", "content": system_msg},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.6,
                    "max_tokens": 1200
                },
                timeout=30,
                verify=False
            )
            response.raise_for_status()
            data = response.json()
            generated_text = data["choices"][0]["message"]["content"].strip()

            print("=== GigaChat Response ===")
            print(generated_text)
            print("=========================")

            # Строим карточки на основе chosen
            cards = []
            for idx, name in enumerate(chosen):
                next_name = chosen[idx+1] if idx+1 < len(chosen) else None
                desc = extract_section(generated_text, name, next_name)
                if not desc:
                    print(f"Не найдено описание для '{name}', пробуем ещё раз")
                    break
                card = f"<b>{name}</b>\n{desc}"
                if idx < len(chosen) - 1:
                    card += "\n────────────────"
                cards.append(card)
            else:
                # Все 5 описаний найдены
                used_anime.update(chosen)
                save_used_anime(used_anime)
                return '\n'.join(cards)

        except Exception as e:
            print(f"Ошибка генерации: {e}")
            return None

    print("Не удалось получить все описания")
    return None

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
