import os
import re
import random
import time
import uuid
import io
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
LAST_MEDIA_TYPE_FILE = "last_media_type.txt"

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
    
    for attempt in range(3):
        try:
            r = requests.post(url, headers=headers, data=data, timeout=30, verify=False)
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
            print(f"Попытка {attempt + 1}: Ошибка получения токена GigaChat: {e}")
            time.sleep(3)
            
    return None

def giga_request(prompt, token, max_tokens=300):
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-Request-ID": str(uuid.uuid4()),
        "X-Session-ID": str(uuid.uuid4()),
        "User-Agent": "AnimeQuizBot/9.0"
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
    
    for attempt in range(3):
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
            print(f"Попытка {attempt + 1}: Ошибка GigaChat (генерация): {e}")
            time.sleep(3)
            
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
    q_words = set(re.findall(r'[а-яёa-z0-9]+', question.lower()))
    a_words = set(re.findall(r'[а-яёa-z0-9]+', anime_name.lower()))
    a_words = {w for w in a_words if len(w) > 2}
    
    if q_words.intersection(a_words):
        return True
    return False

# ==========================================
# 2. ПОЛУЧЕНИЕ МЕДИАФАЙЛОВ
# ==========================================

def get_shikimori_info(anime_name):
    try:
        headers = {"User-Agent": "AnimeQuizBot"}
        search_url = f"https://shikimori.one/api/animes?search={anime_name}&limit=1"
        res = requests.get(search_url, headers=headers, timeout=15).json()
        
        if res and isinstance(res, list) and len(res) > 0:
            return res[0]['id'], res[0]['name']
    except Exception as e:
        print(f"Ошибка поиска на Shikimori для '{anime_name}': {e}")
    return None, None

def fetch_anime_image(anime_name):
    anime_id, _ = get_shikimori_info(anime_name)
    if not anime_id:
        return None
        
    try:
        headers = {"User-Agent": "AnimeQuizBot"}
        url = f"https://shikimori.one/api/animes/{anime_id}/screenshots"
        res = requests.get(url, headers=headers, timeout=15).json()
        
        if res and isinstance(res, list) and len(res) > 0:
            pic = random.choice(res)
            return "https://shikimori.one" + pic['original']
    except Exception:
        pass
    return None

def fetch_anime_audio(anime_name):
    _, romaji_name = get_shikimori_info(anime_name)
    search_query = romaji_name if romaji_name else anime_name
    
    try:
        url = f"https://api.animethemes.moe/anime?q={search_query}&include=animethemes.animethemeentries.audios"
        res = requests.get(url, timeout=20).json()
        
        if not res.get('anime'):
            return None
            
        themes = res['anime'][0]['animethemes']
        ops = [t for t in themes if t['type'] == 'OP']
        
        for op in ops:
            for entry in op.get('animethemeentries', []):
                audios = entry.get('audios', [])
                if audios:
                    return audios[0]['link']
    except Exception:
        pass
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
# 4. ГЕНЕРАЦИЯ ВОПРОСОВ (ЖЕСТКОЕ ЧЕРЕДОВАНИЕ)
# ==========================================

def generate_strict_quiz(anime_name, token, target_media):
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
        }
    ]

    if target_media == "image":
        media_url = fetch_anime_image(anime_name)
        if not media_url: return None, None 
        
        question = random.choice([
            "Один взгляд на эту рисовку, и всё ясно! Откуда этот кадр?",
            "Настоящий отаку узнает этот момент из тысячи. Что за аниме?",
            "Проверим зрительную память! Из какого тайтла этот скриншот?",
            "К какому аниме принадлежит этот кадр?"
        ])
        save_last_value(LAST_QUIZ_TYPE_FILE, "угадай по кадру")
        return question, media_url
        
    elif target_media == "audio":
        media_url = fetch_anime_audio(anime_name)
        if not media_url: return None, None 
        
        question = random.choice([
            "Узнаете эти ноты с первых секунд? Из какого аниме опенинг?",
            "Этот трек точно есть в вашем плейлисте! Откуда он?",
            "Слушаем и угадываем! В каком тайтле звучит эта песня?",
            "Легендарный опенинг! Сможете назвать аниме?"
        ])
        save_last_value(LAST_QUIZ_TYPE_FILE, "угадай опенинг")
        return question, media_url
        
    else: # Текст
        last_type = load_last_value(LAST_QUIZ_TYPE_FILE)
        available = [t for t in question_templates if t["type"] != last_type]
        if not available:
            available = question_templates
            
        template = random.choice(available)
        
        for attempt in range(3):
            raw_question = giga_request(template["prompt"], token, max_tokens=250)
            question = clean_question(raw_question)
            
            if question and not is_answer_in_question(question, anime_name):
                save_last_value(LAST_QUIZ_TYPE_FILE, template["type"])
                return question, None
            else:
                print(f"Попытка {attempt + 1}: Пустой ответ или спойлер в тексте. Ждем 3 секунды...")
                time.sleep(3)

    return None, None

