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

bot = telebot.TeleBot(TELEGRAM_TOKEN)

def get_posts_from_series():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    r = requests.get(PIKABU_SERIES_URL, headers=headers, timeout=20)
    soup = BeautifulSoup(r.text, "lxml")

    posts = []
    for article in soup.select("article.story"):
        title_tag = article.select_one("a.story__title-link")
        title = title_tag.get_text(strip=True) if title_tag else "Без названия"
        link = title_tag.get("href") if title_tag else ""

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
                posts.append({"title": title, "link": link, "image_url": img_url})

    return posts

def download_image(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        r = requests.get(url, headers=headers, timeout=20)
        r.raise_for_status()
        return BytesIO(r.content)
    except Exception as e:
        print(f"Ошибка скачивания: {e}")
        return None

def main():
    posts = get_posts_from_series()
    if not posts:
        print("Не удалось найти мемы")
        return

    post = random.choice(posts)
    print(f"Выбран пост: {post['title']}")

    image_bytes = download_image(post["image_url"])
    if not image_bytes:
        print("Не удалось скачать картинку")
        return

    caption = f"{post['title']}\n\n#аниме #мем #пикабу"
    bot.send_photo(CHANNEL_ID, image_bytes, caption=caption)
    print("Мем опубликован.")

if __name__ == "__main__":
    main()
