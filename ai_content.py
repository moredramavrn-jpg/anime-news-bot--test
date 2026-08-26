import os
import re
import html
import uuid
import time
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

def load_used_anime():
    if not os.path.exists(USED_ANIME_FILE):
        return set()
    with open(USED_ANIME_FILE, 'r', encoding='utf-8') as f:
        return {line.strip().lower() for line in f if line.strip()}

def save_used_anime(anime_set):
    anime_list = list(anime_set)[-100:]
    with open(USED_ANIME_FILE, 'w', encoding='utf-8') as f:
        for name in anime_list:
            f.write(name + '\n')

def extract_anime_names(text):
    names = re.findall(r'«([^»]+)»|"([^"]+)"', text)
    result = set()
    for groups in names:
        for g in groups:
            if g:
                result.add(g.strip().lower())
    return result

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

def replace_rating_numbers(text):
    text = re.sub(r'^4\.\s*', '💥 ', text, flags=re.MULTILINE)
    text = re.sub(r'^5\.\s*', '🌟 ', text, flags=re.MULTILINE)
    return text

def remove_excess_emoji(text):
    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        m = re.match(r'^((?:🥇|🥈|🥉|💥|🌟)\s*)', line)
        if m:
            prefix = m.group(1)
            rest = line[len(prefix):]
            rest_no_emoji = re.sub(r'[\U0001F300-\U0001FAFF]', '', rest)
            cleaned_lines.append(prefix + rest_no_emoji)
        else:
            cleaned_lines.append(line)
    return '\n'.join(cleaned_lines)

def fix_rating_format(text):
    text = replace_rating_numbers(text)
    text = re.sub(r'\s*\n\s*', ' ', text).strip()
    pattern = r'(?=(?:🥇|🥈|🥉|💥|🌟)\s)'
    parts = re.split(pattern, text)
    parts = [p.strip() for p in parts if p.strip()]
    return '\n\n'.join(parts)

def wrap_titles_in_quotes(text):
    lines = text.split('\n')
    wrapped = []
    for line in lines:
        m = re.match(r'^((?:🥇|🥈|🥉|💥|🌟)\s*)([^—]+)(—.*)?$', line)
        if m:
            prefix = m.group(1)
            title_part = m.group(2).strip()
            rest = m.group(3) or ""
            if not (title_part.startswith('«') and title_part.endswith('»')):
                title_part = f"«{title_part}»"
            wrapped.append(f"{prefix}{title_part} {rest}".strip())
        else:
            wrapped.append(line)
    return '\n'.join(wrapped)

def has_anime_titles(text):
    if re.search(r'«[^»]+»|"[^"]+"', text):
        return True
    if re.search(r'(?:🥇|🥈|🥉|💥|🌟)\s*.+?—', text):
        return True
    return False

def generate_content():
    token = get_gigachat_token()
    if not token:
        print("Не удалось получить токен GigaChat")
        return None

    used_anime = load_used_anime()
    last_good = None

    for attempt in range(5):
        system_msg = "Ты — редактор аниме-канала. Ты составляешь топ-5 аниме, используя ТОЛЬКО официальные русские названия."
        prompt = f"""Составь топ-5 аниме, которые стоит посмотреть.
Формат строго:
🥇 «Название аниме» — описание из 2-3 предложений.
🥈 «Название аниме» — описание из 2-3 предложений.
🥉 «Название аниме» — описание из 2-3 предложений.
4. «Название аниме» — описание из 2-3 предложений.
5. «Название аниме» — описание из 2-3 предложений.

Каждый пункт — это ОДИН абзац. Не переноси описание на следующую строку.
Не добавляй дополнительных абзацев после описания.
Используй только один эмодзи перед названием (медаль или цифру). Больше никаких эмодзи в тексте.
Названия обязательно в кавычках «».
Используй ТОЛЬКО официальные русские названия аниме, которые точно существуют. Например: «Твоя апрельская ложь», «Город, в котором меня нет», «Наруто», «Форма голоса», «В лес, где мерцают светлячки».
Если не уверен в правильном русском названии — НЕ используй это аниме. Лучше выбрать другое, которое знаешь точно.
Никакой латиницы. Не выдумывай названия.
Не задавай вопросы, не пиши вводные слова.
{f'НЕ ИСПОЛЬЗУЙ ЭТИ АНИМЕ: {", ".join(sorted(used_anime))}.' if used_anime else ''}

Выведи результат строго в формате:
Заголовок: 5 популярных аниме, которые стоит посмотреть
Текст: <текст топа>
"""
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
                    "temperature": 0.6,   # снизили, чтобы меньше фантазировал
                    "max_tokens": 1200
                },
                timeout=30,
                verify=False
            )
            response.raise_for_status()
            data = response.json()
            generated_text = data["choices"][0]["message"]["content"].strip()

            print(f"=== Attempt {attempt+1} ===")
            print(generated_text)
            print("=====================")

            title, body = parse_generated_text(generated_text)

            if not title or not body:
                continue

            title = "5 популярных аниме, которые стоит посмотреть"

            rating_markers = re.search(r'(?:🥇|🥈|🥉|\d+\.)\s', body)
            if rating_markers:
                body = fix_rating_format(body)
                body = wrap_titles_in_quotes(body)
                body = remove_excess_emoji(body)

            if not has_anime_titles(body):
                print("В тексте нет названий аниме")
                continue

            last_good = (title, body)

            new_anime = extract_anime_names(body)
            if new_anime & used_anime:
                print("Найдены повторяющиеся аниме, пробуем ещё раз")
                used_anime.update(new_anime)
                continue

            save_used_anime(used_anime | new_anime)
            return title, body

        except Exception as e:
            print(f"Ошибка генерации: {e}")
            return None

    if last_good:
        print("Не удалось избежать повторов, публикуем последний вариант")
        save_used_anime(used_anime | extract_anime_names(last_good[1]))
        return last_good

    print("Не удалось сгенерировать контент")
    return None

def send_content_post(title, body):
    message = f"✨ <b>{html.escape(title)}</b>\n\n{body}\n\n#аниме #новости"
    try:
        bot.send_message(CHANNEL_ID, message, parse_mode='HTML', disable_web_page_preview=True)
        print("Контент-пост опубликован.")
    except Exception as e:
        print(f"Ошибка отправки: {e}")

def main():
    result = generate_content()
    if result:
        send_content_post(*result)
    else:
        print("Не удалось сгенерировать контент.")

if __name__ == "__main__":
    main()
