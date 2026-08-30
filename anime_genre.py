import os
import random
import json
import uuid
import time
import urllib3
import telebot
import requests

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
GIGACHAT_AUTHORIZATION_KEY = os.getenv("GIGACHAT_AUTHORIZATION_KEY")

USED_GENRES_FILE = "used_genres.json"
USED_ANIME_FILE = "used_anime_genre.json"

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

def giga_request(prompt, max_tokens=500):
    token = get_gigachat_token()
    if not token:
        return ""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-Request-ID": str(uuid.uuid4()),
        "X-Session-ID": str(uuid.uuid4()),
        "User-Agent": "AnimeGenreBot/1.0"
    }
    payload = {
        "model": "GigaChat-3-Ultra",
        "messages": [
            {"role": "system", "content": "Ты — эксперт по аниме."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.5,
        "max_tokens": max_tokens
    }
    try:
        r = requests.post("https://api.giga.chat/v1/chat/completions",
                          headers=headers, json=payload, timeout=30, verify=False)
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"Ошибка GigaChat: {e}")
        return ""

def load_used_genres():
    if os.path.exists(USED_GENRES_FILE):
        with open(USED_GENRES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_used_genres(genres):
    with open(USED_GENRES_FILE, 'w', encoding='utf-8') as f:
        json.dump(genres, f, ensure_ascii=False)

def load_used_anime():
    if os.path.exists(USED_ANIME_FILE):
        with open(USED_ANIME_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_used_anime(anime_dict):
    with open(USED_ANIME_FILE, 'w', encoding='utf-8') as f:
        json.dump(anime_dict, f, ensure_ascii=False)

def get_genre():
    used = load_used_genres()
    if used:
        prompt = "Назови случайный жанр аниме, которого нет в этом списке: " + ", ".join(used) + ".\nВыведи только название жанра."
    else:
        prompt = "Назови случайный жанр аниме.\nВыведи только название жанра."
    genre = giga_request(prompt, max_tokens=50).strip()
    return genre

def get_genre_info(genre):
    prompt = f"Объясни жанр аниме «{genre}» кратко, в 2-3 предложениях."
    return giga_request(prompt, max_tokens=200).strip()

def get_anime_for_genre(genre, used_anime):
    used_list = used_anime.get(genre, [])
    if used_list:
        prompt = (
            f"Назови 3 популярных аниме жанра «{genre}», которых нет в этом списке: {', '.join(used_list)}.\n"
            "Для каждого дай краткое описание в 1 предложение.\n"
            "Выведи в формате: Название — описание"
        )
    else:
        prompt = (
            f"Назови 3 популярных аниме жанра «{genre}».\n"
            "Для каждого дай краткое описание в 1 предложение.\n"
            "Выведи в формате: Название — описание"
        )
    content = giga_request(prompt, max_tokens=500)
    anime_list = []
    for line in content.split('\n'):
        if '—' in line:
            name, desc = line.split('—', 1)
            anime_list.append({"name": name.strip(), "desc": desc.strip()})
    return anime_list

def main():
    genre = get_genre()
    if not genre:
        print("Не удалось получить жанр")
        return

    genre_info = get_genre_info(genre)
    used_anime = load_used_anime()
    anime_list = get_anime_for_genre(genre, used_anime)

    if len(anime_list) < 3:
        print("Не удалось получить достаточно аниме")
        return

    post = f"🎭 <b>Жанр: {genre}</b>\n\n{genre_info}\n\n📺 <b>Три аниме этого жанра:</b>\n"
    for idx, anime in enumerate(anime_list[:3], 1):
        post += f"{idx}. <b>{anime['name']}</b> — {anime['desc']}\n"
    post += "\n#аниме #жанр"

    bot.send_message(CHANNEL_ID, post, parse_mode='HTML', disable_web_page_preview=True)

    used_genres = load_used_genres()
    used_genres.append(genre)
    save_used_genres(used_genres)

    used_anime.setdefault(genre, [])
    used_anime[genre].extend([a['name'] for a in anime_list[:3]])
    save_used_anime(used_anime)

    print("Пост опубликован.")

if __name__ == "__main__":
    main()
