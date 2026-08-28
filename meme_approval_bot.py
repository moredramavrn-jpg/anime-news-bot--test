import os
import re
import random
import requests
import telebot
import feedparser
from io import BytesIO
from bs4 import BeautifulSoup
from telebot import types

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
YOUR_USER_ID = os.getenv("YOUR_USER_ID")  # ваш Telegram user ID

PIKABU_RSS = "https://pikabu.ru/community/anime?rss=1"

bot = telebot.TeleBot(TELEGRAM_TOKEN)

# Храним текущий мем для каждого пользователя
current_meme = {}

def get_posts_from_rss():
    """Читает RSS Пикабу и возвращает посты с картинками."""
    feed = feedparser.parse(PIKABU_RSS)
    posts = []
    for entry in feed.entries:
        title = entry.get("title", "Без названия")
        link = entry.get("link", "")
        image_url = None

        # Ищем картинку в media_content
        if "media_content" in entry:
            for media in entry.media_content:
                if "url" in media:
                    image_url = media["url"]
                    break

        # Если нет, пробуем вытащить из summary/description
        if not image_url:
            summary = entry.get("summary", "") or entry.get("description", "")
            soup = BeautifulSoup(summary, "lxml")
            img_tag = soup.find("img")
            if img_tag:
                src = img_tag.get("src")
                if src:
                    image_url = src

        if image_url:
            posts.append({
                "title": title,
                "link": link,
                "image_url": image_url
            })
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

def send_meme_for_approval(chat_id):
    posts = get_posts_from_rss()
    if not posts:
        bot.send_message(chat_id, "Не удалось найти мемы")
        return

    post = random.choice(posts)
    current_meme[chat_id] = post

    image_bytes = download_image(post["image_url"])
    if not image_bytes:
        bot.send_message(chat_id, "Не удалось скачать картинку, ищу другую...")
        send_meme_for_approval(chat_id)
        return

    markup = types.InlineKeyboardMarkup()
    btn_ok = types.InlineKeyboardButton("✅ Ок", callback_data="approve_meme")
    btn_no = types.InlineKeyboardButton("❌ Не ок", callback_data="reject_meme")
    markup.add(btn_ok, btn_no)

    caption = f"<b>{post['title']}</b>\n\nПодходит?"
    bot.send_photo(chat_id, image_bytes, caption=caption, parse_mode='HTML', reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def handle_approval(call):
    chat_id = call.message.chat.id

    if call.data == "approve_meme":
        meme = current_meme.get(chat_id)
        if meme:
            # Публикуем в канал
            image_bytes = download_image(meme["image_url"])
            if image_bytes:
                caption = f"{meme['title']}\n\n#аниме #мем #пикабу"
                bot.send_photo(CHANNEL_ID, image_bytes, caption=caption)
                bot.send_message(chat_id, "Опубликовано!")
            else:
                bot.send_message(chat_id, "Не удалось скачать картинку для публикации")
        else:
            bot.send_message(chat_id, "Мем не найден")

    elif call.data == "reject_meme":
        bot.send_message(chat_id, "Ищу другой мем...")
        send_meme_for_approval(chat_id)

    # Убираем кнопки
    bot.edit_message_reply_markup(chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=None)

@bot.message_handler(commands=["start", "meme"])
def handle_start(message):
    if str(message.chat.id) != str(YOUR_USER_ID):
        bot.send_message(message.chat.id, "Нет доступа")
        return
    send_meme_for_approval(message.chat.id)

if __name__ == "__main__":
    print("Бот запущен...")
    bot.polling(none_stop=True)
