def rewrite_news(title, body):
    print(f"Вызываю rewrite_news. HF_API_KEY задан: {bool(HF_API_KEY)}")
    if not HF_API_KEY:
        return title, body
    # остальной код...
