import os
import random
import requests
import urllib3
import telebot
from io import BytesIO

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
VK_TOKEN = os.getenv("VK_TOKEN")

# Точно рабочие и открытые паблики с мемами
VK_DOMAINS = [
    "anime_memes",
    "animedebil",
    "anime_shitt",
    "anime.memes"
]

POSTED_IDS_FILE = "posted_memes.txt"
LAST_TYPE_FILE = "last_meme_type.txt"

bot = telebot.TeleBot(TELEGRAM_TOKEN)

def load_posted_ids():
    if not os.path.exists(POSTED_IDS_FILE):
        return set()
    with open(POSTED_IDS_FILE, 'r', encoding='utf-8') as f:
        return {line.strip() for line in f if line.strip()}

def save_posted_id(post_id):
    with open(POSTED_IDS_FILE, 'a', encoding='utf-8') as f:
        f.write(post_id + '\n')

def get_last_type():
    if os.path.exists(LAST_TYPE_FILE):
        with open(LAST_TYPE_FILE, 'r', encoding='utf-8') as f:
            return f.read().strip()
    return None

def save_last_type(meme_type):
    with open(LAST_TYPE_FILE, 'w', encoding='utf-8') as f:
        f.write(meme_type)

def get_vk_posts(domain):
    if not VK_TOKEN:
        print("[ERROR] VK_TOKEN не найден!")
        return []
        
    url = "https://api.vk.com/method/wall.get"
    params = {
        "domain": domain,
        "count": 20,
        "access_token": VK_TOKEN,
        "v": "5.131"
    }
    
    try:
        r = requests.get(url, params=params, timeout=20).json()
        
        # --- ДЕБАГ: СМОТРИМ ЧТО ОТВЕТИЛ ВК ---
        print(f"\n--- ОТВЕТ ОТ ПАБЛИКА {domain} ---")
        print(r)
        print("----------------------------------\n")
        # -------------------------------------
        
    except Exception as e:
        print(f"Ошибка запроса к ВК: {e}")
        return []
    
    posts = []
    for item in r.get("response", {}).get("items", []):
        if item.get("is_pinned"): 
            continue
        
        post_id = f"{item['owner_id']}_{item['id']}"
        
        raw_text = item.get("text", "")
        title = raw_text.split('\n')[0][:150].strip() if raw_text else "Без названия"
        title = title.replace("#", "")
        
        for attach in item.get("attachments", []):
            if attach["type"] == "photo":
                sizes = attach["photo"]["sizes"]
                best_pic = max(sizes, key=lambda x: x.get("width", 0))
                posts.append({"id": post_id, "title": title, "type": "image", "media_url": best_pic["url"]})
                break
                
            elif attach["type"] == "doc" and attach["doc"].get("ext") in ["gif", "mp4"]:
                posts.append({"id": post_id, "title": title, "type": "video", "media_url": attach["doc"]["url"]})
                break
                
    return posts

def download_media(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=20)
        r.raise_for_status()
        return BytesIO(r.content)
    except Exception as e:
        print(f"Ошибка скачивания медиа: {e}")
        return None

def main():
    posted_ids = load_posted_ids()
    all_posts = []

    for domain in VK_DOMAINS:
        posts = get_vk_posts(domain)
        all_posts.extend(posts)

    all_posts = [p for p in all_posts if p["id"] not in posted_ids]
    if not all_posts:
        print("Нет новых мемов в ВК")
        return

    last_type = get_last_type()
    desired_type = "video" if last_type == "image" else "image"

    print(f"last_type = {last_type}, desired_type = {desired_type}")

    filtered = [p for p in all_posts if p["type"] == desired_type]
    if not filtered:
        print(f"Нет мемов типа {desired_type}, берём любой")
        filtered = all_posts  

    post = random.choice(filtered)
    print(f"Выбран пост: {post['title']} (тип: {post['type']})")

    media_bytes = download_media(post["media_url"])
    if not media_bytes:
        print("Не удалось скачать медиа")
        return

    caption = f"{post['title']}\n\n#аниме #мем" if post['title'] and post['title'] != "Без названия" else "#аниме #мем"

    try:
        if post["type"] == "video":
            bot.send_video(CHANNEL_ID, media_bytes, caption=caption)
        else:
            bot.send_photo(CHANNEL_ID, media_bytes, caption=caption)
        
        save_posted_id(post["id"])
        save_last_type(post["type"])
        print("Мем опубликован.")
    except Exception as e:
        print(f"Ошибка отправки в Telegram: {e}")

if __name__ == "__main__":
    main()
