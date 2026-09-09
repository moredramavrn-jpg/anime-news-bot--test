import os
import re
import random
import time
import uuid
import urllib3
import telebot
import requests

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Токены и ID
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
GIGACHAT_AUTHORIZATION_KEY = os.getenv("GIGACHAT_AUTHORIZATION_KEY")

# Файлы данных
POPULAR_ANIME_FILE = "popular_anime.txt"
LAST_QUIZ_TYPE_FILE = "last_quiz_type.txt"
LAST_MEDIA_TYPE_FILE = "last_media_type.txt" # Новый файл для чередования визуала

bot = telebot.TeleBot(TELEGRAM_TOKEN)

gigachat_access_token = None
gigachat_token_expires_at = 0

# ==========================================
# 1. РАБОТА С GIGACHAT (ТЕКСТОВЫЕ ВОПРОСЫ)
# ==========================================

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

def giga_request(prompt, token, max_tokens=300):
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-Request-ID": str(uuid.uuid4()),
        "X-Session-ID": str(uuid.uuid4()),
        "User-Agent": "AnimeQuizBot/3.0"
    }
    payload = {
        "model": "GigaChat-3-Ultra",
        "messages": [
            {
                "role": "system", 
                "content": (
                    "Ты — харизматичный ведущий викторины по аниме. "
                    "Генерируй ровно один короткий вопрос без вводных слов. "
                    "Ответом на вопрос всегда является НАЗВАНИЕ АНИМЕ. "
                    "КРАЙНЕ ВАЖНО: Никогда не используй слова из названия аниме в тексте своего вопроса!"
                )
            },
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
        return response.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"Ошибка GigaChat: {e}")
        return ""

def clean_question(text):
    if not text:
        return ""
    text = re.sub(r'Как и любая языковая модель.*?информация\.', '', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'Ответ сгенерирован нейросетевой моделью.*?информация\.', '', text, flags=re.IGNORECASE | re.DOTALL)
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    if lines:
        question = lines[0]
        question = re.sub(r'\.{3,}$', '', question).strip()
        return question
    return ""

def is_answer_in_question(question, anime_name):
    """Проверяет, нет ли слов из названия аниме в самом вопросе (защита от спойлеров)"""
    q_words = set(re.findall(r'[а-яёa-z0-9]+', question.lower()))
    a_words = set(re.findall(r'[а-яёa-z0-9]+', anime_name.lower()))
    
    # Исключаем короткие предлоги и союзы из названия
    a_words = {w for w in a_words if len(w) > 2}
    
    # Если есть пересечение слов, значит нейросеть проболталась
    if q_words.intersection(a_words):
        return True
    return False

# ==========================================
# 2. ПОЛУЧЕНИЕ МЕДИАФАЙЛОВ (КАРТИНКИ И ОПЕНИНГИ)
# ==========================================

def fetch_anime_image(anime_name):
    try:
        search_url = f"https://api.jikan.moe/v4/anime?q={anime_name}&limit=1"
        search_res = requests.get(search_url, timeout=10).json()
        
        if not search_res.get('data'):
            return None
            
        anime_id = search_res['data'][0]['mal_id']
        
        pics_url = f"https://api.jikan.moe/v4/anime/{anime_id}/pictures"
        pics_res = requests.get(pics_url, timeout=10).json()
        
        if pics_res.get('data'):
            pic = random.choice(pics_res['data'])
            return pic['jpg']['large_image_url']
    except Exception as e:
        print(f"Ошибка поиска картинки: {e}")
    return None

def fetch_anime_opening(anime_name):
    try:
        url = f"https://api.animethemes.moe/anime?q={anime_name}&include=animethemes.animethemeentries.videos"
        res = requests.get(url, timeout=15).json()
        
        if not res.get('anime'):
            return None
            
        themes = res['anime'][0]['animethemes']
        ops = [t for t in themes if t['type'] == 'OP']
        
        if ops:
            video_url = ops[0]['animethemeentries'][0]['videos'][0]['link']
            return video_url
    except Exception as e:
        print(f"Ошибка поиска опенинга: {e}")
    return None

# ==========================================
# 3. ФАЙЛОВЫЕ ПОМОЩНИКИ
# ==========================================

def load_last_value(filename):
    if os.path.exists(filename):
        with open(filename, 'r', encoding='utf-8') as f:
            return f.read().strip()
    return None

def save_last_value(filename, value):
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(value)

def load_popular_anime():
    if not os.path.exists(POPULAR_ANIME_FILE):
        return []
    with open(POPULAR_ANIME_FILE, 'r', encoding='utf-8') as f:
        return [line.strip() for line in f if line.strip()]

# ==========================================
# 4. ГЕНЕРАЦИЯ ВОПРОСОВ (ШАБЛОНЫ)
# ==========================================

def generate_quiz_content(anime_name, token):
    question_templates = [
        {
            "type": "плохое описание сюжета",
            "media_type": "text",
            "prompt": f"Опиши сюжет аниме «{anime_name}» смешно и абсурдно. НЕ используй имена героев. Начни с 'В каком аниме...?'"
        },
        {
            "type": "ребус из эмодзи",
            "media_type": "text",
            "prompt": f"Подбери 4-5 эмодзи, которые идеально описывают сюжет аниме «{anime_name}». Формат вывода: '[Эмодзи] Какое аниме зашифровано в этом послании?'"
        },
        {
            "type": "три ассоциации",
            "media_type": "text",
            "prompt": f"Выбери 3 уникальных слова-ассоциации (предметы, термины — НЕ имена), которые указывают на аниме «{anime_name}». Формат: 'Три слова: [Слово 1], [Слово 2], [Слово 3]. О каком аниме речь?'"
        },
        {
            "type": "угадай по кадру",
            "media_type": "image",
            "prompt": (
                "Сформулируй короткий, интригующий вопрос к прикрепленному кадру из аниме. "
                "Суть вопроса: нужно угадать тайтл по картинке. "
                "Выведи только текст вопроса без ответов, спойлеров и имен."
            )
        },
        {
            "type": "угадай опенинг",
            "media_type": "video",
            "prompt": (
                "Сформулируй короткий, зажигательный вопрос к видео с опенингом аниме. "
                "Суть вопроса: нужно угадать тайтл по музыке. "
                "Выведи только текст вопроса без ответов, спойлеров и названия трека."
            )
        }
    ]

    last_media = load_last_value(LAST_MEDIA_TYPE_FILE)
    
    # Оставляем только те шаблоны, чей media_type отличается от прошлого
    available = [t for t in question_templates if t["media_type"] != last_media]
    if not available:
        available = question_templates

    random.shuffle(available)
    
    for template in available:
        media_url = None
        
        # Поиск медиа
        if template["media_type"] == "image":
            media_url = fetch_anime_image(anime_name)
            if not media_url: continue 
            
        elif template["media_type"] == "video":
            media_url = fetch_anime_opening(anime_name)
            if not media_url: continue 
            
        # Генерация с проверкой (до 3 попыток на перегенерацию, если ИИ проболтался)
        for attempt in range(3):
            raw_question = giga_request(template["prompt"], token, max_tokens=250)
            question = clean_question(raw_question)
            
            # Проверяем, есть ли ответ в самом вопросе
            if question and not is_answer_in_question(question, anime_name):
                save_last_value(LAST_QUIZ_TYPE_FILE, template["type"])
                save_last_value(LAST_MEDIA_TYPE_FILE, template["media_type"])
                return question, media_url, template["media_type"]
            else:
                print(f"Попытка {attempt + 1}: Нейросеть проболталась или выдала пустой ответ. Пробуем снова...")

    return None, None, None

# ==========================================
# 5. ОТПРАВКА
# ==========================================

def send_quiz_poll(question_text, options, correct_index, media_url=None, media_type="text"):
    header = "🎌 Аниме-викторина\n\n"
    full_question = f"{header}{question_text}"

    if len(full_question) > 300:
        full_question = full_question[:297] + "..."

    try:
        if media_type == "image" and media_url:
            bot.send_photo(chat_id=CHANNEL_ID, photo=media_url)
            time.sleep(1) 
        
        elif media_type == "video" and media_url:
            bot.send_video(chat_id=CHANNEL_ID, video=media_url, supports_streaming=True)
            time.sleep(1)

        bot.send_poll(
            chat_id=CHANNEL_ID,
            question=full_question,
            options=options,
            type="quiz",
            correct_option_id=correct_index,
            open_period=86400,
            is_anonymous=True
        )
        print(f"Викторина опубликована. Тип: {media_type}")
    except Exception as e:
        print(f"Ошибка отправки опроса: {e}")

def main():
    all_anime = load_popular_anime()
    if len(all_anime) < 4:
        print("Недостаточно названий для создания вариантов (нужно минимум 4)")
        return

    token = get_gigachat_token()
    if not token:
        print("Не удалось получить токен GigaChat")
        return

    correct_anime = random.choice(all_anime)
    wrong_pool = [a for a in all_anime if a.lower() != correct_anime.lower()]
    
    if len(wrong_pool) < 3:
        print("Недостаточно названий для вариантов ответов.")
        return
        
    wrong_answers = random.sample(wrong_pool, 3)

    question, media_url, media_type = generate_quiz_content(correct_anime, token)
    
    if not question:
        print("Не удалось сгенерировать корректный вопрос (возможно ИИ все время сливал ответ)")
        return

    options = [correct_anime] + wrong_answers
    random.shuffle(options)
    correct_index = options.index(correct_anime)

    send_quiz_poll(question, options, correct_index, media_url, media_type)

if __name__ == "__main__":
    main()
