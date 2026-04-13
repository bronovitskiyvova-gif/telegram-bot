import os
import re
import json
import requests
from urllib.parse import urlparse, urlunparse, unquote
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
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Accept-Language": "uk-UA,uk;q=0.9,en-US;q=0.8,en;q=0.7,ru;q=0.6",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
}


# =========================
# HELPERS
# =========================
def normalize_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def clean_url(url: str) -> str:
    """
    Прибирає utm та зайвий query-string.
    Це особливо корисно для rieltor/lun referral links.
    """
    try:
        p = urlparse(url)
        return urlunparse((p.scheme, p.netloc, p.path, "", "", ""))
    except Exception:
        return url


def safe_get(url: str):
    url = clean_url(url)
    return requests.get(url, headers=HEADERS, timeout=30, allow_redirects=True)


def safe_search(pattern, text, flags=re.IGNORECASE):
    return re.search(pattern, text or "", flags)


def looks_russian(text: str) -> bool:
    if not text:
        return False
    markers = [
        "продается", "улица", "этаж", "дом", "рядом", "ремонт",
        "отопление", "меблирована", "просмотр", "санузел", "площадь",
        "квартира", "жизни", "полностью", "идеальный"
    ]
    low = text.lower()
    return sum(1 for m in markers if m in low) >= 2


def ru_to_ua_text(text: str) -> str:
    if not text:
        return text

    replacements = {
        "Продается": "Продається",
        "продается": "продається",
        "улица": "вулиця",
        "Улица": "Вулиця",
        "этаж": "поверх",
        "Этаж": "Поверх",
        "этажа": "поверху",
        "дом": "будинок",
        "Дом": "Будинок",
        "дома": "будинку",
        "отопление": "опалення",
        "Отопление": "Опалення",
        "индивидуальное": "індивідуальне",
        "Индивидуальное": "Індивідуальне",
        "центральное": "централізоване",
        "Центральное": "Централізоване",
        "площадь": "площа",
        "Площадь": "Площа",
        "комната": "кімната",
        "комнаты": "кімнати",
        "рядом": "поруч",
        "без лифта": "без ліфта",
        "лифт": "ліфт",
        "лифта": "ліфта",
        "полностью": "повністю",
        "меблирована": "мебльована",
        "укомплектована": "укомплектована",
        "техника": "техніка",
        "санузел": "санвузол",
        "состояние": "стан",
        "качественный": "якісний",
        "дизайнерский": "дизайнерський",
        "метро": "метро",
        "удобный": "зручний",
        "просмотр": "перегляд",
        "звоните": "телефонуйте",
        "году": "році",
        "год": "рік",
        "в эксплуатации": "в експлуатації",
        "квартира-студия": "квартира-студія",
        "идеальный вариант": "ідеальний варіант",
        "для жизни": "для життя",
        "инвестиции": "інвестиції",
        "теплый пол": "тепла підлога",
        "двухконтурный котел": "двоконтурний котел",
        "шкаф": "шафа",
        "большой": "великий",
        "отдельная": "окрема",
        "территория": "територія",
        "охрана": "охорона",
        "видеонаблюдение": "відеоспостереження",
        "большие": "великі",
        "панорамные окна": "панорамні вікна",
        "вид во двор": "вид у двір",
        "местоположение": "розташування",
        "новая почта": "Нова пошта",
        "остановка транспорта": "зупинка транспорту",
        "удобный выезд": "зручний виїзд",
        "кольцевую дорогу": "Кільцеву дорогу",
        "идеально под аренду": "ідеально під оренду",
        "комфортное проживание": "комфортне проживання",
        "без дополнительных вложений": "без додаткових вкладень",
        "предоставлю дополнительные фото и видео": "надам додаткові фото та відео",
        "договоримся о просмотре": "домовимось про перегляд",
        "мебелью": "меблями",
        "техникой": "технікою",
        "с ремонтом": "з ремонтом",
        "в квартире": "у квартирі",
        "подходит": "підходить",
        "после покупки": "після купівлі",
        "жилья": "житла",
        "сразу": "одразу",
        "создана": "створена",
        "для комфортного": "для комфортного",
    }

    for ru, ua in replacements.items():
        text = text.replace(ru, ua)

    return text


