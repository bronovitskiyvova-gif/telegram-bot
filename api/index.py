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

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "uk-UA,uk;q=0.9,en-US;q=0.8,en;q=0.7",
}


# =========================
# 🧠 ДОПОМІЖНІ ФУНКЦІЇ
# =========================
def normalize_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def clean_description(text: str) -> str:
    if not text:
        return "Опис не знайдено"

    text = normalize_spaces(text)

    bad_phrases = [
        "Продаж",
        "Оренда",
        "Мій ЛУН",
        "Інше",
        "Новобудови",
        "показати менше",
        "показати більше",
        "завантажуй застосунок",
        "25 фотографій",
        "фотографій",
    ]

    for phrase in bad_phrases:
        text = text.replace(phrase, "")

    stop_words = [
        "Показати менше",
        "Показати більше",
        "Схожі оголошення",
        "Інші пропозиції",
        "Зателефонувати",
        "Написати",
        "Поскаржитися",
        "Новобудови",
        "Продаж",
        "Оренда",
        "Мій ЛУН",
        "Завантажуй застосунок",
    ]

    lower_text = text.lower()
    for stop in stop_words:
        idx = lower_text.find(stop.lower())
        if idx > 200:
            text = text[:idx].strip()
            lower_text = text.lower()

    return text[:1800] if text else "Опис не знайдено"


def extract_section_by_heading(soup, heading_text="Опис"):
    tags = soup.find_all(["h1", "h2", "h3", "h4", "div", "span", "p", "section"])
    for tag in tags:
        txt = normalize_spaces(tag.get_text(" ", strip=True))
        if txt.lower() == heading_text.lower():
            nxt = tag.find_next(["div", "section", "article", "p"])
            if nxt:
                block_text = normalize_spaces(nxt.get_text(" ", strip=True))
                if len(block_text) > 120:
                    return clean_description(block_text)

            parent = tag.parent
            if parent:
                block_text = normalize_spaces(parent.get_text(" ", strip=True))
                if len(block_text) > 200:
                    block_text = block_text.replace(heading_text, "", 1).strip()
                    return clean_description(block_text)
    return ""


def extract_images_from_scripts(soup, preferred_domains=None):
    images = set()
    preferred_domains = preferred_domains or []

    for script in soup.find_all("script"):
        content = script.string or script.get_text()
        if not content:
            continue

        urls = re.findall(r'https://[^"\']+\.(?:jpg|jpeg|png|webp)', content)
        for url in urls:
            low = url.lower()
            if any(x in low for x in ["logo", "icon", "avatar", "svg"]):
                continue

            if preferred_domains:
                if any(domain in low for domain in preferred_domains):
                    images.add(url)
            else:
                images.add(url)

    return images


def collect_images(soup, preferred_domains=None):
    images = set()
    preferred_domains = preferred_domains or []

    for img in soup.find_all("img"):
        for attr in ["src", "data-src", "data-lazy", "srcset"]:
            value = img.get(attr)
            if not value:
                continue

            if attr == "srcset":
                for part in value.split(","):
                    u = part.strip().split(" ")[0]
                    low = u.lower()
                    if u.startswith("http") and not any(x in low for x in ["logo", "icon", "avatar", "svg"]):
                        if preferred_domains:
                            if any(domain in low for domain in preferred_domains):
                                images.add(u)
                            else:
                                images.add(u)
                        else:
                            images.add(u)
            else:
                low = value.lower()
                if value.startswith("http") and not any(x in low for x in ["logo", "icon", "avatar", "svg"]):
                    if preferred_domains:
                        if any(domain in low for domain in preferred_domains):
                            images.add(value)
                        else:
                            images.add(value)
                    else:
                        images.add(value)

    script_images = extract_images_from_scripts(soup, preferred_domains=preferred_domains)
    images |= script_images

    cleaned = []
    for u in images:
        low = u.lower()
        if any(x in low for x in ["thumb", "thumbnail", "small", "logo", "icon", "avatar"]):
            continue
        cleaned.append(u)

    return cleaned[:10]


