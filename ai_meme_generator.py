import os
import random
import requests
import urllib3
import telebot
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont

# Отключаем предупреждения о ненадежном SSL (нужно для GigaChat API)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Загружаем ключи из переменных окружения (GitHub Secrets)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
GIGACHAT_AUTH_KEY = os.getenv("GIGACHAT_AUTHORIZATION_KEY")

bot = telebot.TeleBot(TELEGRAM_TOKEN)

def get_gigachat_token():
    """Получаем токен доступа для GigaChat API"""
    url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': 'application/json',
        'RqUID': '6f0b4819-4536-498b-9f4f-9a3b2b4f91d8',
        'Authorization': f'Basic {GIGACHAT_AUTH_KEY}'
    }
    payload = {'scope': 'GIGACHAT_API_PERS'}
    
    try:
        response = requests.post(url, headers=headers, data=payload, verify=False, timeout=20)
        return response.json().get('access_token')
    except Exception as e:
        print(f"Ошибка получения токена GigaChat: {e}")
        return None

def generate_meme_text():
    """Генерируем жесткую двухуровневую фразу для мема через GigaChat"""
    token = get_gigachat_token()
    if not token:
        return "КОГДА ЗАПУСТИЛ БОТА НА СЕРВЕРЕ\nИ ОН СЪЕЛ ТВОЮ СОБАКУ"
        
    url = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Authorization': f'Bearer {token}'
    }
    
    prompt = (
        "Сгенерируй короткую и максимально абсурдную фразу для жесткого аниме-мема. "
        "Фраза должна состоять из двух частей: верхняя строка начинается со слова «КОГДА» (или «Я КОГДА»), "
        "а нижняя — неожиданное, шокирующее или нелепое действие. "
        "Верни строго две строки текста, разделенные переносом строки. Без кавычек, без лишних пояснений. "
        "Пример формата:\nКОГДА СПРОСИЛ У БАТИ\nПОЧЕМУ ОТ НЕГО ПАХХНЕТ ЕДЕРНЫМ ТОПЛИВОМ"
    )
    
    payload = {
        "model": "GigaChat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 1.0,
        "max_tokens": 80
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, verify=False, timeout=20)
        text = response.json()['choices'][0]['message']['content'].strip()
        return text
    except Exception as e:
        print(f"Ошибка генерации текста от GigaChat: {e}")
        return "КОГДА ПЕРЕСМОТРЕЛ ВСЕХ АНИМЕ\nИ НАЧАЛ ВИДЕТЬ ТЕНЕВИКОВ В ШКАФУ"

def create_meme_image(text_payload):
    """Накладываем текст на случайную картинку из папки assets с обводкой"""
    assets_dir = "assets"
    if not os.path.exists(assets_dir):
        os.makedirs(assets_dir)
        
    # Ищем картинки в папке assets
    bg_files = [f for f in os.listdir(assets_dir) if f.lower().endswith(('.jpg', '.png', '.jpeg'))]
    
    # Если папка пустая, ставим черный фон
    if not bg_files:
        img = Image.new('RGB', (800, 800), color=(15, 15, 15))
    else:
        chosen_bg = random.choice(bg_files)
        img = Image.open(os.path.join(assets_dir, chosen_bg)).convert("RGB")
        img = img.resize((800, 800)) # Приводим к квадрату
        
    draw = ImageDraw.Draw(img)
    
    # Пытаемся загрузить жирный шрифт (если в системе нет arial, подтянется дефолтный)
    try:
        font = ImageFont.truetype("arial.ttf", 42)
    except:
        font = ImageFont.load_default()
        
    # Разбиваем текст на части (верх / низ)
    lines = text_payload.split('\n')
    top_text = lines[0] if len(lines) > 0 else "КОГДА НАПИСАЛ КОД"
    bottom_text = lines[1] if len(lines) > 1 else "А ОН ЗАРАБОТАЛ"

    def draw_text_with_outline(text, y_position):
        """Вспомогательная функция для отрисовки текста с черной обводкой"""
        # Считаем примерную ширину текста по центру (800 - ширина картинки)
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        x_position = (800 - text_width) / 2
        
        # Толстая черная обводка вкруг текста
        for adj_x in range(-3, 4):
            for adj_y in range(-3, 4):
                draw.text((x_position + adj_x, y_position + adj_y), text, font=font, fill=(0, 0, 0))
                
        # Сам белый текст поверх обводки
        draw.text((x_position, y_position), text, font=font, fill=(255, 255, 255))

    # Рисуем верхний текст (ближе к верху)
    draw_text_with_outline(top_text, 40)
    
    # Рисуем нижний текст (ближе к низу)
    draw_text_with_outline(bottom_text, 700)
    
    # Сохраняем в байтовый поток для отправки в Telegram
    bio = BytesIO()
    img.save(bio, format="JPEG")
    bio.seek(0)
    return bio

def main():
    print("Генерируем текст мемчика...")
    meme_text = generate_meme_text()
    print(f"Сгенерированный текст:\n{meme_text}")
    
    print("Собираем картинку...")
    meme_image = create_meme_image(meme_text)
    
    caption = f"#нейромем #щитпост"
    
    try:
        bot.send_photo(CHANNEL_ID, meme_image, caption=caption)
        print("Мем успешно улетел в канал!")
    except Exception as e:
        print(f"Ошибка отправки в Telegram: {e}")

if __name__ == "__main__":
    main()
