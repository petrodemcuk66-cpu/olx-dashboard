# 🛒 OLX Ukraine — Analytics Dashboard

[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://your-app.streamlit.app)
![Python](https://img.shields.io/badge/Python-3.11+-blue?logo=python)
![License](https://img.shields.io/badge/license-MIT-green)

Інтерактивний дашборд для аналізу оголошень з [OLX.ua](https://www.olx.ua).

---

## 🚀 Live Demo
👉 **[your-app.streamlit.app](https://your-app.streamlit.app)**

---

## ✨ Що вміє

| Функція | Технологія |
|---|---|
| Парсинг 5 категорій OLX | `requests` + `BeautifulSoup` |
| Retry, throttling, обробка помилок | власний `OLXClient` |
| Аналіз та агрегація | `pandas` |
| 8 типів інтерактивних графіків | `plotly` |
| Фільтри: категорія, місто, ціна | `streamlit` |
| PDF-звіт з одного кліку | `WeasyPrint` + `Jinja2` |
| Деплой | Streamlit Cloud (безкоштовно) |

---

## 📁 Структура

```
olx-dashboard/
├── app.py            # Streamlit дашборд
├── scraper.py        # OLX парсер з retry
├── analysis.py       # Аналіз з pandas
├── report.py         # PDF генератор
├── data/
│   └── listings.csv  # Зібрані дані
├── .streamlit/
│   └── config.toml   # Темна тема
├── requirements.txt
└── README.md
```

---

## 🛠 Локальний запуск

```bash
git clone https://github.com/yourusername/olx-dashboard.git
cd olx-dashboard
pip install -r requirements.txt

# Збираємо дані (або пропусти — автоматично буде демо)
python scraper.py --pages 3

# Тільки демо-дані (без інтернету)
python scraper.py --demo

# Запускаємо дашборд
streamlit run app.py
```

---

## ☁ Деплой на Streamlit Cloud

1. Форкни репо на GitHub
2. [streamlit.io/cloud](https://streamlit.io/cloud) → New app
3. Обери репо → `app.py` → **Deploy**

Безкоштовно. Займає 2 хвилини.

---

## 📄 Ліцензія
MIT