def extract_address(text):
    patterns = [
        r"(ЖК\s+[A-ЯІЇЄA-Za-zА-Яа-яіїє0-9«»\"'`\-\s]+)",
        r"(вул\.?\s*[A-ЯІЇЄA-Za-zА-Яа-яіїє0-9\-\s]+(?:,\s*\d+[A-Za-zА-Яа-я]?)?)",
        r"(просп\.?\s*[A-ЯІЇЄA-Za-zА-Яа-яіїє0-9\-\s]+(?:,\s*\d+[A-Za-zА-Яа-я]?)?)",
        r"(пров\.?\s*[A-ЯІЇЄA-Za-zА-Яа-яіїє0-9\-\s]+(?:,\s*\d+[A-Za-zА-Яа-я]?)?)",
        r"(бул\.?\s*[A-ЯІЇЄA-Za-zА-Яа-яіїє0-9\-\s]+(?:,\s*\d+[A-Za-zА-Яа-я]?)?)",
    ]

    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            return normalize_spaces(m.group(1))

    return None


def parse_price_to_number(price_value):
    if not price_value:
        return None
    cleaned = price_value.replace("$", "").replace(" ", "").replace(",", ".")
    try:
        return float(cleaned)
    except Exception:
        return None


def parse_area_to_number(area_value):
    if not area_value:
        return None
    cleaned = area_value.replace("м²", "").replace(" ", "").replace(",", ".")
    try:
        return float(cleaned)
    except Exception:
        return None


def calc_price_per_m2(price_value, area_value):
    price_num = parse_price_to_number(price_value)
    area_num = parse_area_to_number(area_value)

    if not price_num or not area_num or area_num <= 0:
        return None

    return f"{round(price_num / area_num)} $/м²"


def extract_common_data(text):
    def find(pattern):
        m = re.search(pattern, text, re.IGNORECASE)
        return m.group(1).strip() if m else None

    data = {}

    data["rooms"] = find(r"(\d+)\s*кім")
    data["area"] = find(r"(\d+(?:[\.,]\d+)?)\s*м²")
    if data["area"]:
        data["area"] = data["area"].replace(",", ".") + " м²"

    data["price"] = find(r"(\d[\d\s]*)\s?\$")
    if data["price"]:
        data["price"] = normalize_spaces(data["price"]) + " $"

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

    data["address"] = extract_address(text)
    data["price_per_m2"] = calc_price_per_m2(data.get("price"), data.get("area"))

    return data


def format_text(d):
    return f"""
🏠 Кількість кімнат: {d.get('rooms') or '---'}
📍 Адреса: {d.get('address') or '---'}

💰 Ціна: {d.get('price') or '---'}
📏 Ціна за м²: {d.get('price_per_m2') or '---'}
📐 Площа: {d.get('area') or '---'}
🏢 Поверх: {d.get('floor') or '---'}

🧱 Тип будинку: {d.get('building') or '---'}
📅 Рік введення в експлуатацію: {d.get('year') or '---'}
🔥 Тип опалення: {d.get('heating') or '---'}

📝 Опис:
{d.get('description') or 'Опис не знайдено'}
""".strip()


# =========================
# 🟠 OLX
# =========================
def parse_olx(url):
    r = requests.get(url, headers=HEADERS, timeout=20)
    soup = BeautifulSoup(r.text, "html.parser")
    text = soup.get_text(" ", strip=True)

    data = extract_common_data(text)

    description = ""
    desc_block = soup.find("div", {"data-cy": "ad_description"})
    if desc_block:
        description = desc_block.get_text(" ", strip=True)

    if not description:
        description = extract_section_by_heading(soup, "Опис")

    if not description:
        for div in soup.find_all(["div", "section", "article", "p"]):
            t = normalize_spaces(div.get_text(" ", strip=True))
            if len(t) > 300 and any(word in t.lower() for word in ["квартира", "кімнат", "поверх", "будинок"]):
                description = clean_description(t)
                break

    images = collect_images(soup)

    data["description"] = clean_description(description)
    data["images"] = images
    return data


