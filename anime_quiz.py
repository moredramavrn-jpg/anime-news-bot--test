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

# === ЖЕСТКАЯ ПРИВЯЗКА ПУТЕЙ К ПАПКЕ СКРИПТА ===
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
POPULAR_ANIME_FILE = os.path.join(BASE_DIR, "popular_anime.txt")
LAST_QUIZ_TYPE_FILE = os.path.join(BASE_DIR, "last_quiz_type.txt")
LAST_MEDIA_TYPE_FILE = os.path.join(BASE_DIR, "last_media_type.txt")
# ==============================================

bot = telebot.TeleBot(TELEGRAM_TOKEN)

gigachat_access_token = None
gigachat_token_expires_at = 0

# ==========================================
# 1. РАБОТА С GIGACHAT
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
        "User-Agent": "AnimeQuizBot/9.7"
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
        # ИСПРАВЛЕНИЕ ТУТ: склеиваем все строчки через пробел, чтобы не терять вопрос!
        question = " ".join(lines)
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
    except Exception:
        pass
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
        url = f"https://api.animethemes.moe/anime?q={search_query}&include=animethemes.animethemeentries.videos.audio"
        res = requests.get(url, timeout=20).json()
        
        if not res.get('anime'):
            return None
            
        themes = res['anime'][0]['animethemes']
        ops = [t for t in themes if t['type'] == 'OP']
        
        for op in ops:
            for entry in op.get('animethemeentries', []):
                videos = entry.get('videos', [])
                for video in videos:
                    audio = video.get('audio')
                    if audio and audio.get('link'):
                        return audio['link']
    except Exception:
        pass
    return None

# ==========================================
# 3. ФАЙЛОВЫЕ ПОМОЩНИКИ И УМНЫЕ ФИЛЬТРЫ
# ==========================================

def load_last_value(filename):
    if os.path.exists(filename):
        with open(filename, 'r', encoding='utf-8') as f:
            return f.read().strip()
    return None

def save_last_value(filename, value):
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(value)
        print(f"[DEBUG] Состояние успешно сохранено: '{value}' в файл {os.path.basename(filename)}")
    except Exception as e:
        print(f"[ERROR] Не удалось сохранить файл {filename}: {e}")

def load_popular_anime():
    if not os.path.exists(POPULAR_ANIME_FILE):
        return []
    with open(POPULAR_ANIME_FILE, 'r', encoding='utf-8') as f:
        return [line.strip() for line in f if line.strip()]

def get_base_name(name):
    """Вычленяет чистое корневое название франшизы для фильтрации дублей."""
    base = name.lower()
    base = base.replace('re:zero', 'rezero')
    base = re.split(r':\s+| - | — |\.\s+', base)[0]
    base = re.sub(r'\s*\(\d{4}\)', '', base)
    base = re.sub(r'\s+(фильм|сезон|часть|ova|ona|movie|tv).*', '', base)
    base = re.sub(r'\s+\d+$', '', base)
    return base.strip()

def are_same_franchise(name1, name2):
    """Проверяет, относятся ли два тайтла к одной франшизе."""
    b1 = get_base_name(name1)
    b2 = get_base_name(name2)
    if b1 == b2: return True
    if len(b1) > 4 and len(b2) > 4:
        if b1.startswith(b2 + " ") or b2.startswith(b1 + " "): return True
    if "джоджо" in b1 and "джоджо" in b2: return True
    return False

def format_display_name(name):
    """Очищает название для красивого показа в опросе (оставляет Re:Zero целым)."""
    base = name
    base = re.split(r':\s+| - | — |\.\s+', base)[0]
    base = re.sub(r'\s*\(\d{4}\)', '', base)
    base = re.sub(r'\s+(Фильм|Сезон|Часть|OVA|ONA|Movie|TV|фильм|сезон|часть).*', '', base)
    return base.strip()

# ==========================================
# 4. ГЕНЕРАЦИЯ ВОПРОСОВ (ЖЕСТКОЕ ЧЕРЕДОВАНИЕ)
# ==========================================

