import os
import re
import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types
from aiogram.types import Update, InputMediaPhoto
from aiogram.fsm.storage.memory import MemoryStorage

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

app = FastAPI()
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

headers = {
    "User-Agent": "Mozilla/5.0"
}


def clean(text: str) -> str:
    if not text:
        return "Опис не знайдено"
    return re.sub(r"\s+", " ", text).strip()[:1200]


def extract_images(soup):
    images = set()

    for img in soup.find_all("img"):
        for attr in ["src", "data-src", "data-lazy"]:
            src = img.get(attr)
            if src and src.startswith("http") and not any(x in src.lower() for x in ["logo", "icon", "avatar"]):
                images.add(src)

    for script in soup.find_all("script"):
        content = script.string or script.get_text()
        if content:
            urls = re.findall(r'https://[^"\']+\.(?:jpg|jpeg|png|webp)', content)
            images.update(urls)

    return list(images)[:10]


def extract_data(text):
    def find(pattern):
        m = re.search(pattern, text, re.IGNORECASE)
        return m.group(1).strip() if m else None

    data = {}
    data["rooms"] = find(r"(\d+)\s*кім")
    data["area"] = find(r"(\d+(?:[\.,]\d+)?)\s*м²")
    data["price"] = find(r"(\d[\d\s]*)\s?\$")
    data["year"] = find(r"\b(20\d{2})\b")

    floor = re.search(r"(\d+)\s*/\s*(\d+)", text)
    if floor:
        data["floor"] = f"{floor.group(1)}/{floor.group(2)}"

    low = text.lower()

    if "цегл" in low:
        data["building"] = "цегляний"
    elif "панел" in low:
        data["building"] = "панельний"
    elif "монол" in low:
        data["building"] = "моноліт"

    if "централіз" in low:
        data["heating"] = "централізоване"
    elif "автоном" in low:
        data["heating"] = "автономне"

    addr = re.search(r"(вул\.|просп\.|жк)\s*[^,\n]+", text, re.IGNORECASE)
    if addr:
        data["address"] = addr.group(0).strip()

    return data


def parse(url):
    r = requests.get(url, headers=headers, timeout=15)
    soup = BeautifulSoup(r.text, "html.parser")
    text = soup.get_text(" ", strip=True)

    data = extract_data(text)

    description = ""
    for div in soup.find_all("div"):
        t = div.get_text(" ", strip=True)
        if len(t) > 300:
            description = t
            break

    data["description"] = clean(description)
    data["images"] = extract_images(soup)
    return data


def format_text(d):
    return f"""
🏠 Кількість кімнат: {d.get('rooms') or '---'}
📍 Адреса: {d.get('address') or '---'}

💰 Ціна: {d.get('price') or '---'}
📐 Площа: {d.get('area') or '---'}
🏢 Поверх: {d.get('floor') or '---'}

🧱 Тип будинку: {d.get('building') or '---'}
📅 Рік введення в експлуатацію: {d.get('year') or '---'}
🔥 Тип опалення: {d.get('heating') or '---'}

📝 Опис:
{d.get('description') or 'Опис не знайдено'}
""".strip()


@dp.message()
async def handle_message(message: types.Message):
    url = (message.text or "").strip()

    if not url.startswith("http"):
        await message.answer("❌ Відправ посилання")
        return

    try:
        data = parse(url)

        if data.get("images"):
            media = [InputMediaPhoto(media=img) for img in data["images"][:10]]
            try:
                await message.answer_media_group(media)
            except Exception:
                await message.answer("⚠️ Фото не відправились")

        await message.answer(format_text(data))

    except Exception as e:
        await message.answer(f"❌ Помилка обробки: {e}")


@app.get("/")
@app.get("/api")
async def root():
    return {"ok": True, "message": "Telegram bot webhook is running"}


@app.post("/")
@app.post("/api")
async def telegram_webhook(request: Request):
    data = await request.json()
    update = Update(**data)
    await dp.feed_update(bot, update)
    return {"ok": True}
