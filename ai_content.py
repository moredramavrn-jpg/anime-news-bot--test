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

def extract_anime_names(text):
    # Извлекаем названия без кавычек и номеров
    lines = text.split('\n')
    names = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith('─'):
            continue
        # Убираем начальный номер, если есть
        line = re.sub(r'^\d+\.\s*', '', line)
        # Если строка не пустая и не является описанием (длина > 3), считаем названием
        if len(line) > 2:
            names.append(line.lower())
    return set(names)

def parse_generated_text(raw_text):
    lines = raw_text.strip().split('\n')
    title = None
    body_lines = []

    for line in lines:
        if line.startswith('Заголовок:'):
            title = line.replace('Заголовок:', '').strip()
        elif line.startswith('Текст:'):
            body_lines.append(line.replace('Текст:', '').strip())
        elif not title and not body_lines and len(line.strip()) > 3:
            title = line.strip()
        else:
            body_lines.append(line.strip())

    body = '\n'.join([l for l in body_lines if l]).strip()
    if not title and body_lines:
        title = body_lines[0]
        body = '\n'.join(body_lines[1:]).strip()

    return title, body

def format_cards(text):
    # Ожидаем, что каждый пункт разделён пустой строкой
    items = [p.strip() for p in text.split('\n\n') if p.strip()]
    cards = []
    for idx, item in enumerate(items):
        lines = item.split('\n')
        if not lines:
            continue
        first_line = lines[0].strip()
        # Убираем номер и возможные эмодзи/кавычки
        name = re.sub(r'^(?:\d+\.\s*|🥇\s*|🥈\s*|🥉\s*|💥\s*|🌟\s*)', '', first_line)
        name = name.strip('«»"').strip()
        # Описание — остальные строки
        desc_lines = [l.strip() for l in lines[1:] if l.strip()]
        desc = ' '.join(desc_lines)
        if desc:
            desc = desc[0].upper() + desc[1:]
        card = f"<b>{name}</b>\n{desc}"
        if idx < len(items) - 1:
            card += "\n────────────────"
        cards.append(card)
    return '\n'.join(cards)

def generate_top_5():
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

    prompt = f"""Составь подборку из 5 аниме, которые стоит посмотреть, используя только эти названия: {anime_list}.

Формат строго:
1. Название аниме
Описание из 2-3 предложений.

2. Название аниме
Описание из 2-3 предложений.

3. Название аниме
Описание из 2-3 предложений.

4. Название аниме
Описание из 2-3 предложений.

5. Название аниме
Описание из 2-3 предложений.

Каждый пункт — это номер, затем название (без кавычек), затем с новой строки описание.
Не добавляй пустых строк между номером и названием, и между названием и описанием.
Разделяй пункты пустой строкой.
Не используй эмодзи.
Не задавай вопросы, не пиши вводные слова.

Выведи результат строго в формате:
Заголовок: аниме, которые стоит посмотреть
Текст: <текст подборки>
"""
    system_msg = "Ты — редактор аниме-канала. Ты составляешь подборки только из предоставленного списка названий."

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

            title, body = parse_generated_text(generated_text)
            if not title or not body:
                continue

            # Проверяем, что есть хотя бы 3 названия
            extracted = extract_anime_names(body)
            if len(extracted) < 3:
                continue

            used_anime.update(chosen)
            save_used_anime(used_anime)

            return title, body

        except Exception as e:
            print(f"Ошибка генерации: {e}")
            return None

    print("Не удалось получить корректный ответ")
    return None

def send_content_post(title, body):
    header = "✨ <b>Рубрика: аниме, которые стоит посмотреть</b>"
    cards = format_cards(body)
    message = f"{header}\n\n{cards}\n\n#аниме #рекомендации #чтопосмотреть"
    try:
        bot.send_message(CHANNEL_ID, message, parse_mode='HTML', disable_web_page_preview=True)
        print("Контент-пост опубликован.")
    except Exception as e:
        print(f"Ошибка отправки: {e}")

def main():
    result = generate_top_5()
    if result:
        send_content_post(*result)
    else:
        print("Не удалось сгенерировать контент.")

if __name__ == "__main__":
    main()
