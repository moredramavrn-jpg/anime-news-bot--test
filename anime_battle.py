import os
import random
import requests
import uuid
import time
import urllib3
import telebot
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")

CHARACTERS_FILE = "characters.txt"

bot = telebot.TeleBot(TELEGRAM_TOKEN)

def load_characters():
    """
    Загружает список персонажей из файла characters.txt.
    Формат строки: Имя|Аниме|URL_картинки
    Возвращает список словарей.
    """
    if not os.path.exists(CHARACTERS_FILE):
        print(f"Файл {CHARACTERS_FILE} не найден")
        return []

    characters = []
    with open(CHARACTERS_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split('|')
            if len(parts) < 3:
                continue
            characters.append({
                'name': parts[0].strip(),
                'anime': parts[1].strip(),
                'image_url': parts[2].strip()
            })
    return characters

def download_image(url):
    """Скачивает изображение по URL и возвращает BytesIO."""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        r = requests.get(url, headers=headers, timeout=20)
        r.raise_for_status()
        return BytesIO(r.content)
    except Exception as e:
        print(f"Ошибка скачивания изображения {url}: {e}")
        return None

def create_collage(img1_bytes, img2_bytes):
    """
    Создаёт коллаж из двух изображений с текстом "VS" между ними.
    Возвращает BytesIO с готовым JPEG.
    """
    try:
        img1 = Image.open(img1_bytes)
        img2 = Image.open(img2_bytes)

        # Приводим к одинаковой высоте (например, 600px)
        height = 600
        img1 = img1.resize((int(img1.width * height / img1.height), height))
        img2 = img2.resize((int(img2.width * height / img2.height), height))

        # Ширина коллажа = ширина 1 + ширина 2 + пространство под "VS"
        vs_space = 150
        collage_width = img1.width + img2.width + vs_space
        collage_height = height

        # Белый фон
        collage = Image.new("RGB", (collage_width, collage_height), "white")
        collage.paste(img1, (0, 0))
        collage.paste(img2, (img1.width + vs_space, 0))

        # Рисуем "VS"
        draw = ImageDraw.Draw(collage)
        font = ImageFont.truetype("arial.ttf", 100)
        text = "VS"
        text_bbox = draw.textbbox((0, 0), text, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
        text_x = img1.width + (vs_space - text_width) // 2
        text_y = (collage_height - text_height) // 2
        draw.text((text_x, text_y), text, fill="black", font=font)

        # Сохраняем в BytesIO
        output = BytesIO()
        collage.save(output, format="JPEG")
        output.seek(0)
        return output
    except Exception as e:
        print(f"Ошибка создания коллажа: {e}")
        return None

def send_battle(char1, char2, collage_bytes):
    """Отправляет пост с коллажем и подписью."""
    caption = (
        f"⚔️ <b>Аниме-баттл!</b>\n\n"
        f"Сегодня сражаются:\n\n"
        f"🔥 <b>{char1['name']}</b> из аниме «{char1['anime']}»\n"
        f"⚡ <b>{char2['name']}</b> из аниме «{char2['anime']}»\n\n"
        f"Кто победит? Голосуйте реакциями:\n"
        f"👍 — за {char1['name']}\n"
        f"🔥 — за {char2['name']}\n\n"
        f"#аниме #баттл #голосование"
    )
    try:
        bot.send_photo(
            CHANNEL_ID,
            collage_bytes,
            caption=caption,
            parse_mode='HTML'
        )
        print(f"Баттл опубликован: {char1['name']} vs {char2['name']}")
    except Exception as e:
        print(f"Ошибка отправки баттла: {e}")

def main():
    characters = load_characters()
    if len(characters) < 2:
        print("Недостаточно персонажей для баттла (нужно минимум 2)")
        return

    # Выбираем двух случайных разных персонажей
    char1, char2 = random.sample(characters, 2)

    # Скачиваем изображения
    print(f"Скачиваю изображение для {char1['name']}...")
    img1_bytes = download_image(char1['image_url'])
    if not img1_bytes:
        print("Не удалось скачать первое изображение")
        return

    print(f"Скачиваю изображение для {char2['name']}...")
    img2_bytes = download_image(char2['image_url'])
    if not img2_bytes:
        print("Не удалось скачать второе изображение")
        return

    # Создаём коллаж
    print("Создаю коллаж...")
    collage_bytes = create_collage(img1_bytes, img2_bytes)
    if not collage_bytes:
        print("Не удалось создать коллаж")
        return

    # Отправляем
    send_battle(char1, char2, collage_bytes)

if __name__ == "__main__":
    main()
