import os
import re
import random
import time
import io
import urllib3
import telebot
import requests
import google.generativeai as genai

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Токены и ID
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Настройка Gemini
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# === ЖЕСТКАЯ ПРИВЯЗКА ПУТЕЙ К ПАПКЕ СКРИПТА ===
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
POPULAR_ANIME_FILE = os.path.join(BASE_DIR, "popular_anime.txt")
LAST_QUIZ_TYPE_FILE = os.path.join(BASE_DIR, "last_quiz_type.txt")
LAST_MEDIA_TYPE_FILE = os.path.join(BASE_DIR, "last_media_type.txt")
# ==============================================

bot = telebot.TeleBot(TELEGRAM_TOKEN)

# ==========================================
# 1. РАБОТА С GEMINI (ТЕКСТОВЫЕ ВОПРОСЫ)
# ==========================================

def gemini_request(prompt):
    try:
        model = genai.GenerativeModel(
            model_name='gemini-1.5-flash',
            system_instruction=(
                "Ты — харизматичный ведущий викторины по аниме. "
                "Генерируй ровно один короткий креативный вопрос без вводных слов (таких как 'Конечно, вот вопрос:' и т.д.). "
                "Ответом на вопрос всегда является НАЗВАНИЕ АНИМЕ. "
                "КРАЙНЕ ВАЖНО: Никогда не используй слова из названия аниме или имена главных героев в тексте своего вопроса! "
                "Пиши так, чтобы было интересно угадывать."
            )
        )
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print(f"[ERROR] Ошибка генерации Gemini: {e}")
        return ""

def clean_question(text):
    if not text:
        return ""
    # Очистка от возможных Markdown-выделений, если нейросеть их добавит
    text = text.replace('**', '').replace('*', '')
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    if lines:
        return " ".join(lines)
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
    if not anime_id: return None
        
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
        
        if not res.get('anime'): return None
            
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
# 3. ФАЙЛОВЫЕ ПОМОЩНИКИ (С ЛОГИРОВАНИЕМ)
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

# ==========================================
# 4. ГЕНЕРАЦИЯ ВОПРОСОВ (ЖЕСТКОЕ ЧЕРЕДОВАНИЕ)
# ==========================================

def generate_strict_quiz(anime_name, target_media):
    question_templates = [
        {
            "type": "история браузера",
            "media_type": "text",
            "prompt": f"Придумай 3 смешных поисковых запроса в браузере, которые мог бы вбивать герой аниме «{anime_name}». Категорически без имен. В конце предложи угадать, чей это браузер."
        },
        {
            "type": "заметки психотерапевта",
            "media_type": "text",
            "prompt": f"Напиши короткую заметку от лица психотерапевта, к которому пришел герой аниме «{anime_name}». Врач в шоке от проблем пациента (без имен). В конце попроси угадать тайтл."
        },
        {
            "type": "полицейская сводка",
            "media_type": "text",
            "prompt": f"Составь смешную полицейскую сводку о разрушениях после типичной драки в аниме «{anime_name}». Опиши способности языка бюрократа (без имен). Закончи вопросом о том, где это произошло."
        },
        {
            "type": "отзыв хейтера",
            "media_type": "text",
            "prompt": f"Напиши утрированно 'гневный' и смешной отзыв зрителя на логику мира аниме «{anime_name}» (без имен). Закончи текстом вопросом к читателям, чтобы они угадали тайтл."
        },
        {
            "type": "глазами прохожего (POV)",
            "media_type": "text",
            "prompt": f"Опиши безумную сцену из аниме «{anime_name}» от лица случайного прохожего, который ничего не понимает. Имена не называй. В конце спроси, из какого это аниме."
        },
        {
            "type": "ребус из эмодзи",
            "media_type": "text",
            "prompt": f"Подбери 4-5 эмодзи, которые идеально описывают сюжет аниме «{anime_name}». Выведи эмодзи и задай вопрос 'Какое аниме здесь скрыто?'."
        },
        {
            "type": "три ассоциации",
            "media_type": "text",
            "prompt": f"Выбери 3 уникальных предмета, термина или особенности лора (НЕ имена) из аниме «{anime_name}». Перечисли их и спроси 'Для какого мира характерны эти вещи?'"
        },
        {
            "type": "анкета знакомств",
            "media_type": "text",
            "prompt": f"Напиши абсурдную анкету для сайта знакомств от лица персонажа из аниме «{anime_name}». Перечисли его пугающие 'плюсы' и 'минусы' (без имен). Закончи вопросом, откуда этот герой."
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
        
    else: # Текст (Gemini)
        if not GEMINI_API_KEY:
            print("[ERROR] Ключ Gemini API не найден!")
            return None, None
            
        last_type = load_last_value(LAST_QUIZ_TYPE_FILE)
        available = [t for t in question_templates if t["type"] != last_type]
        if not available:
            available = question_templates
            
        template = random.choice(available)
        
        for attempt in range(3):
            raw_question = gemini_request(template["prompt"])
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

    # Читаем прошлый формат и определяем следующий
    last_media = load_last_value(LAST_MEDIA_TYPE_FILE)
    print(f"[DEBUG] Прошлый формат из файла: '{last_media}'")
    
    sequence = {"text": "image", "image": "audio", "audio": "text"}
    target_media = sequence.get(last_media, "text")
    print(f"[DEBUG] Целевой формат на сейчас: '{target_media}'")

    quiz_data = None
    for attempt in range(10):
        correct_anime = random.choice(all_anime)
        wrong_pool = [a for a in all_anime if a.lower() != correct_anime.lower()]
        if len(wrong_pool) < 3: continue
        wrong_answers = random.sample(wrong_pool, 3)

        question, media_url = generate_strict_quiz(correct_anime, target_media)
        
        if question:
            quiz_data = (correct_anime, wrong_answers, question, media_url)
            break
        else:
            print(f"[DEBUG] Аниме '{correct_anime}' не подошло для формата '{target_media}'. Ищу другое...")

    if not quiz_data:
        print(f"[ERROR] Критическая ошибка: Не удалось создать викторину формата '{target_media}' за 10 попыток.")
        return

    correct_anime, wrong_answers, question, media_url = quiz_data
    options = [correct_anime] + wrong_answers
    random.shuffle(options)
    correct_index = options.index(correct_anime)

    send_quiz_poll(question, options, correct_index, media_url, target_media)
    
    # Сохраняем формат ТОЛЬКО после успешной отправки
    save_last_value(LAST_MEDIA_TYPE_FILE, target_media)

if __name__ == "__main__":
    main()
