"""
scraper.py — парсер оголошень з OLX.ua
Використовує requests + BeautifulSoup з повною обробкою помилок.
Зберігає результат у data/listings.csv

Запуск:
    python scraper.py
    python scraper.py --category electronics --pages 5
"""

from __future__ import annotations

import argparse
import csv
import logging
import re
import time
import os
from dataclasses import dataclass, asdict, fields
from datetime import datetime
from pathlib import Path
from typing import Iterator

import requests
from bs4 import BeautifulSoup

# ── Логування ──────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Константи ──────────────────────────────────────────────────
BASE_URL = "https://www.olx.ua"

CATEGORIES: dict[str, str] = {
    "electronics":    "/uk/elektronika/",
    "real_estate":    "/uk/nedvizhimost/",
    "cars":           "/uk/transport/legkovye-avtomobili/",
    "jobs":           "/uk/rabota/",
    "clothes":        "/uk/moda-i-stil/",
    "furniture":      "/uk/dom-i-sad/mebel/",
    "services":       "/uk/uslugi/",
    "animals":        "/uk/zhivotnye/",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "uk-UA,uk;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

OUT_PATH = Path("data/listings.csv")


# ── Модель даних ───────────────────────────────────────────────
@dataclass
class Listing:
    title: str
    price_raw: str
    price_uah: float | None
    category: str
    city: str
    region: str
    date_raw: str
    date_parsed: str
    url: str
    is_business: bool
    negotiable: bool
    scraped_at: str

    @classmethod
    def fieldnames(cls) -> list[str]:
        return [f.name for f in fields(cls)]


# ── Допоміжні функції ──────────────────────────────────────────
def parse_price(raw: str) -> tuple[float | None, bool]:
    """
    Повертає (ціна в грн, торг_можливий).
    Приклади: '15 000 грн', 'Договірна', '$ 200'
    """
    if not raw:
        return None, False

    raw = raw.strip()
    negotiable = "договірн" in raw.lower() or "торг" in raw.lower()

    if negotiable and not any(ch.isdigit() for ch in raw):
        return None, True

    # Долари → гривні (приблизний курс)
    usd_rate = 39.5
    if "$" in raw or "USD" in raw.upper():
        nums = re.findall(r"[\d\s]+", raw)
        if nums:
            try:
                val = float(nums[0].replace(" ", "").replace("\u00a0", ""))
                return round(val * usd_rate, 0), negotiable
            except ValueError:
                pass

    nums = re.findall(r"[\d\s]+", raw)
    if nums:
        try:
            val = float(nums[0].replace(" ", "").replace("\u00a0", ""))
            return val, negotiable
        except ValueError:
            pass

    return None, negotiable


def parse_date(raw: str) -> str:
    """Нормалізує дату з OLX у формат YYYY-MM-DD."""
    if not raw:
        return ""
    raw = raw.strip().lower()
    today = datetime.today()

    if "сьогодні" in raw or "today" in raw:
        return today.strftime("%Y-%m-%d")
    if "вчора" in raw or "yesterday" in raw:
        from datetime import timedelta
        return (today - timedelta(days=1)).strftime("%Y-%m-%d")

    months_uk = {
        "січня": "01", "лютого": "02", "березня": "03", "квітня": "04",
        "травня": "05", "червня": "06", "липня": "07", "серпня": "08",
        "вересня": "09", "жовтня": "10", "листопада": "11", "грудня": "12",
    }
    for uk, num in months_uk.items():
        if uk in raw:
            match = re.search(r"(\d{1,2})", raw)
            if match:
                day = match.group(1).zfill(2)
                year = today.year
                return f"{year}-{num}-{day}"
    return raw


def parse_location(location_str: str) -> tuple[str, str]:
    """Розділяє 'Київ, Київська обл.' → ('Київ', 'Київська')."""
    if not location_str:
        return "", ""
    parts = [p.strip() for p in location_str.split(",")]
    city = parts[0] if parts else ""
    region = parts[1].replace(" обл.", "").replace(" область", "").strip() if len(parts) > 1 else city
    return city, region


# ── HTTP клієнт з retry ────────────────────────────────────────
class OLXClient:
    """Requests-сесія з автоматичним retry і throttling."""

    def __init__(self, delay: float = 1.5, retries: int = 3):
        self.delay = delay
        self.retries = retries
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self._last_request = 0.0

    def get(self, url: str, **kwargs) -> requests.Response | None:
        # Throttling
        elapsed = time.time() - self._last_request
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)

        for attempt in range(1, self.retries + 1):
            try:
                resp = self.session.get(url, timeout=15, **kwargs)
                self._last_request = time.time()

                if resp.status_code == 200:
                    return resp
                if resp.status_code == 429:
                    wait = 30 * attempt
                    log.warning("Rate limit — чекаємо %ds...", wait)
                    time.sleep(wait)
                    continue
                if resp.status_code in (403, 404):
                    log.error("HTTP %d для %s", resp.status_code, url)
                    return None

                log.warning("HTTP %d (спроба %d/%d)", resp.status_code, attempt, self.retries)
                time.sleep(3 * attempt)

            except requests.Timeout:
                log.warning("Timeout (спроба %d/%d): %s", attempt, self.retries, url)
                time.sleep(5 * attempt)
            except requests.ConnectionError as exc:
                log.warning("ConnectionError (спроба %d/%d): %s", attempt, self.retries, exc)
                time.sleep(5 * attempt)
            except requests.RequestException as exc:
                log.error("Непередбачена помилка: %s", exc)
                return None

        log.error("Всі %d спроби вичерпано для %s", self.retries, url)
        return None