def clean_description(text: str) -> str:
    if not text:
        return "Опис не знайдено"

    text = normalize_spaces(text)

    garbage = [
        "Продаж", "Оренда", "Мій ЛУН", "Інше", "Новобудови",
        "Показати менше", "Показати більше",
        "Схожі оголошення", "Інші пропозиції",
        "Зателефонувати", "Написати", "Поскаржитися",
        "Завантажуй застосунок", "фотографій", "Більше про новобудову"
    ]
    for g in garbage:
        text = text.replace(g, "")

    text = normalize_spaces(text)

    if looks_russian(text):
        text = ru_to_ua_text(text)
        text = normalize_spaces(text)

    return text[:2600] if text else "Опис не знайдено"


def is_image_url(url: str) -> bool:
    if not url:
        return False

    url = unquote(url)
    if url.startswith("//"):
        url = "https:" + url

    if not url.startswith("http"):
        return False

    low = url.lower()
    bad = ["logo", "icon", "avatar", "sprite", ".svg", "thumbnail", "thumb"]
    if any(x in low for x in bad):
        return False

    if any(ext in low for ext in [".jpg", ".jpeg", ".png", ".webp"]):
        return True

    image_markers = ["/image", "/images/", "/photos/", "/photo/", "cdn", "media"]
    return any(marker in low for marker in image_markers)


def normalize_image_url(url: str) -> str:
    if not url:
        return ""
    url = unquote(url)
    if url.startswith("//"):
        url = "https:" + url
    return url


def image_dedupe_key(url: str) -> str:
    """
    Прибирає query та типові розміри, щоб дублікати OLX/LUN не повторювались.
    """
    try:
        u = normalize_image_url(url)
        p = urlparse(u)
        path = p.path.lower()

        # прибираємо суфікси розмірів типу _640x480, -800x600
        path = re.sub(r'[_-]\d{2,4}x\d{2,4}(?=\.)', '', path)

        # тільки останні 2 сегменти шляху
        parts = [x for x in path.split("/") if x]
        short = "/".join(parts[-2:]) if len(parts) >= 2 else path
        return f"{p.netloc.lower()}::{short}"
    except Exception:
        return url.lower()


def dedupe_images(images):
    result = []
    seen = set()
    for img in images:
        if not is_image_url(img):
            continue
        key = image_dedupe_key(img)
        if key in seen:
            continue
        seen.add(key)
        result.append(img)
    return result


def extract_json_ld_objects(soup):
    objs = []
    for script in soup.find_all("script", {"type": "application/ld+json"}):
        raw = script.string or script.get_text()
        if not raw:
            continue
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                objs.extend(data)
            else:
                objs.append(data)
        except Exception:
            pass
    return objs


def extract_description_from_jsonld(soup):
    for obj in extract_json_ld_objects(soup):
        if isinstance(obj, dict):
            desc = obj.get("description")
            if isinstance(desc, str) and len(desc) > 60:
                return clean_description(desc)
    return ""


def extract_images_from_jsonld(soup):
    images = []
    for obj in extract_json_ld_objects(soup):
        if isinstance(obj, dict):
            img = obj.get("image")
            if isinstance(img, str) and is_image_url(img):
                images.append(normalize_image_url(img))
            elif isinstance(img, list):
                for x in img:
                    if isinstance(x, str) and is_image_url(x):
                        images.append(normalize_image_url(x))
    return images


def extract_meta_description(soup):
    for key in ["description", "og:description", "twitter:description"]:
        tag = soup.find("meta", attrs={"name": key}) or soup.find("meta", attrs={"property": key})
        if tag:
            content = tag.get("content")
            if content and len(content) > 60:
                return clean_description(content)
    return ""


def extract_meta_images(soup):
    images = []
    for key in ["og:image", "twitter:image"]:
        tag = soup.find("meta", attrs={"property": key}) or soup.find("meta", attrs={"name": key})
        if tag:
            content = tag.get("content")
            if is_image_url(content):
                images.append(normalize_image_url(content))
    return images


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
                if len(block_text) > 180:
                    block_text = block_text.replace(heading_text, "", 1).strip()
                    return clean_description(block_text)
    return ""


def extract_price(text):
    patterns = [
        r"(\d[\d\s]{2,})\s?\$",
        r"USD\s?(\d[\d\s]{2,})",
    ]
    for p in patterns:
        m = safe_search(p, text)
        if m:
            return normalize_spaces(m.group(1)) + " $"
    return None


