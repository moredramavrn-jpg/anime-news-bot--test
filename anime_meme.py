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
GIGACHAT_AUTHORIZATION_KEY = os.getenv("GIGACHAT_AUTHORIZATION_KEY")

ANILIST_API = "https://graphql.anilist.co"

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

def get_random_anime_image():
    """Получает случайный постер аниме через AniList API."""
    query = """
    query ($page: Int) {
      Page(page: $page, perPage: 1) {
        media(type: ANIME, sort: POPULARITY_DESC) {
          coverImage {
            extraLarge
            large
          }
        }
      }
    }
    """
    page = random.randint(1, 50)
    variables = {"page": page}
    try:
        r = requests.post(ANILIST_API, json={"query": query, "variables": variables}, timeout=20)
        r.raise_for_status()
        data = r.json()
        media_list = data["data"]["Page"]["media"]
        if media_list:
            img_url = media_list[0]["coverImage"]["extraLarge"] or media_list[0]["coverImage"]["large"]
            return img_url
    except Exception as e:
        print(f"Ошибка получения картинки: {e}")
    return None

def generate_meme_text():
    """Генерирует чёрную юмористическую подпись через GigaChat."""
    token = get_gigachat_token()
    if not token:
        return "Когда аниме закончилось на самом интересном месте"

    prompt = (
        "Придумай короткую смешную подпись для аниме-мема в стиле чёрного юмора. "
        "Не перегибай с жестью, но и не делай слишком мягко. "
        "Максимум 8 слов. Без кавычек. Выведи только текст."
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-Request-ID": str(uuid.uuid4()),
        "X-Session-ID": str(uuid.uuid4()),
        "User-Agent": "AnimeMemeBot/1.0"
    }
    payload = {
        "model": "GigaChat-3-Ultra",
        "messages": [
            {"role": "system", "content": "Ты — автор мемов."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.9,
        "max_tokens": 100
    }
    try:
        r = requests.post(
            "https://api.giga.chat/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=30,
            verify=False
        )
        r.raise_for_status()
        data = r.json()
        text = data["choices"][0]["message"]["content"].strip()
        text = text.strip('«»"')
        return text
    except Exception as e:
        print(f"Ошибка GigaChat: {e}")
        return "Когда аниме закончилось на самом интересном месте"

def download_image(url):
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        r = requests.get(url, headers=headers, timeout=20)
        r.raise_for_status()
        return BytesIO(r.content)
    except Exception as e:
        print(f"Ошибка скачивания картинки: {e}")
        return None

def wrap_text(draw, text, font, max_width):
    """Переносит текст по словам, чтобы он влезал в max_width."""
    words = text.split()
    lines = []
    current = ""
    for word in words:
        test = (current + " " + word).strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return "\n".join(lines)

def add_text_to_image(image_bytes, text):
    """Добавляет текст на картинку снизу с переносом по ширине."""
    try:
        img = Image.open(image_bytes).convert("RGB")
        width, height = img.size

        # Резервируем место под текст
        text_space = 160
        new_img = Image.new("RGB", (width, height + text_space), "black")
        new_img.paste(img, (0, 0))

        draw = ImageDraw.Draw(new_img)
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 32)
        except:
            font = ImageFont.load_default()

        # Максимальная ширина текста = ширина картинки минус отступы
        max_text_width = width - 40
        wrapped = wrap_text(draw, text, font, max_text_width)

        # Вычисляем высоту текста
        text_bbox = draw.multiline_textbbox((0, 0), wrapped, font=font, align="center")
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]

        x = (width - text_width) // 2
        y = height + (text_space - text_height) // 2
        draw.multiline_text((x, y), wrapped, fill="white", font=font, align="center")

        output = BytesIO()
        new_img.save(output, format="JPEG")
        output.seek(0)
        return output
    except Exception as e:
        print(f"Ошибка наложения текста: {e}")
        return None

def send_meme(image_bytes):
    caption = "#аниме #мем #юмор"
    try:
        bot.send_photo(
            CHANNEL_ID,
            image_bytes,
            caption=caption
        )
        print("Мем опубликован.")
    except Exception as e:
        print(f"Ошибка отправки мема: {e}")

def main():
    print("Получаю случайную картинку...")
    image_url = get_random_anime_image()
    if not image_url:
        print("Не удалось получить картинку")
        return

    img_bytes = download_image(image_url)
    if not img_bytes:
        print("Не удалось скачать картинку")
        return

    print("Генерирую подпись...")
    meme_text = generate_meme_text()
    print(f"Подпись: {meme_text}")

    print("Накладываю текст...")
    meme_image = add_text_to_image(img_bytes, meme_text)
    if not meme_image:
        print("Не удалось создать мем")
        return

    send_meme(meme_image)

if __name__ == "__main__":
    main()