# ── Парсер сторінки ────────────────────────────────────────────
def parse_listing_card(card: BeautifulSoup, category: str, scraped_at: str) -> Listing | None:
    """Витягує дані з однієї картки оголошення."""
    try:
        # Назва
        title_el = (
            card.select_one("h4") or
            card.select_one("[data-cy='ad-card-title']") or
            card.select_one(".title-cell h3")
        )
        if not title_el:
            return None
        title = title_el.get_text(strip=True)

        # Посилання
        link_el = card.select_one("a[href]")
        url = ""
        if link_el:
            href = link_el.get("href", "")
            url = href if href.startswith("http") else BASE_URL + href

        # Ціна
        price_el = (
            card.select_one("[data-testid='ad-price']") or
            card.select_one(".price strong") or
            card.select_one("[class*='price']")
        )
        price_raw = price_el.get_text(strip=True) if price_el else ""
        price_uah, negotiable = parse_price(price_raw)

        # Локація
        location_el = (
            card.select_one("[data-testid='location-date']") or
            card.select_one(".bottom-cell .breadcrumb") or
            card.select_one("[class*='location']")
        )
        location_text = location_el.get_text(strip=True) if location_el else ""
        # Дата часто склеєна з локацією
        date_raw = ""
        if location_el:
            spans = location_el.find_all(["span", "p"])
            texts = [s.get_text(strip=True) for s in spans]
            if texts:
                date_raw = texts[-1]
                location_text = texts[0] if len(texts) > 1 else location_text

        city, region = parse_location(location_text)
        date_parsed = parse_date(date_raw)

        # Бізнес-акаунт
        is_business = bool(
            card.select_one("[data-testid='business-badge']") or
            card.select_one(".badge-business") or
            card.select_one("[class*='business']")
        )

        return Listing(
            title=title,
            price_raw=price_raw,
            price_uah=price_uah,
            category=category,
            city=city,
            region=region,
            date_raw=date_raw,
            date_parsed=date_parsed,
            url=url,
            is_business=is_business,
            negotiable=negotiable,
            scraped_at=scraped_at,
        )

    except Exception as exc:
        log.debug("Помилка парсингу картки: %s", exc)
        return None


