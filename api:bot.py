
import os
import re
import json
import requests
from bs4 import BeautifulSoup

from aiogram import Bot, Dispatcher, types
from aiogram.types import Update, InputMediaPhoto
from aiogram.fsm.storage.memory import MemoryStorage

TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

headers = {
    "User-Agent": "Mozilla/5.0"
}

# =========================
# 🧠 ОЧИСТКА ОПИСУ
# =========================
def clean(text):
    if not text:
        return "Опис не знайдено"
    text = re.sub(r"\s+", " ", text)
    return text[:1200]


# =========================
# 📸 ФОТО (максимум)
# =========================
def extract_images(soup):
    images = set()

    for img in soup.find_all("img"):
        for attr in ["src", "data-src", "data-lazy"]:
            src = img.get(attr)
            if src and "http" in src:
                if not any(x in src for x in ["logo", "icon"]):
                    images.add(src)

    # JSON (OLX / RIA / LUN)
    for script in soup.find_all("script"):
        if script.string:
            urls = re.findall(r'https://[^"]+\.(jpg|jpeg|png|webp)', script.string)
            for u in urls:
                images.add(u)

    return list(images)[:10]


# =========================
# 📊 ДАНІ
# =========================
def extract_data(text):
    def find(pattern):
        m = re.search(pattern, text)
        return m.group(1) if m else None

    data = {}

    data["rooms"] = find(r"(\d+)\s*кім")
    data["area"] = find(r"(\d+\.?\d*)\s*м²")
    data["price"] = find(r"(\d[\d\s]+)\s?\$")
    
    floor = re.search(r"(\d+)\s*/\s*(\d+)", text)
    if floor:
        data["floor"] = f"{floor.group(1)}/{floor.group(2)}"

    data["year"] = find(r"(20\d{2})")

    # будинок
    if "цегл" in text.lower():
        data["building"] = "цегляний"
    elif "панел" in text.lower():
        data["building"] = "панельний"

    # опалення
    if "централіз" in text.lower():
        data["heating"] = "централізоване"
    elif "автоном" in text.lower():
        data["heating"] = "автономне"

    # адреса
    addr = re.search(r"(вул\.|просп\.|ЖК)[^,.]+", text)
    if addr:
        data["address"] = addr.group(0)

    return data


# =========================
# 🌍 ПАРСИНГ
# =========================
def parse(url):
    r = requests.get(url, headers=headers, timeout=10)
    soup = BeautifulSoup(r.text, "html.parser")

    text = soup.get_text(" ", strip=True)

    data = extract_data(text)

    # опис
    description = ""
    for div in soup.find_all("div"):
        t = div.get_text(" ", strip=True)
        if len(t) > 300:
            description = t
            break

    data["description"] = clean(description)

    # фото
    data["images"] = extract_images(soup)

    return data


# =========================
# 📝 ФОРМАТ
# =========================
def format_text(d):
    return f"""
🏠 Кількість кімнат: {d.get('rooms') or '---'}
📍 Адреса: {d.get('address') or '---'}

💰 Ціна: {d.get('price') or '---'}
📐 Площа: {d.get('area') or '---'}
🏢 Поверх: {d.get('floor') or '---'}

🧱 Тип будинку: {d.get('building') or '---'}
📅 Рік: {d.get('year') or '---'}
🔥 Опалення: {d.get('heating') or '---'}

📝 Опис:
{d.get('description')}
"""


# =========================
# 🤖 ОБРОБКА
# =========================
@dp.message()
async def handle(message: types.Message):
    url = message.text.strip()

    if not url.startswith("http"):
        await message.answer("❌ Відправ посилання")
        return

    data = parse(url)

    if data["images"]:
        media = [InputMediaPhoto(media=img) for img in data["images"]]
        try:
            await message.answer_media_group(media)
        except:
            await message.answer("⚠️ Фото не відправились")

    await message.answer(format_text(data))


# =========================
# 🌐 VERCEL HANDLER
# =========================
async def handler(request):
    data = await request.json()
    update = Update(**data)
    await dp.feed_update(bot, update)
    return {"ok": True}
