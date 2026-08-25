def rewrite_news(title, body):
    """
    Пытается переписать заголовок и текст через специализированную модель парафраза.
    Если модель недоступна или результат слишком похож, возвращает оригинал.
    """
    try:
        # Модель для парафраза на русском
        paraphraser_url = "https://api-inference.huggingface.co/models/cointegrated/rut5-base-paraphraser"
        headers = {
            "Authorization": f"Bearer {HF_API_KEY}",
            "Content-Type": "application/json"
        }

        # Функция для парафраза одного текста
        def paraphrase_text(text):
            payload = {
                "inputs": text,
                "parameters": {
                    "max_length": 200,
                    "num_beams": 5,
                    "early_stopping": True
                }
            }
            response = requests.post(paraphraser_url, headers=headers, json=payload, timeout=20)
            response.raise_for_status()
            result = response.json()
            if isinstance(result, list) and len(result) > 0:
                return result[0].get('generated_text', text)
            elif isinstance(result, dict):
                return result.get('generated_text', text)
            return text

        # Переписываем заголовок
        new_title = paraphrase_text(title)

        # Переписываем текст (для скорости ограничиваем длину)
        max_body_len = 3000
        if len(body) > max_body_len:
            body_part = body[:max_body_len]
        else:
            body_part = body
        new_body = paraphrase_text(body_part)

        # Проверяем, насколько изменился текст
        if (SequenceMatcher(None, title, new_title).ratio() < 0.9 and
            SequenceMatcher(None, body_part, new_body).ratio() < 0.9):
            return new_title, new_body
        else:
            print("Результат парафраза слишком похож на оригинал, оставляем оригинал")
            return title, body

    except Exception as e:
        print(f"Ошибка при парафразе через Hugging Face: {e}")
        return title, body
