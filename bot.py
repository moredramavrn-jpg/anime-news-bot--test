import os
import re
import html
import io
import json
import feedparser
import telebot
import requests
from difflib import SequenceMatcher
from urllib.parse import urljoin, urlparse, unquote
from bs4 import BeautifulSoup
from telebot import types
from groq import Groq

# ===== НАСТРОЙКИ =====
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

RSS_URLS = [
    "https://www.goha.ru/rss/anime",
    "https://kg-portal.ru/rss/news_anime.rss"
]

POSTED_FILE = "posted.txt"

bot = telebot.TeleBot(TELEGRAM_TOKEN)
groq_client = Groq(api_key=GROQ_API_KEY)
GROQ_MODEL = "qwen/qwen3.6-27b"   # вернули доступную модель

# ---------- Работа с опубликованными ----------
def normalize_title(title):
    return re.sub(r'[^\w]', '', title.lower())

def load_posted():
    links = set()
    titles = set()
    if os.path.exists(POSTED_FILE):
        with open(POSTED_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line.startswith('LINK:'):
                    links.add(line[5:])
                elif line.startswith('TITLE:'):
                    titles.add(line[6:])
                elif line:
                    links.add(line)
    return links, titles

def save_posted(links, titles):
    with open(POSTED_FILE, 'w', encoding='utf-8') as f:
        for link in links:
            f.write(f"LINK:{link}\n")
        for title in titles:
            f.write(f"TITLE:{title}\n")

def is_duplicate(link, title, links, titles):
    if link and link in links:
        return True
    norm_title = normalize_title(title)
    if norm_title in titles:
        return True
    for existing_title in titles:
        if SequenceMatcher(None, norm_title, existing_title).ratio() > 0.9:
            return True
    return False

# ---------- HTML / парсинг ----------
def clean_html(raw_html):
    if not raw_html:
        return ""
    soup = BeautifulSoup(raw_html, "lxml")
    for script in soup(["script", "style"]):
        script.decompose()
    text = soup.get_text(separator=" ")
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def make_absolute(url, base_domain):
    if url.startswith('//'):
        return 'https:' + url
    if url.startswith('/'):
        return urljoin(base_domain, url)
    return url

def get_page_soup(url):
    try:
        domain = urlparse(url).netloc
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3',
            'Referer': f'https://{domain}/',
        }
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        return BeautifulSoup(r.text, 'lxml')
    except Exception as e:
        print(f"Ошибка загрузки {url}: {e}")
        return None

def extract_full_text_from_page(soup):
    if not soup:
        return ""

    main_content = soup.select_one('div.editor-body')
    if not main_content:
        main_content = soup.select_one('div.news_text')

    if not main_content:
        selectors = [
            'article', 'div.news-content', 'div.content', 'div.news-text',
            'div.post-content', 'div.entry-content', 'div.article-content',
            'div.news-detail__text', 'div.b-news__text', 'div.js-news-text',
            'div.article__text', 'div.text-content', 'div.news-item__text',
            'div.detail__text', 'div.news-full__text', 'div.article-body'
        ]
        for selector in selectors:
            main_content = soup.select_one(selector)
            if main_content:
                break

    if main_content:
        return clean_html(str(main_content))
    return ""

def fetch_full_text(entry):
    link = entry.get('link')
    if link:
        soup = get_page_soup(link)
        if soup:
            full_text = extract_full_text_from_page(soup)
            if full_text:
                return full_text
    summary = entry.get('summary', '') or entry.get('description', '')
    if summary:
        return clean_html(summary)
    return ""

# ---------- Изображения ----------
def extract_image_from_page(soup, page_url=None):
    if not soup:
        return None

    selectors = [
        'div.editor-body-image img', 'div.editor-body img',
        'div.news_cover_center img', 'div.news_text img',
        'div.news_box img', 'article img', 'div.news_image img',
        'div.article_image img', 'div.full_news img',
        'div.news_content img', 'div.news-full__text img',
    ]

    for selector in selectors:
        img_tag = soup.select_one(selector)
        if img_tag:
            src = (img_tag.get('src') or img_tag.get('data-src') or
                   img_tag.get('data-original') or img_tag.get('data-lazy-src'))
            if src:
                return make_absolute(src, page_url or 'https://kg-portal.ru')

    news_text = soup.select_one('div.news_text')
    if news_text:
        for img in news_text.find_all('img'):
            src = (img.get('src') or img.get('data-src') or
                   img.get('data-original') or img.get('data-lazy-src'))
            if src:
                return make_absolute(src, page_url or 'https://kg-portal.ru')

    og_image = soup.select_one('meta[property="og:image"]')
    if og_image and og_image.get('content'):
        return make_absolute(og_image['content'], page_url or 'https://kg-portal.ru')

    for img in soup.find_all('img'):
        src = (img.get('src') or img.get('data-src') or
               img.get('data-original') or img.get('data-lazy-src'))
        if src and re.search(r'\.(jpg|jpeg|png|webp)(\?.*)?$', src, re.IGNORECASE):
            return make_absolute(src, page_url or 'https://kg-portal.ru')

    return None

