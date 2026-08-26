import os
import random
import time
import uuid
import urllib3
import telebot
import requests

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
GIGACHAT_AUTHORIZATION_KEY = os.getenv("GIGACHAT_AUTHORIZATION_KEY")

TOP_ANIME_FILE = "top_anime.txt"

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

def load_top_anime():
    if not os.path.exists(TOP_ANIME_FILE):
        print(f"Файл {TOP_ANIME_FILE} не найден")
        return []
    with open(TOP_ANIME_FILE, 'r', encoding='utf-8') as f:
        return [line.strip() for line in f if line.strip()]

def giga_request(prompt, token, max_tokens=300):
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-Request-ID": str(uuid.uuid4()),
        "X-Session-ID": str(uuid.uuid4()),
        "User-Agent": "AnimeRiddlePollBot/1.0"
    }
    payload = {
        "model": "GigaChat-3-Ultra",
        "messages": [
            {"role": "system", "content": "Ты — автор загадок про аниме."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.8,
        "max_tokens": max_tokens
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
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"Ошибка GigaChat: {e}")
        return ""

def generate_riddle(anime_name, token):
    prompt = (
        f"Придумай загадку-описание аниме «{anime_name}». Опиши сюжет, персонажей или ключевые детали, "
        "но не называй само аниме. Загадка должна быть интересной и давать подсказки. "
        "Выведи только текст загадки (без вступления и ответа)."
    )
    return giga_request(prompt, token, max_tokens=250)

def send_riddle_poll(riddle_text, options, correct_index):
    """
    Отправляет опрос с загадкой и 4 вариантами ответа.
    correct_index — индекс правильного варианта (0-3).
    open_period — через сколько секунд показать ответ (3 часа = 10800).
    """
    header = "🧩 <b>Аниме-загадка</b>\n"
    question = f"{header}{riddle_text}"
    try:
        bot.send_poll(
            chat_id=CHANNEL_ID,
            question=question,
            options=options,
            type="quiz",
            correct_option_id=correct_index,
            open_period=10800,          # 3 часа
            is_anonymous=False
        )
        print("Загадка-опрос опубликована.")
    except Exception as e:
        print(f"Ошибка отправки опроса: {e}")

def main():
    all_anime = load_top_anime()
    if len(all_anime) < 4:
        print("Недостаточно названий для создания вариантов")
        return

    token = get_gigachat_token()
    if not token:
        print("Не удалось получить токен GigaChat")
        return

    # Выбираем правильное аниме и 3 случайных других
    correct_anime = random.choice(all_anime)
    wrong_pool = [a for a in all_anime if a.lower() != correct_anime.lower()]
    if len(wrong_pool) < 3:
        print("Недостаточно названий для создания вариантов")
        return
    wrong_answers = random.sample(wrong_pool, 3)

    # Генерируем загадку
    riddle_text = generate_riddle(correct_anime, token)
    if not riddle_text:
        print("Не удалось сгенерировать загадку")
        return

    # Формируем варианты и запоминаем правильный индекс
    options = [correct_anime] + wrong_answers
    random.shuffle(options)
    correct_index = options.index(correct_anime)

    # Отправляем опрос
    send_riddle_poll(riddle_text, options, correct_index)

if __name__ == "__main__":
    main()