def scrape_category(
    client: OLXClient,
    category: str,
    path: str,
    max_pages: int = 5,
) -> Iterator[Listing]:
    """Генератор: віддає Listing по одному з усіх сторінок категорії."""
    scraped_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    for page in range(1, max_pages + 1):
        url = f"{BASE_URL}{path}"
        params = {"page": page} if page > 1 else {}

        log.info("  Сторінка %d/%d → %s", page, max_pages, url)
        resp = client.get(url, params=params)

        if resp is None:
            log.warning("  Пропускаємо сторінку %d", page)
            break

        soup = BeautifulSoup(resp.text, "html.parser")

        # OLX може мати різні селектори — пробуємо всі
        cards = (
            soup.select("[data-cy='l-card']") or
            soup.select("li.offer-wrapper") or
            soup.select(".offer-titlebox") or
            soup.select("article") or
            []
        )

        if not cards:
            log.info("  Картки не знайдено на сторінці %d — кінець", page)
            break

        found = 0
        for card in cards:
            listing = parse_listing_card(card, category, scraped_at)
            if listing:
                found += 1
                yield listing

        log.info("  Знайдено %d оголошень", found)

        # Перевіряємо чи є наступна сторінка
        next_btn = soup.select_one("[data-cy='pagination-forward']") or \
                   soup.select_one("a[data-testid='pagination-forward']")
        if not next_btn:
            log.info("  Остання сторінка досягнута")
            break


# ── Збереження ─────────────────────────────────────────────────
def save_to_csv(listings: list[Listing], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=Listing.fieldnames())
        writer.writeheader()
        writer.writerows([asdict(l) for l in listings])
    log.info("Збережено %d записів → %s", len(listings), path)