def fetch_image_url(entry, soup=None):
    link = entry.get('link')
    if soup is None and link:
        soup = get_page_soup(link)

    if soup:
        image = extract_image_from_page(soup, link)
        if image:
            return image

    image = extract_image_url_from_entry(entry)
    if image:
        return image

    print(f"Картинка не найдена для {link}")
    return None

def extract_image_url_from_entry(entry):
    base_domain = 'https://www.goha.ru'
    if 'link' in entry:
        link = entry.get('link', '')
        if 'kg-portal.ru' in link:
            base_domain = 'https://kg-portal.ru'

    if 'media_content' in entry:
        for media in entry.media_content:
            if 'url' in media:
                return make_absolute(media['url'], base_domain)
    if 'media_thumbnail' in entry:
        for media in entry.media_thumbnail:
            if 'url' in media:
                return make_absolute(media['url'], base_domain)
    if 'enclosures' in entry and entry.enclosures:
        for enc in entry.enclosures:
            if 'href' in enc and enc.get('type', '').startswith('image'):
                return make_absolute(enc['href'], base_domain)
            if 'url' in enc and enc.get('type', '').startswith('image'):
                return make_absolute(enc['url'], base_domain)
    summary = entry.get('summary', '') or entry.get('description', '')
    if summary:
        match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', summary, re.IGNORECASE)
        if match:
            return make_absolute(match.group(1), base_domain)
    content = entry.get('content', [])
    for c in content:
        if 'value' in c:
            match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', c['value'], re.IGNORECASE)
            if match:
                return make_absolute(match.group(1), base_domain)
    return None

# ---------- Видео ----------
def is_youtube_video(url):
    return ('youtube.com/watch' in url) or ('youtu.be/' in url)

def to_short_youtube_url(url):
    decoded_url = unquote(url)
    video_id = None
    if 'youtube.com/watch' in decoded_url:
        match = re.search(r'v=([^&]+)', decoded_url)
        if match:
            video_id = match.group(1)
    elif 'youtu.be/' in decoded_url:
        match = re.search(r'youtu\.be/([^?&]+)', decoded_url)
        if match:
            video_id = match.group(1)
    if video_id:
        return f"https://youtu.be/{video_id}"
    return decoded_url

def extract_video_url_from_page(soup):
    if not soup:
        return None, False

    # 1. Прямые видеофайлы (mp4/webm)
    video_tag = soup.select_one('video')
    if video_tag:
        src = video_tag.get('src')
        if src and re.search(r'\.(mp4|webm)(\?.*)?$', src, re.IGNORECASE):
            return src, False
        source_tag = video_tag.select_one('source')
        if source_tag and source_tag.get('src') and re.search(r'\.(mp4|webm)(\?.*)?$', source_tag['src'], re.IGNORECASE):
            return source_tag['src'], False

    og_video = soup.select_one('meta[property="og:video"]')
    if og_video and og_video.get('content'):
        url = og_video['content']
        if re.search(r'\.(mp4|webm)(\?.*)?$', url, re.IGNORECASE):
            return url, False

    scripts = soup.find_all('script')
    script_text = ' '.join(s.get_text() for s in scripts)
    pattern = r'(?:sources|vodQualities)[^{]*?["\']src["\']\s*:\s*["\']([^"\']+\.(?:mp4|webm))'
    match = re.search(pattern, script_text, re.IGNORECASE)
    if match:
        return html.unescape(match.group(1)), False

    # 2. YouTube
    yt_tag = soup.select_one('editor-body-youtube')
    if yt_tag and yt_tag.get('url'):
        url = yt_tag['url']
        if is_youtube_video(url):
            return url, True

    iframe = soup.select_one('iframe[src*="youtube.com/embed"], iframe[src*="youtu.be/"]')
    if iframe and iframe.get('src'):
        return iframe['src'], True

    if og_video and og_video.get('content'):
        url = og_video['content']
        if is_youtube_video(url):
            return url, True

    for a in soup.select('a.youtube'):
        href = a.get('href', '')
        match = re.search(r'url=([^&]+)', href)
        if match:
            url = html.unescape(match.group(1))
            if is_youtube_video(url):
                return url, True

    return None, False

