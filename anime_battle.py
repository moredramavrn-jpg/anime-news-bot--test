from PIL import Image, ImageDraw, ImageFont

# Открываем картинки
img1 = Image.open("character1.jpg")
img2 = Image.open("character2.jpg")

# Приводим к одинаковой высоте
height = 500
img1 = img1.resize((int(img1.width * height / img1.height), height))
img2 = img2.resize((int(img2.width * height / img2.height), height))

# Создаём коллаж
collage = Image.new("RGB", (img1.width + img2.width + 100, height), "white")
collage.paste(img1, (0, 0))
collage.paste(img2, (img1.width + 100, 0))

# Добавляем текст "VS"
draw = ImageDraw.Draw(collage)
font = ImageFont.truetype("arial.ttf", 80)
draw.text((img1.width + 10, height // 2 - 40), "VS", fill="black", font=font)

# Сохраняем
collage.save("collage.jpg")