def generate_strict_quiz(search_name, display_name, token, target_media):
    question_templates = [
        {
            "type": "история браузера",
            "media_type": "text",
            "prompt": f"Придумай 3 ОЧЕНЬ КОРОТКИХ смешных поисковых запроса в браузере, которые мог бы вбивать герой аниме «{display_name}». Без имен. Предложи угадать тайтл. СТРОГО до 200 символов суммарно."
        },
        {
            "type": "заметки психотерапевта",
            "media_type": "text",
            "prompt": f"Напиши ОЧЕНЬ КОРОТКУЮ заметку от лица психотерапевта, к которому пришел герой аниме «{display_name}». Врач в шоке (без имен). В конце попроси угадать тайтл. МАКСИМУМ 2-3 предложения, до 200 символов."
        },
        {
            "type": "полицейская сводка",
            "media_type": "text",
            "prompt": f"Составь КРАТКУЮ смешную полицейскую сводку о разрушениях после драки в аниме «{display_name}». Опиши способности (без имен). Спроси, где это произошло. СТРОГО до 200 символов."
        },
        {
            "type": "отзыв хейтера",
            "media_type": "text",
            "prompt": f"Напиши ОЧЕНЬ КОРОТКИЙ 'гневный' и смешной отзыв зрителя на логику мира аниме «{display_name}» (без имен). Закончи вопросом к читателям. Максимум 2 предложения, до 200 символов."
        },
        {
            "type": "глазами прохожего (POV)",
            "media_type": "text",
            "prompt": f"Опиши ОЧЕНЬ КРАТКО безумную сцену из аниме «{display_name}» от лица прохожего. Имена не называй. В конце спроси, из какого это аниме. Уложись в 2 предложения, до 200 символов."
        },
        {
            "type": "ребус из эмодзи",
            "media_type": "text",
            "prompt": f"Подбери 4-5 эмодзи, которые идеально описывают сюжет аниме «{display_name}». Выведи эмодзи и задай вопрос 'Какое аниме здесь скрыто?'."
        },
        {
            "type": "три ассоциации",
            "media_type": "text",
            "prompt": f"Выбери 3 уникальных предмета или термина (НЕ имена) из аниме «{display_name}». Перечисли их и спроси 'Для какого мира характерны эти вещи?'"
        },
        {
            "type": "анкета знакомств",
            "media_type": "text",
            "prompt": f"Напиши ОЧЕНЬ КОРОТКУЮ абсурдную анкету для сайта знакомств от лица персонажа «{display_name}». Плюсы и минусы (без имен). Закончи вопросом, откуда герой. СТРОГО до 200 символов."
        }
    ]

    if target_media == "image":
        media_url = fetch_anime_image(search_name)
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
        media_url = fetch_anime_audio(search_name)
        if not media_url: return None, None 
        
        question = random.choice([
            "Узнаете эти ноты с первых секунд? Из какого аниме опенинг?",
            "Этот трек точно есть в вашем плейлисте! Откуда он?",
            "Слушаем и угадываем! В каком тайтле звучит эта песня?",
            "Легендарный опенинг! Сможете назвать аниме?"
        ])
        save_last_value(LAST_QUIZ_TYPE_FILE, "угадай опенинг")
        return question, media_url
        
    else: 
        last_type = load_last_value(LAST_QUIZ_TYPE_FILE)
        available = [t for t in question_templates if t["type"] != last_type]
        if not available:
            available = question_templates
            
        template = random.choice(available)
        
        for attempt in range(3):
            raw_question = giga_request(template["prompt"], token, max_tokens=250)
            question = clean_question(raw_question)
            
            if question and not (is_answer_in_question(question, display_name) or is_answer_in_question(question, search_name)):
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
            print("[DEBUG] Скачиваю картинку...")
            img_data = requests.get(media_url, headers={"User-Agent": "AnimeQuizBot"}, timeout=20).content
            media_msg = bot.send_photo(chat_id=CHANNEL_ID, photo=img_data)
        
        elif media_type == "audio" and media_url:
            print("[DEBUG] Скачиваю аудио опенинга...")
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
        print(f"[SUCCESS] Викторина опубликована. Тип: {media_type}")
    except Exception as e:
        print(f"[ERROR] Ошибка отправки опроса: {e}")

def main():
    all_anime = load_popular_anime()
    if len(all_anime) < 4:
        print("[ERROR] Недостаточно названий в файле popular_anime.txt (нужно минимум 4)")
        return

    token = get_gigachat_token()
    if not token:
        print("[ERROR] Не удалось получить токен GigaChat")
        return

    last_media = load_last_value(LAST_MEDIA_TYPE_FILE)
    print(f"[DEBUG] Прошлый формат из файла: '{last_media}'")
    
    sequence = {"text": "image", "image": "audio", "audio": "text"}
    target_media = sequence.get(last_media, "text")
    print(f"[DEBUG] Целевой формат на сейчас: '{target_media}'")

    quiz_data = None
    for attempt in range(10):
        correct_anime = random.choice(all_anime)
        display_correct = format_display_name(correct_anime)
        
        wrong_answers = []
        shuffled_pool = all_anime.copy()
        random.shuffle(shuffled_pool)
        
        for a in shuffled_pool:
            if are_same_franchise(a, correct_anime):
                continue
                
            is_duplicate = False
            for w in wrong_answers:
                if are_same_franchise(a, w):
                    is_duplicate = True
                    break
                    
            if not is_duplicate:
                wrong_answers.append(a)
                
            if len(wrong_answers) == 3:
                break
                
        if len(wrong_answers) < 3: 
            continue

        display_wrongs = [format_display_name(w) for w in wrong_answers]

        question, media_url = generate_strict_quiz(correct_anime, display_correct, token, target_media)
        
        if question:
            quiz_data = (display_correct, display_wrongs, question, media_url)
            break
        else:
            print(f"[DEBUG] Аниме '{correct_anime}' не подошло для формата '{target_media}'. Ищу другое...")

    if not quiz_data:
        print(f"[ERROR] Критическая ошибка: Не удалось создать викторину формата '{target_media}' за 10 попыток.")
        return

    final_correct, final_wrongs, question, media_url = quiz_data
    options = [final_correct] + final_wrongs
    random.shuffle(options)
    correct_index = options.index(final_correct)

    send_quiz_poll(question, options, correct_index, media_url, target_media)
    
    save_last_value(LAST_MEDIA_TYPE_FILE, target_media)

if __name__ == "__main__":
    main()