def fetch_video_info(entry, soup=None):
    if soup is None:
        link = entry.get('link')
        if link:
            soup = get_page_soup(link)
    if soup:
        return extract_video_url_from_page(soup)
    return None, False

def download_image(url, referer=None):
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        if referer:
            headers['Referer'] = referer
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        return io.BytesIO(r.content)
    except Exception as e:
        print(f"Не удалось скачать изображение {url}: {e}")
        return None

# ---------- Обработка текста ----------
def clean_think_tags(text):
    end_idx = text.rfind('</think>')
    if end_idx != -1:
        return text[end_idx + len('</think>'):].strip()
    start_idx = text.find('<think>')
    if start_idx != -1:
        return text[start_idx + len('<think>'):].strip()
    return text.strip()

def clean_generated_text(text):
    text = clean_think_tags(text)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'^(?:Заголовок|Текст)\s*[:：]\s*', '', text, flags=re.IGNORECASE)
    text = text.strip('"\'')
    text = text.strip()
    return text

def format_news_body(text):
    if not text:
        return ""

    unwanted_phrases = [
        r'Читать дальше\s*→?',
        r'Читать полностью\s*:?',
        r'Источник\s*:',
    ]
    for pattern in unwanted_phrases:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)

    text = re.sub(r'\s+', ' ', text).strip()

    if '\n\n' in text:
        paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
        return "\n\n".join(paragraphs)

    sentences = re.split(r'(?<=[.!?])\s+', text)
    if len(sentences) <= 2:
        return text

    paragraphs = []
    current = []
    for sent in sentences:
        current.append(sent)
        if len(current) == 2:
            paragraphs.append(" ".join(current))
            current = []
    if current:
        paragraphs.append(" ".join(current))

    return "\n\n".join(paragraphs)

def escape_html(text):
    return html.escape(text, quote=False)

def make_hashtag(text):
    words = text.strip().split()
    clean_words = []
    for w in words:
        clean_w = re.sub(r'[^\w]', '', w, flags=re.UNICODE)
        if clean_w:
            clean_words.append(clean_w.lower())
    if not clean_words:
        return None
    return '#' + '_'.join(clean_words)

def extract_title_hashtag(title):
    match = re.search(r'«([^»]+)»', title)
    if not match:
        match = re.search(r'"([^"]+)"', title)
    if match:
        anime_name = match.group(1).strip()
        return make_hashtag(anime_name)
    return None

def build_post_html(title, body, emoji='📄'):
    title_esc = escape_html(title)
    body_esc = escape_html(body) if body else ""

    parts = [f"{emoji} <b>{title_esc}</b>"]

    if body_esc:
        body_with_quotes = re.sub(r'«[^»]+»', lambda m: f"<b>{m.group(0)}</b>", body_esc)
        parts.append("┄┄┄ ✦ ┄┄┄")
        parts.append(body_with_quotes)

    hashtags = ["#аниме", "#новости"]
    title_tag = extract_title_hashtag(title)
    if title_tag and title_tag not in hashtags:
        hashtags.append(title_tag)

    parts.append("")
    parts.append("🏷️ " + " ".join(hashtags))

    return "\n".join(parts)

def is_podcast_entry(entry):
    title = entry.get('title', '')
    link = entry.get('link', '')
    if re.match(r'^ЕВА-\d+', title, re.IGNORECASE):
        return True
    if 'ЕВА' in title.upper() and '/comments/' in link:
        return True
    if re.search(r'/eva\d+', link, re.IGNORECASE):
        return True
    return False