def extract_rooms(text):
    patterns = [
        r"(\d+)\s*кім",
        r"(\d+)[-\s]?кімнат",
        r"кімнат[^\d]{0,10}(\d+)",
        r"(\d+)[-\s]?к\b",
        r"(\d+)\s*комн",
        r"(\d+)\s*rooms?",
    ]
    for p in patterns:
        m = safe_search(p, text)
        if m:
            return m.group(1)
    return None


def extract_area_general(text):
    patterns = [
        r"Загальна площа[^0-9]{0,20}(\d+(?:[.,]\d+)?)\s*м²",
        r"Площа[^0-9]{0,20}(\d+(?:[.,]\d+)?)\s*м²",
        r"Общая площадь[^0-9]{0,20}(\d+(?:[.,]\d+)?)\s*м²",
        r"(\d+(?:[.,]\d+)?)\s*м²",
    ]
    for p in patterns:
        m = safe_search(p, text)
        if m:
            return m.group(1).replace(",", ".") + " м²"
    return None


def extract_area_lun(text):
    m = safe_search(r"(\d+(?:[.,]\d+)?)\s*/\s*(\d+(?:[.,]\d+)?)\s*/\s*(\d+(?:[.,]\d+)?)\s*м²", text)
    if m:
        return m.group(1).replace(",", ".") + " м²"
    return extract_area_general(text)


def extract_floor_olx(text):
    patterns = [
        r"Поверх:\s*(\d+)\s*/\s*(\d+)",
        r"Поверх:\s*(\d+)\s*з\s*(\d+)",
        r"(\d+)\s*поверх[^0-9]{0,10}з\s*(\d+)",
        r"(\d+)\s*/\s*(\d+)\s*поверх",
        r"поверх[^0-9]{0,10}(\d+)\s*/\s*(\d+)",
        r"поверх[^0-9]{0,10}(\d+)\s*з\s*(\d+)",
        r"этаж[^0-9]{0,10}(\d+)\s*(?:из|/)\s*(\d+)",
        r"(\d+)\s*этаж[^0-9]{0,10}из\s*(\d+)",
    ]
    for p in patterns:
        m = safe_search(p, text)
        if m:
            return f"{m.group(1)}/{m.group(2)}"
    return None


def extract_floor_general(text):
    patterns = [
        r"Поверх[^0-9]{0,15}(\d+)\s*(?:з|/)\s*(\d+)",
        r"(\d+)\s*(?:з|/)\s*(\d+)\s*поверх",
        r"поверх[^0-9]{0,10}(\d+)\s*(?:з|/)\s*(\d+)",
        r"Этаж[^0-9]{0,15}(\d+)\s*(?:из|/)\s*(\d+)",
        r"(\d+)\s*этаж[^0-9]{0,10}из\s*(\d+)",
    ]
    for p in patterns:
        m = safe_search(p, text)
        if m:
            return f"{m.group(1)}/{m.group(2)}"
    return None


def extract_floor_lun(text):
    m = safe_search(r"поверх\s*(\d+)\s*з\s*(\d+)", text)
    if m:
        return f"{m.group(1)}/{m.group(2)}"

    m = safe_search(r"(\d+)\s*/\s*(\d+)\s*поверх", text)
    if m:
        return f"{m.group(1)}/{m.group(2)}"

    return extract_floor_general(text)


def extract_floor_domria(text):
    patterns = [
        r"Поверх[^0-9]{0,20}(\d+)\s*(?:з|/)\s*(\d+)",
        r"поверх[^0-9]{0,20}(\d+)\s*(?:з|/)\s*(\d+)",
        r"(\d+)\s*(?:з|/)\s*(\d+)\s*поверх",
        r"Этаж[^0-9]{0,20}(\d+)\s*(?:из|/)\s*(\d+)",
        r"(\d+)\s*этаж[^0-9]{0,10}из\s*(\d+)",
    ]
    for p in patterns:
        m = safe_search(p, text)
        if m:
            return f"{m.group(1)}/{m.group(2)}"
    return extract_floor_general(text)


def extract_year(text):
    m = safe_search(r"\b(20\d{2}|19\d{2})\b", text)
    return m.group(1) if m else None


def extract_building(text):
    low = text.lower()
    if "цегл" in low or "кирп" in low:
        return "цегляний"
    if "панел" in low:
        return "панельний"
    if "монол" in low:
        return "моноліт"
    return None


def extract_heating(text):
    low = text.lower()
    if "централіз" in low:
        return "централізоване"
    if "автоном" in low:
        return "автономне"
    if "індивідуаль" in low or "индивидуаль" in low:
        return "індивідуальне"
    return None


