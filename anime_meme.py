import os
import random
import requests
import urllib3
import telebot
from io import BytesIO
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")

PIKABU_SERIES_URL = "https://pikabu.ru/series/anime_memyi_59562"
LAST_TYPE_FILE = "last_meme_type.txt"

bot = telebot.TeleBot(TELEGRAM_TOKEN)

def get_posts_from_series():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    r = requests.get(PIKABU_SERIES_URL, headers=headers, timeout=20)
    soup = BeautifulSoup(r.text, "lxml")

    posts = []
    for article in soup.select("article.story"):
        # Пропускаем посты с текстом
        content = article.select_one(".story__content")
        if content:
            text_blocks = content.select(".story-block_type_text")
            if text_blocks:
                continue

        title_tag = article.select_one("a.story__title-link")
        title = title_tag.get_text(strip=True) if title_tag else "Без названия"
        link = title_tag.get("href") if title_tag else ""

        # Видео
        video_tag = article.select_one("video")
        if video_tag:
            video_url = video_tag.get("src") or video_tag.get("data-src")
            if video_url and video_url.startswith("//"):
                video_url = "https:" + video_url
            posts.append({"title": title, "link": link, "type": "video", "media_url": video_url})
            continue

        # Картинка
        img_tag = article.select_one("img.story-image__image")
        if img_tag:
            img_url = (
                img_tag.get("data-large-image") or
                img_tag.get("data-src") or
                img_tag.get("src")
            )
            if img_url and img_url.startswith("//"):
                img_url = "https:" + img_url
            if img_url:
                posts.append({"title": title, "link": link, "type": "image", "media_url": img_url})

    return posts

def download_media(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        r = requests.get(url, headers=headers, timeout=20)
        r.raise_for_status()
        return BytesIO(r.content)
    except Exception as e:
        print(f"Ошибка скачивания: {e}")
        return None

def get_last_type():
    if os.path.exists(LAST_TYPE_FILE):
        with open(LAST_TYPE_FILE, 'r', encoding='utf-8') as f:
            return f.read().strip()
    return None

def save_last_type(meme_type):
    with open(LAST_TYPE_FILE, 'w', encoding='utf-8') as f:
        f.write(meme_type)

def main():
    posts = get_posts_from_series()
    if not posts:
        print("Не удалось найти мемы")
        return

    last_type = get_last_type()

    # Определяем, какой тип нам нужен в этот раз (чередуем)
    desired_type = "video" if last_type == "image" else "image"

    # Отбираем посты нужного типа
    filtered = [p for p in posts if p["type"] == desired_type]
    if not filtered:
        # Если нужного типа нет, берём любой
        filtered = posts

    post = random.choice(filtered)
    print(f"Выбран пост: {post['title']} (тип: {post['type']})")

    media_bytes = download_media(post["media_url"])
    if not media_bytes:
        print("Не удалось скачать медиа")
        return

    caption = f"{post['title']}\n\n#аниме #мем #пикабу"

    if post["type"] == "video":
        bot.send_video(CHANNEL_ID, media_bytes, caption=caption)
    else:
        bot.send_photo(CHANNEL_ID, media_bytes, caption=caption)

    # Сохраняем тип опубликованного мема
    save_last_type(post["type"])

    print("Мем опубликован.")

if __name__ == "__main__":
    main()
