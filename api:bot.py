import asyncio
import re
from bs4 import BeautifulSoup

from aiogram import Bot, Dispatcher, types
from aiogram.types import InputMediaPhoto

from playwright.async_api import async_playwright

TOKEN = "7577433217:AAHD2hdqRGwvtddu0Z1V0t3h1yls1QYFL5M"

bot = Bot(token=TOKEN)
dp = Dispatcher()


# =========================
# 🧠 ОЧИСТКА ОПИСУ
# =========================
def clean(text):
    if not text:
        return "Опис не знайдено"

    text = re.sub(r"\s+", " ", text)
    text = text.replace("Меню", "")
    return text[:1200]


# =========================
# 🌍 ПАРСИНГ ЧЕРЕЗ БРАУЗЕР
# =========================
async def parse(url):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        await page.goto(url, timeout=60000)
        await page.wait_for_timeout(3000)

        html = await page.content()
        await browser.close()

    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)

    # 📊 дані
    rooms = re.search(r"(\d+)\s*кім", text)
    area = re.search(r"(\d+\.?\d*)\s*м²", text)
    floor = re.search(r"(\d+)\s*/\s*(\d+)", text)
    price = re.search(r"(\d[\d\s]+)\s?\$", text)
    year = re.search(r"(20\d{2})", text)

    # 🔥 опалення
    if "централіз" in text.lower():
        heating = "централізоване"
    elif "автоном" in text.lower():
        heating = "автономне"
    else:
        heating = None

    # 🧱 будинок
    if "цегл" in text.lower():
        building = "цегляний"
    elif "панел" in text.lower():
        building = "панельний"
    else:
        building = None

    # 📍 адреса
    address = None
    addr = re.search(r"(вул\.|просп\.|ЖК)[^,.]+", text)
    if addr:
        address = addr.group(0)

    # 📝 опис
    description = ""
    for div in soup.find_all("div"):
        t = div.get_text(" ", strip=True)
        if len(t) > 300:
            description = t
            break

    description = clean(description)

    # 📸 фото (тепер 100%)
    images = []
    for img in soup.find_all("img"):
        src = img.get("src")
        if src and "http" in src:
            if not any(x in src for x in ["logo", "icon"]):
                images.append(src)

    images = list(set(images))[:10]

    return {
        "rooms": rooms.group(1) if rooms else "---",
        "area": f"{area.group(1)} м²" if area else "---",
        "floor": f"{floor.group(1)}/{floor.group(2)}" if floor else "---",
        "price": f"{price.group(1)}$" if price else "---",
        "year": year.group(1) if year else "---",
        "building": building or "---",
        "heating": heating or "---",
        "address": address or "---",
        "description": description,
        "images": images
    }


# =========================
# 📝 ФОРМАТ
# =========================
def format_text(d):
    return f"""
🏠 Кількість кімнат: {d['rooms']}
📍 Адреса: {d['address']}

💰 Ціна: {d['price']}
📐 Площа: {d['area']}
🏢 Поверх: {d['floor']}

🧱 Тип будинку: {d['building']}
📅 Рік: {d['year']}
🔥 Опалення: {d['heating']}

📝 Опис:
{d['description']}
"""


# =========================
# 🤖 БОТ
# =========================
@dp.message()
async def handle(message: types.Message):
    url = message.text.strip()

    if not url.startswith("http"):
        await message.answer("❌ Відправ посилання")
        return

    data = await parse(url)

    # фото
    if data["images"]:
        media = [InputMediaPhoto(media=img) for img in data["images"]]
        try:
            await message.answer_media_group(media)
        except:
            await message.answer("⚠️ Фото не відправились")

    await message.answer(format_text(data))


# =========================
# 🚀 ЗАПУСК
# =========================
async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())