# ---------- Рерайт через Groq (JSON) ----------
def rewrite_news(title, body, target_len=800):
    print(f"Пытаюсь переписать через Groq: {title}")
    try:
        prompt = f"""Ты — редактор аниме-новостей. Перепиши следующие заголовок и текст новости так, чтобы они стали уникальными и краткими. Сократи текст до {target_len} символов, сохранив все ключевые факты и имена. Пиши на русском языке. Верни результат в виде JSON с полями "title" и "text".

Заголовок: {title}

Текст: {body[:1500]}
"""
        response = groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": "Ты — опытный копирайтер. Возвращай только JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.5,
            max_tokens=800
        )
        generated_text = response.choices[0].message.content.strip()
        # Пытаемся извлечь JSON из ответа
        json_match = re.search(r'\{.*\}', generated_text, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group(0))
            new_title = data.get('title', title)
            new_body = data.get('text', body)
            if new_title and new_body and (new_title != title or new_body != body):
                return new_title, new_body
        else:
            print("JSON не найден, используем оригинал")
            return title, body
    except Exception as e:
        print(f"Ошибка при рерайте через Groq: {e}")
        return title, body

def truncate_by_paragraphs(text, max_len):
    if len(text) <= max_len:
        return text
    paragraphs = text.split('\n\n')
    result = []
    current_len = 0
    for p in paragraphs:
        if current_len + len(p) + 2 > max_len:
            break
        result.append(p)
        current_len += len(p) + 2
    if not result:
        return text[:max_len]
    return '\n\n'.join(result)

def send_post(title, body, link, image_url, video_url, is_youtube):
    if video_url and is_youtube:
        emoji = '🎬'
        target_len = 800
    elif video_url and not is_youtube:
        emoji = '🎞️'
        target_len = 800
    elif image_url:
        emoji = '🖼️'
        target_len = 800
    else:
        emoji = '📄'
        target_len = 1500

    if GROQ_API_KEY:
        print("Вызываю rewrite_news...")
        title, body = rewrite_news(title, body, target_len=target_len)
        print("Рерайт завершён")
    else:
        print("GROQ_API_KEY не задан, пропускаю рерайт")

    body = format_news_body(body)

    if target_len:
        body = truncate_by_paragraphs(body, target_len)

    message_text = build_post_html(title, body, emoji)

    if video_url and not is_youtube:
        try:
            bot.send_video(CHANNEL_ID, video_url, caption=message_text[:1024], parse_mode='HTML')
            return
        except Exception as e:
            print(f"Не удалось отправить видео: {e}")

    if video_url and is_youtube:
        short_url = to_short_youtube_url(video_url)
        bot.send_message(
            CHANNEL_ID,
            message_text + f"\n\nСмотреть: {short_url}",
            parse_mode='HTML',
            disable_web_page_preview=False
        )
        return

    if image_url:
        image_file = download_image(image_url, referer=link)
        if image_file:
            try:
                bot.send_photo(CHANNEL_ID, image_file, caption=message_text[:1024], parse_mode='HTML')
                return
            except Exception as e:
                print(f"Не удалось отправить фото: {e}")

    bot.send_message(CHANNEL_ID, message_text, parse_mode='HTML', disable_web_page_preview=True)

def main():
    print(f"GROQ_API_KEY задан: {bool(GROQ_API_KEY)}")
    if not GROQ_API_KEY:
        print("ВНИМАНИЕ: GROQ_API_KEY отсутствует, рерайт отключён")

    links, titles = load_posted()
    new_posts = 0

    for rss_url in RSS_URLS:
        print(f"Обрабатываю ленту: {rss_url}")
        try:
            feed = feedparser.parse(rss_url)
        except Exception as e:
            print(f"Не удалось получить ленту {rss_url}: {e}")
            continue

        for entry in feed.entries[:10]:
            if is_podcast_entry(entry):
                print(f"Пропущен подкаст: {entry.get('title')}")
                continue

            link = entry.get('link', '')
            title = entry.get('title', 'Без названия')
            if is_duplicate(link, title, links, titles):
                print(f"Дубликат пропущен: {title}")
                continue

            soup = get_page_soup(link) if link else None
            full_text = extract_full_text_from_page(soup) if soup else fetch_full_text(entry)
            image_url = fetch_image_url(entry, soup)
            video_url, is_youtube = fetch_video_info(entry, soup)

            try:
                send_post(title, full_text, link, image_url, video_url, is_youtube)
                links.add(link)
                titles.add(normalize_title(title))
                new_posts += 1
                print(f"Опубликовано: {title}")
            except Exception as e:
                print(f"Ошибка отправки для {link}: {e}")

    if new_posts > 0:
        save_posted(links, titles)
        print(f"Сохранено {new_posts} новых записей в {POSTED_FILE}")
    else:
        print("Новых новостей нет.")

if __name__ == "__main__":
    main()