def normalize_address(addr: str) -> str:
    if not addr:
        return addr

    addr = normalize_spaces(addr)
    addr = re.sub(r"\bЖК\b", "ЖК", addr, flags=re.IGNORECASE)
    addr = re.sub(r"\bулица\b", "вулиця", addr, flags=re.IGNORECASE)
    addr = re.sub(r"\bвул\b\.?", "вулиця", addr, flags=re.IGNORECASE)
    addr = re.sub(r"\bпросп\b\.?", "проспект", addr, flags=re.IGNORECASE)
    addr = re.sub(r"\bпров\b\.?", "провулок", addr, flags=re.IGNORECASE)
    addr = re.sub(r"\bбул\b\.?", "бульвар", addr, flags=re.IGNORECASE)
    addr = re.sub(r"\s+,", ",", addr)

    stop_words = [
        "Більше про новобудову",
        "Ціна", "Площа", "Поверх", "Кімнат",
        "Этаж", "Площадь", "Цена", "Комнат"
    ]
    for stop in stop_words:
        pos = addr.find(stop)
        if pos > 0:
            addr = addr[:pos].strip()

    return normalize_spaces(addr)


def extract_address(text):
    patterns = [
        r"(ЖК\s+[A-ЯІЇЄA-Za-zА-Яа-яіїє0-9«»\"'`\- ]+(?:,\s*\d+[A-Za-zА-Яа-я]?)?)",
        r"(вул\.?\s*[A-ЯІЇЄA-Za-zА-Яа-яіїє0-9\- ]+(?:,\s*\d+[A-Za-zА-Яа-я]?)?)",
        r"(улица\s*[A-ЯІЇЄA-Za-zА-Яа-яіїє0-9\- ]+(?:,\s*\d+[A-Za-zА-Яа-я]?)?)",
        r"(просп\.?\s*[A-ЯІЇЄA-Za-zА-Яа-яіїє0-9\- ]+(?:,\s*\d+[A-Za-zА-Яа-я]?)?)",
        r"(пров\.?\s*[A-ЯІЇЄA-Za-zА-Яа-яіїє0-9\- ]+(?:,\s*\d+[A-Za-zА-Яа-я]?)?)",
        r"(бул\.?\s*[A-ЯІЇЄA-Za-zА-Яа-яіїє0-9\- ]+(?:,\s*\d+[A-Za-zА-Яа-я]?)?)",
    ]
    for p in patterns:
        m = safe_search(p, text)
        if m:
            return normalize_address(m.group(1))
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
    p = parse_price_to_number(price_value)
    a = parse_area_to_number(area_value)
    if not p or not a or a <= 0:
        return None
    return f"{round(p / a)} $/м²"


def collect_images_basic(soup):
    images = []

    for img in soup.find_all("img"):
        for attr in ["src", "data-src", "data-lazy", "srcset"]:
            val = img.get(attr)
            if not val:
                continue

            if attr == "srcset":
                for part in val.split(","):
                    u = normalize_image_url(part.strip().split(" ")[0])
                    if is_image_url(u):
                        images.append(u)
            else:
                u = normalize_image_url(val)
                if is_image_url(u):
                    images.append(u)

    images.extend(extract_meta_images(soup))
    images.extend(extract_images_from_jsonld(soup))

    for script in soup.find_all("script"):
        content = script.string or script.get_text()
        if not content:
            continue

        urls = re.findall(r'https?://[^"\']+', content)
        for u in urls:
            u = normalize_image_url(re.split(r'["\'\s,)]', u)[0])
            if is_image_url(u):
                images.append(u)

        esc_urls = re.findall(r'https:\\/\\/[^"\']+', content)
        for u in esc_urls:
            u = normalize_image_url(u.replace("\\/", "/"))
            u = re.split(r'["\'\s,)]', u)[0]
            if is_image_url(u):
                images.append(u)

        more = re.findall(r'"(?:src|url|image|photo|mainImage|large|medium|small)"\s*:\s*"([^"]+)"', content)
        for u in more:
            u = normalize_image_url(u.replace("\\/", "/"))
            if is_image_url(u):
                images.append(u)

    return dedupe_images(images)[:20]


