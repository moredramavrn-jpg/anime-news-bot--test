def rewrite_news(title, body):
    try:
        paraphraser_url = "https://api-inference.huggingface.co/models/mrm8488/bert2bert_shared-russian-paraphraser"
        headers = {
            "Authorization": f"Bearer {HF_API_KEY}",
            "Content-Type": "application/json"
        }

        def paraphrase_text(text, max_length=512):
            payload = {
                "inputs": text,
                "parameters": {
                    "max_length": max_length,
                    "temperature": 1.2,
                    "top_p": 0.9,
                    "do_sample": True,
                    "early_stopping": False,
                    "num_beams": 1,
                    "repetition_penalty": 1.2
                }
            }
            response = requests.post(paraphraser_url, headers=headers, json=payload, timeout=25)
            response.raise_for_status()
            result = response.json()
            if isinstance(result, list) and len(result) > 0:
                return result[0].get('generated_text', text)
            elif isinstance(result, dict):
                return result.get('generated_text', text)
            return text

        new_title = paraphrase_text(title, max_length=100)
        # Берём только начало текста, чтобы не перегружать модель
        body_part = body[:1000] if len(body) > 1000 else body
        new_body = paraphrase_text(body_part, max_length=1024)

        # Проверяем, что текст действительно изменился
        if (SequenceMatcher(None, title, new_title).ratio() < 0.95 and
            SequenceMatcher(None, body_part, new_body).ratio() < 0.95):
            return new_title, new_body
        else:
            print("Парафраз не изменил текст, возвращаю оригинал")
            return title, body
    except Exception as e:
        print(f"Ошибка парафраза: {e}")
        return title, body
