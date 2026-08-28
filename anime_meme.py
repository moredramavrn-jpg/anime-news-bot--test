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

PIKABU_SERIES_URLS = [
    "https://pikabu.ru/series/anime_memyi_59562",
    "https://pikabu.ru/series/podborki_randomnyikh_anime_memov_31394"
]

POSTED_IDS_FILE = "posted_memes.txt"

bot = telebot.TeleBot(TELEGRAM_TOKEN)

def load_posted_ids():
    if not os.path.exists(POSTED_IDS_FILE):
        return set()
    with open(POSTED_IDS_FILE, 'r', encoding='utf-8') as f:
        return {line.strip() for line in f if line.strip()}

def save_posted_id(post_id):
    with open(POSTED_IDS_FILE, 'a', encoding='utf-8') as f:
        f.write(post_id + '\n')

def get_posts_from_series(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    r = requests.get(url, headers=headers, timeout=20)
    soup = BeautifulSoup(r.text, "lxml")

    posts = []
    for article in soup.select("article.story"):
        post_id = article.get("data-story-id", "")

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
        video_url = None

        video_tag = article.select_one("video")
        if video_tag:
            video_url = video_tag.get("src") or video_tag.get("data-src")

        if not video_url:
            iframe = article.select_one("iframe")
            if iframe:
                video_url = iframe.get("src")

        if not video_url:
            for a in article.select("a[href]"):
                href = a.get("href", "")
                if any(ext in href for ext in [".mp4", ".webm", ".mov", "video"]):
                    video_url = href
                    break

        if video_url:
            if video_url.startswith("//"):
                video_url = "https:" + video_url
            posts.append({"id": post_id, "title": title, "link": link, "type": "video", "media_url": video_url})
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
                posts.append({"id": post_id, "title": title, "link": link, "type": "image", "media_url": img_url})

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

def main():
    posted_ids = load_posted_ids()
    all_posts = []

    for url in PIKABU_SERIES_URLS:
        posts = get_posts_from_series(url)
        all_posts.extend(posts)

    # Исключаем опубликованные
    all_posts = [p for p in all_posts if p["id"] not in posted_ids]
    if not all_posts:
        print("Нет новых мемов")
        return

    # Выбираем только картинки (или видео, если появятся)
    images = [p for p in all_posts if p["type"] == "image"]
    if not images:
        print("Нет картинок")
        return

    post = random.choice(images)
    print(f"Выбран пост: {post['title']}")

    media_bytes = download_media(post["media_url"])
    if not media_bytes:
        print("Не удалось скачать медиа")
        return

    caption = f"{post['title']}\n\n#аниме #мем"

    bot.send_photo(CHANNEL_ID, media_bytes, caption=caption)

    save_posted_id(post["id"])
    print("Мем опубликован.")

if __name__ == "__main__":
    main()