def build_base_data(text):
    data = {}
    data["rooms"] = extract_rooms(text)
    data["area"] = extract_area_general(text)
    data["price"] = extract_price(text)
    data["year"] = extract_year(text)
    data["building"] = extract_building(text)
    data["heating"] = extract_heating(text)
    data["address"] = extract_address(text)
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
# ПАРСЕРИ
# =========================
def parse_olx(url):
    r = safe_get(url)
    soup = BeautifulSoup(r.text, "html.parser")
    text = soup.get_text(" ", strip=True)

    data = build_base_data(text)
    data["floor"] = extract_floor_olx(text) or extract_floor_general(text)

    description = ""
    desc_block = soup.find("div", {"data-cy": "ad_description"})
    if desc_block:
        description = desc_block.get_text(" ", strip=True)

    if not description:
        description = extract_description_from_jsonld(soup)
    if not description:
        description = extract_meta_description(soup)
    if not description:
        description = extract_section_by_heading(soup, "Опис")

    if not description:
        for div in soup.find_all(["div", "section", "article", "p"]):
            t = normalize_spaces(div.get_text(" ", strip=True))
            if len(t) > 250 and any(w in t.lower() for w in ["квартира", "будинок", "ремонт", "поверх"]):
                description = clean_description(t)
                break

    images = collect_images_basic(soup)

    data["description"] = clean_description(description)
    data["images"] = images
    data["price_per_m2"] = calc_price_per_m2(data.get("price"), data.get("area"))
    return data


def parse_lun(url):
    r = safe_get(url)
    soup = BeautifulSoup(r.text, "html.parser")
    text = soup.get_text(" ", strip=True)

    data = build_base_data(text)
    data["area"] = extract_area_lun(text)
    data["floor"] = extract_floor_lun(text)

    if not data.get("address"):
        m = safe_search(r"(ЖК\s+[^\n]+?(?:вулиця|вул\.?|проспект|просп\.?)\s+[^\n,]+,\s*\d+[A-Za-zА-Яа-я]?)", text)
        if m:
            data["address"] = normalize_address(m.group(1))

    description = extract_section_by_heading(soup, "Опис")
    if not description:
        description = extract_description_from_jsonld(soup)
    if not description:
        description = extract_meta_description(soup)
    if not description:
        for div in soup.find_all(["div", "section", "article", "p"]):
            t = normalize_spaces(div.get_text(" ", strip=True))
            if len(t) > 250 and any(w in t.lower() for w in ["квартира", "будинок", "ремонт", "поверх"]):
                description = clean_description(t)
                break

    images = collect_images_basic(soup)

    data["description"] = clean_description(description)
    data["images"] = images
    data["price_per_m2"] = calc_price_per_m2(data.get("price"), data.get("area"))
    return data


def parse_domria(url):
    r = safe_get(url)
    soup = BeautifulSoup(r.text, "html.parser")
    text = soup.get_text(" ", strip=True)

    data = build_base_data(text)
    data["floor"] = extract_floor_domria(text)

    description = extract_section_by_heading(soup, "Опис")
    if not description:
        description = extract_description_from_jsonld(soup)
    if not description:
        description = extract_meta_description(soup)

    if not description:
        selectors = [
            ("div", {"class": re.compile(r".*description.*", re.I)}),
            ("div", {"data-testid": re.compile(r".*description.*", re.I)}),
            ("section", {"class": re.compile(r".*description.*", re.I)}),
            ("article", {}),
        ]
        for name, attrs in selectors:
            block = soup.find(name, attrs)
            if block:
                t = normalize_spaces(block.get_text(" ", strip=True))
                if len(t) > 120:
                    description = clean_description(t)
                    break

    if not description:
        for div in soup.find_all(["div", "section", "article", "p"]):
            t = normalize_spaces(div.get_text(" ", strip=True))
            if len(t) > 220 and any(w in t.lower() for w in ["квартира", "будинок", "ремонт", "поверх"]):
                description = clean_description(t)
                break

    description = clean_description(description)
    if looks_russian(description):
        description = clean_description(ru_to_ua_text(description))

    images = collect_images_basic(soup)

    data["description"] = description
    data["images"] = images
    data["price_per_m2"] = calc_price_per_m2(data.get("price"), data.get("area"))
    return data