# ==========================================
# 5. ОТПРАВКА И ГЛАВНЫЙ ЦИКЛ
# ==========================================

def send_quiz_poll(question_text, options, correct_index, media_url=None, media_type="text"):
    header = "🎌 Аниме-викторина\n\n"
    full_question = f"{header}{question_text}"

    if len(full_question) > 300:
        full_question = full_question[:297] + "..."

    try:
        media_msg = None
        
        if media_type == "image" and media_url:
            print("Скачиваю картинку...")
            img_data = requests.get(media_url, headers={"User-Agent": "AnimeQuizBot"}, timeout=20).content
            media_msg = bot.send_photo(chat_id=CHANNEL_ID, photo=img_data)
        
        elif media_type == "audio" and media_url:
            print("Скачиваю аудио опенинга...")
            audio_data = requests.get(media_url, headers={"User-Agent": "AnimeQuizBot"}, timeout=30).content
            
            audio_file = io.BytesIO(audio_data)
            audio_file.name = "opening_track.ogg"
            media_msg = bot.send_audio(chat_id=CHANNEL_ID, audio=audio_file)

        reply_id = media_msg.message_id if media_msg else None

        bot.send_poll(
            chat_id=CHANNEL_ID,
            question=full_question,
            options=options,
            type="quiz",
            correct_option_id=correct_index,
            open_period=86400,
            is_anonymous=True,
            reply_to_message_id=reply_id 
        )
        print(f"Викторина опубликована. Тип: {media_type}")
    except Exception as e:
        print(f"Ошибка отправки опроса: {e}")

def main():
    all_anime = load_popular_anime()
    if len(all_anime) < 4:
        print("Недостаточно названий (нужно минимум 4)")
        return

    token = get_gigachat_token()
    if not token:
        print("Не удалось получить токен GigaChat")
        return

    # Определяем, какой формат нам нужен СЕЙЧАС (строгое чередование)
    last_media = load_last_value(LAST_MEDIA_TYPE_FILE)
    sequence = {"text": "image", "image": "audio", "audio": "text"}
    target_media = sequence.get(last_media, "text")
    print(f"Целевой формат викторины: {target_media}")

    # Бот делает до 10 попыток найти аниме, которое поддерживает нужный формат
    quiz_data = None
    for attempt in range(10):
        correct_anime = random.choice(all_anime)
        wrong_pool = [a for a in all_anime if a.lower() != correct_anime.lower()]
        if len(wrong_pool) < 3: continue
        wrong_answers = random.sample(wrong_pool, 3)

        question, media_url = generate_strict_quiz(correct_anime, token, target_media)
        
        if question:
            quiz_data = (correct_anime, wrong_answers, question, media_url)
            break
        else:
            print(f"Аниме '{correct_anime}' не подошло для формата {target_media}. Ищу другое...")

    if not quiz_data:
        print(f"Критическая ошибка: Не удалось создать викторину формата {target_media} за 10 попыток.")
        return

    correct_anime, wrong_answers, question, media_url = quiz_data

    options = [correct_anime] + wrong_answers
    random.shuffle(options)
    correct_index = options.index(correct_anime)

    send_quiz_poll(question, options, correct_index, media_url, target_media)
    
    # Сохраняем формат ТОЛЬКО после успешной отправки, чтобы цепочка не сбивалась
    save_last_value(LAST_MEDIA_TYPE_FILE, target_media)

if __name__ == "__main__":
    main()
