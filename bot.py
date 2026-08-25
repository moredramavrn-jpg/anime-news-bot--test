def fetch_kanobu_entries():
    print("Загружаю Канобу...")
    soup = get_page_soup(KANOBU_URL)
    if not soup:
        print("Не удалось загрузить страницу Канобу")
        return []
    print("Страница загружена, ищу JSON-LD...")
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            data = json.loads(script.string)
            print(f"Найден JSON-LD типа: {data.get('@type')}")
            if data.get('@type') == 'ItemList':
                items = data.get('itemListElement', [])
                print(f"Найдено элементов: {len(items)}")
                for item in items[:2]:
                    print(item)
                return [{'title': item.get('name'), 'link': item.get('url')} for item in items if item.get('name') and item.get('url')][:10]
        except Exception as e:
            print(f"Ошибка парсинга JSON-LD: {e}")
    print("JSON-LD с ItemList не найден")
    return []