def parse_rieltor(url):
    r = safe_get(url)
    soup = BeautifulSoup(r.text, "html.parser")
    text = soup.get_text(" ", strip=True)

    title_text = ""
    if soup.title and soup.title.string:
        title_text = soup.title.string

    meta_desc = extract_meta_description(soup)
    merged_text = " ".join([text, title_text, meta_desc])

    data = build_base_data(merged_text)
    data["floor"] = extract_floor_general(merged_text)

    if not data.get("price"):
        m = safe_search(r"(\d[\d\s]{2,})\s?\$", title_text)
        if m:
            data["price"] = normalize_spaces(m.group(1)) + " $"

    if not data.get("rooms"):
        for source in [title_text, meta_desc, merged_text]:
            m = safe_search(r"(\d+)\s*кімнат", source)
            if m:
                data["rooms"] = m.group(1)
                break

    if not data.get("floor"):
        m = safe_search(r"(\d+)\s*поверх\s*(\d+)[-\s]?пов", title_text)
        if m:
            data["floor"] = f"{m.group(1)}/{m.group(2)}"

    if not data.get("area"):
        m = safe_search(r"(\d+(?:[.,]\d+)?)\s*/\s*(\d+(?:[.,]\d+)?)\s*/\s*(\d+(?:[.,]\d+)?)\s*м²", title_text)
        if m:
            data["area"] = m.group(1).replace(",", ".") + " м²"

    if not data.get("address"):
        data["address"] = extract_address(title_text)

    description = extract_section_by_heading(soup, "Опис")
    if not description:
        description = extract_description_from_jsonld(soup)
    if not description:
        description = meta_desc

    if not description:
        selectors = [
            ("div", {"class": re.compile(r".*description.*", re.I)}),
            ("section", {"class": re.compile(r".*description.*", re.I)}),
            ("div", {"id": re.compile(r".*description.*", re.I)}),
            ("article", {}),
            ("main", {}),
            ("body", {}),
        ]
        for name, attrs in selectors:
            block = soup.find(name, attrs)
            if block:
                t = normalize_spaces(block.get_text(" ", strip=True))
                if len(t) > 120 and any(w in t.lower() for w in ["квартира", "будинок", "ремонт", "поверх", "кімнат"]):
                    description = clean_description(t)
                    break

    images = collect_images_basic(soup)

    data["description"] = clean_description(description)
    data["images"] = images
    data["price_per_m2"] = calc_price_per_m2(data.get("price"), data.get("area"))
    return data


def parse_fallback(url):
    r = safe_get(url)
    soup = BeautifulSoup(r.text, "html.parser")
    text = soup.get_text(" ", strip=True)

    data = build_base_data(text)
    data["floor"] = extract_floor_general(text)

    description = extract_section_by_heading(soup, "Опис")
    if not description:
        description = extract_description_from_jsonld(soup)
    if not description:
        description = extract_meta_description(soup)

    if not description:
        for div in soup.find_all(["div", "section", "article", "p"]):
            t = normalize_spaces(div.get_text(" ", strip=True))
            if len(t) > 220 and any(w in t.lower() for w in ["квартира", "будинок", "ремонт", "поверх"]):
                description = clean_description(t)
                break

    images = collect_images_basic(soup)

    data["description"] = clean_description(description)
    data["images"] = images
    data["price_per_m2"] = calc_price_per_m2(data.get("price"), data.get("area"))
    return data


def parse_url(url):
    low = url.lower()

    if "olx." in low:
        return parse_olx(url)

    if "rieltor.ua" in low or "realtor.ua" in low:
        return parse_rieltor(url)

    if "dom.ria" in low or "domria" in low:
        return parse_domria(url)

    if "lun.ua" in low:
        return parse_lun(url)

    return parse_fallback(url)


# =========================
# TELEGRAM
# =========================
async def send_images_safely(message: types.Message, images):
    if not images:
        return

    images = dedupe_images(images)[:10]

    try:
        media = [InputMediaPhoto(media=img) for img in images]
        await message.answer_media_group(media)
        return
    except Exception:
        pass

    sent = 0
    for img in images:
        try:
            await message.answer_photo(img)
            sent += 1
            if sent >= 5:
                break
        except Exception:
            continue

    if sent == 0:
        await message.answer("⚠️ Фото не відправились")


@dp.message()
async def handle_message(message: types.Message):
    url = (message.text or "").strip()

    if not url.startswith("http"):
        await message.answer("❌ Відправ посилання")
        return

    try:
        data = parse_url(url)

        if data.get("images"):
            await send_images_safely(message, data["images"])

        await message.answer(format_text(data))

    except Exception as e:
        await message.answer(f"❌ Помилка обробки: {e}")


# =========================
# FASTAPI / VERCEL
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