# ── Демо-дані ──────────────────────────────────────────────────
def generate_demo_data() -> list[Listing]:
    """400 реалістичних OLX-оголошень для розробки без інтернету."""
    import random
    import numpy as np

    rng = np.random.default_rng(42)
    random.seed(42)

    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    templates: dict[str, dict] = {
        "electronics": {
            "titles": [
                "iPhone 14 Pro 256GB", "Samsung Galaxy S23", "MacBook Pro M2",
                "iPad Air 5", "AirPods Pro 2", "Sony WH-1000XM5", "PlayStation 5",
                "Nintendo Switch OLED", "Xiaomi 13T Pro", "Google Pixel 8",
                "Ноутбук Lenovo ThinkPad", "Монітор LG 27 4K", "Навушники Bose QC45",
                "Фотоапарат Canon EOS R50", "Планшет Samsung Tab S9",
            ],
            "price_range": (500, 80000),
        },
        "real_estate": {
            "titles": [
                "1-кімнатна квартира в центрі", "2-кімнатна квартира новобудова",
                "Студія біля метро", "3-кімнатна квартира з ремонтом",
                "Оренда кімнати для студентів", "Будинок з ділянкою 10 соток",
                "Офісне приміщення 50 м²", "Комерційна нерухомість",
                "Квартира-студія подобово", "Земельна ділянка під забудову",
            ],
            "price_range": (5000, 3000000),
        },
        "cars": {
            "titles": [
                "Toyota Camry 2020", "Volkswagen Golf 2019", "BMW 5 Series 2021",
                "Skoda Octavia 2022", "Honda CR-V 2020", "Hyundai Tucson 2021",
                "Kia Sportage 2022", "Ford Focus 2018", "Renault Duster 2020",
                "Nissan Qashqai 2019", "Audi A4 2021", "Mercedes C-Class 2020",
            ],
            "price_range": (50000, 1500000),
        },
        "clothes": {
            "titles": [
                "Куртка зимова Nike", "Джинси Levi's 501", "Кросівки Adidas Ultraboost",
                "Сукня вечірня", "Пальто жіноче", "Спортивний костюм",
                "Сумка шкіряна", "Кросівки Nike Air Max", "Светр вовняний",
                "Чоботи зимові", "Рюкзак шкільний", "Кепка New Era",
            ],
            "price_range": (100, 8000),
        },
        "furniture": {
            "titles": [
                "Диван-ліжко розкладний", "Шафа купе 3 двері", "Кухонний гарнітур",
                "Ліжко двоспальне 160х200", "Стіл обідній розкладний",
                "Крісло офісне", "Комод з ящиками", "Стелаж металевий",
                "Матрац пружинний", "Тумбочка прикроватна",
            ],
            "price_range": (500, 50000),
        },
    }

    cities_regions = [
        ("Київ", "Київська"), ("Київ", "Київська"), ("Київ", "Київська"),
        ("Львів", "Львівська"), ("Львів", "Львівська"),
        ("Харків", "Харківська"), ("Дніпро", "Дніпропетровська"),
        ("Одеса", "Одеська"), ("Запоріжжя", "Запорізька"),
        ("Вінниця", "Вінницька"), ("Полтава", "Полтавська"),
        ("Черкаси", "Черкаська"), ("Суми", "Сумська"),
        ("Тернопіль", "Тернопільська"), ("Житомир", "Житомирська"),
    ]

    listings = []
    cats = list(templates.keys())
    n_per_cat = 80

    for cat in cats:
        tmpl = templates[cat]
        for _ in range(n_per_cat):
            title_base = random.choice(tmpl["titles"])
            suffix = random.choice(["", ", б/у", ", торг", ", стан відмінний", ""])
            title = title_base + suffix

            lo, hi = tmpl["price_range"]
            price = int(rng.integers(lo, hi))
            negotiable = random.random() < 0.2
            price_raw = f"{price:,} грн".replace(",", " ") + (" (торг)" if negotiable else "")

            city, region = random.choice(cities_regions)
            days_ago = int(rng.integers(0, 60))
            from datetime import timedelta
            date_obj = datetime.today() - timedelta(days=days_ago)
            date_str = date_obj.strftime("%Y-%m-%d")

            listings.append(Listing(
                title=title,
                price_raw=price_raw,
                price_uah=float(price),
                category=cat,
                city=city,
                region=region,
                date_raw=price_raw,
                date_parsed=date_str,
                url=f"https://www.olx.ua/uk/ad/{cat}-{len(listings)+1}/",
                is_business=random.random() < 0.15,
                negotiable=negotiable,
                scraped_at=now,
            ))

    random.shuffle(listings)
    return listings


# ── CLI ────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="OLX.ua scraper")
    parser.add_argument(
        "--category", default="all",
        help=f"Категорія: all або одна з {list(CATEGORIES.keys())}",
    )
    parser.add_argument("--pages", type=int, default=3, help="Сторінок на категорію")
    parser.add_argument("--demo", action="store_true", help="Використати демо-дані")
    parser.add_argument("--delay", type=float, default=1.5, help="Затримка між запитами (сек)")
    args = parser.parse_args()

    if args.demo:
        log.info("Режим демо-даних...")
        listings = generate_demo_data()
    else:
        client = OLXClient(delay=args.delay)
        cats = CATEGORIES if args.category == "all" else {
            args.category: CATEGORIES.get(args.category, "/uk/")
        }

        listings: list[Listing] = []
        for name, path in cats.items():
            log.info("Категорія: %s", name)
            try:
                cat_listings = list(scrape_category(client, name, path, args.pages))
                listings.extend(cat_listings)
                log.info("Зібрано %d оголошень з '%s'", len(cat_listings), name)
            except KeyboardInterrupt:
                log.info("Перервано користувачем")
                break
            except Exception as exc:
                log.error("Помилка категорії '%s': %s", name, exc)
                continue

        if not listings:
            log.warning("Не вдалось зібрати дані. Генеруємо демо...")
            listings = generate_demo_data()

    save_to_csv(listings, OUT_PATH)
    log.info("Готово! Всього %d оголошень.", len(listings))


if __name__ == "__main__":
    main()