# =========================
# 🔵 REALTOR.UA
# =========================
def parse_realtor(url):
    r = requests.get(url, headers=HEADERS, timeout=20)
    soup = BeautifulSoup(r.text, "html.parser")
    text = soup.get_text(" ", strip=True)

    data = extract_common_data(text)

    description = extract_section_by_heading(soup, "Опис")

    if not description:
        selectors = [
            ("div", {"class": re.compile(r".*description.*", re.I)}),
            ("section", {"class": re.compile(r".*description.*", re.I)}),
            ("div", {"id": re.compile(r".*description.*", re.I)}),
            ("article", {}),
        ]

        for name, attrs in selectors:
            block = soup.find(name, attrs)
            if block:
                t = normalize_spaces(block.get_text(" ", strip=True))
                if len(t) > 150:
                    description = clean_description(t)
                    break

    if not description:
        for block in soup.find_all(["div", "section", "article", "p"]):
            t = normalize_spaces(block.get_text(" ", strip=True))
            if len(t) > 250 and any(word in t.lower() for word in ["квартира", "кімнат", "будинок", "поверх", "ремонт"]):
                description = clean_description(t)
                break

    images = collect_images(soup, preferred_domains=["realtor", "cdn", "img"])

    data["description"] = description or "Опис не знайдено"
    data["images"] = images
    return data


# =========================
# 🟢 DOM.RIA
# =========================
def parse_domria(url):
    r = requests.get(url, headers=HEADERS, timeout=20)
    soup = BeautifulSoup(r.text, "html.parser")
    text = soup.get_text(" ", strip=True)

    data = extract_common_data(text)

    description = extract_section_by_heading(soup, "Опис")

    if not description:
        selectors = [
            ("div", {"class": re.compile(r".*description.*", re.I)}),
            ("div", {"data-testid": re.compile(r".*description.*", re.I)}),
            ("section", {"class": re.compile(r".*description.*", re.I)}),
        ]

        for name, attrs in selectors:
            block = soup.find(name, attrs)
            if block:
                t = normalize_spaces(block.get_text(" ", strip=True))
                if len(t) > 150:
                    description = clean_description(t)
                    break

    if not description:
        for div in soup.find_all(["div", "section", "article"]):
            t = normalize_spaces(div.get_text(" ", strip=True))
            if len(t) > 250 and any(word in t.lower() for word in ["квартира", "ремонт", "будинок", "поверх"]):
                description = clean_description(t)
                break

    images = collect_images(soup, preferred_domains=["ria", "dom.ria", "cdn"])

    data["description"] = description or "Опис не знайдено"
    data["images"] = images
    return data


# =========================
# 🟡 LUN / ІНШІ
# =========================
def parse_fallback(url):
    r = requests.get(url, headers=HEADERS, timeout=20)
    soup = BeautifulSoup(r.text, "html.parser")
    text = soup.get_text(" ", strip=True)

    data = extract_common_data(text)

    description = extract_section_by_heading(soup, "Опис")

    if not description:
        for div in soup.find_all(["div", "section", "article"]):
            t = normalize_spaces(div.get_text(" ", strip=True))
            if len(t) > 350 and any(word in t.lower() for word in ["квартира", "будинок", "кімнат", "поверх"]):
                description = clean_description(t)
                break

    images = collect_images(soup)

    data["description"] = description or "Опис не знайдено"
    data["images"] = images
    return data


def parse_url(url):
    low = url.lower()

    if "olx." in low:
        return parse_olx(url)

    if "realtor.ua" in low:
        return parse_realtor(url)

    if "dom.ria" in low or "domria" in low:
        return parse_domria(url)

    return parse_fallback(url)


# =========================
# 🤖 TELEGRAM
# =========================
@dp.message()
async def handle_message(message: types.Message):
    url = (message.text or "").strip()

    if not url.startswith("http"):
        await message.answer("❌ Відправ посилання")
        return

    try:
        data = parse_url(url)

        if data.get("images"):
            media = [InputMediaPhoto(media=img) for img in data["images"][:10]]
            try:
                await message.answer_media_group(media)
            except Exception:
                await message.answer("⚠️ Фото не відправились")

        await message.answer(format_text(data))

    except Exception as e:
        await message.answer(f"❌ Помилка обробки: {e}")


# =========================
# 🌐 FASTAPI / VERCEL
# =========================
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
