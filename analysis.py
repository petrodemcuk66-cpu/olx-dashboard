"""
analysis.py — аналіз OLX-оголошень з pandas
Всі функції повертають готові DataFrame для дашборду і PDF.
"""

from __future__ import annotations

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta

DATA_PATH = Path("data/listings.csv")

CATEGORY_UA: dict[str, str] = {
    "electronics": "Електроніка",
    "real_estate": "Нерухомість",
    "cars": "Авто",
    "jobs": "Робота",
    "clothes": "Одяг",
    "furniture": "Меблі",
    "services": "Послуги",
    "animals": "Тварини",
}


# ── Завантаження ───────────────────────────────────────────────
def load_data() -> pd.DataFrame:
    if DATA_PATH.exists():
        df = pd.read_csv(DATA_PATH, encoding="utf-8-sig")
    else:
        from scraper import generate_demo_data
        from dataclasses import asdict
        listings = generate_demo_data()
        df = pd.DataFrame([asdict(l) for l in listings])
        DATA_PATH.parent.mkdir(exist_ok=True)
        df.to_csv(DATA_PATH, index=False, encoding="utf-8-sig")
    return df


# ── Очищення ───────────────────────────────────────────────────
def clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # Числові
    df["price_uah"] = pd.to_numeric(df["price_uah"], errors="coerce")
    df["has_price"] = df["price_uah"].notna() & (df["price_uah"] > 0)

    # Дата
    df["date_parsed"] = pd.to_datetime(df["date_parsed"], errors="coerce")
    df["days_ago"] = (datetime.today() - df["date_parsed"]).dt.days.clip(lower=0)
    df["week"] = df["date_parsed"].dt.to_period("W").astype(str)

    # Булеві
    for col in ("is_business", "negotiable"):
        if col in df.columns:
            df[col] = df[col].astype(str).str.lower().isin(("true", "1", "yes"))

    # Категорія → укр назва
    df["category_ua"] = df["category"].map(CATEGORY_UA).fillna(df["category"])

    # Місто: нормалізуємо порожні
    df["city"] = df["city"].fillna("Невідомо").replace("", "Невідомо")
    df["region"] = df["region"].fillna("Невідомо").replace("", "Невідомо")

    # Прибираємо очевидні аномалії цін (< 1 або > 10 млн)
    df.loc[df["price_uah"] < 1, "price_uah"] = np.nan
    df.loc[df["price_uah"] > 10_000_000, "price_uah"] = np.nan

    return df


# ── Загальна статистика ────────────────────────────────────────
def summary_stats(df: pd.DataFrame) -> dict:
    paid = df[df["has_price"]]
    total = len(df)
    return {
        "total":          total,
        "categories":     df["category"].nunique(),
        "cities":         df["city"].nunique(),
        "avg_price":      round(paid["price_uah"].mean(), 0) if not paid.empty else 0,
        "median_price":   round(paid["price_uah"].median(), 0) if not paid.empty else 0,
        "negotiable_pct": round(df["negotiable"].mean() * 100, 1),
        "business_pct":   round(df["is_business"].mean() * 100, 1),
        "with_price_pct": round(df["has_price"].mean() * 100, 1),
        "new_today":      int((df["days_ago"] == 0).sum()),
    }


# ── По категоріях ──────────────────────────────────────────────
def by_category(df: pd.DataFrame) -> pd.DataFrame:
    paid = df[df["has_price"]]
    count = df.groupby(["category", "category_ua"]).size().rename("count").reset_index()
    avg = paid.groupby("category")["price_uah"].mean().round(0).rename("avg_price").reset_index()
    med = paid.groupby("category")["price_uah"].median().round(0).rename("median_price").reset_index()
    result = count.merge(avg, on="category", how="left").merge(med, on="category", how="left")
    result["share_pct"] = (result["count"] / result["count"].sum() * 100).round(1)
    return result.sort_values("count", ascending=False).reset_index(drop=True)


# ── По містах ──────────────────────────────────────────────────
def by_city(df: pd.DataFrame, top_n: int = 12) -> pd.DataFrame:
    paid = df[df["has_price"]]
    count = df.groupby("city").size().rename("count")
    avg = paid.groupby("city")["price_uah"].median().round(0).rename("median_price")
    result = pd.concat([count, avg], axis=1).reset_index()
    return result.sort_values("count", ascending=False).head(top_n).reset_index(drop=True)


# ── Динаміка по днях ───────────────────────────────────────────
def listings_by_date(df: pd.DataFrame, days: int = 30) -> pd.DataFrame:
    cutoff = datetime.today() - timedelta(days=days)
    recent = df[df["date_parsed"] >= cutoff].copy()
    result = (
        recent.groupby("date_parsed")
        .size()
        .rename("count")
        .reset_index()
        .sort_values("date_parsed")
    )
    result["date_str"] = result["date_parsed"].dt.strftime("%d.%m")
    return result


# ── Розподіл цін ───────────────────────────────────────────────
def price_distribution(df: pd.DataFrame, category: str | None = None) -> pd.DataFrame:
    d = df[df["has_price"]].copy()
    if category:
        d = d[d["category"] == category]
    # Відкидаємо топ-1% (outliers)
    q99 = d["price_uah"].quantile(0.99)
    d = d[d["price_uah"] <= q99]
    return d[["price_uah", "category", "category_ua", "city"]].dropna()


# ── Топ оголошень ──────────────────────────────────────────────
def top_listings(df: pd.DataFrame, by: str = "price_uah", top_n: int = 10) -> pd.DataFrame:
    cols = ["title", "category_ua", "city", "price_uah", "negotiable",
            "is_business", "date_parsed", "url"]
    cols = [c for c in cols if c in df.columns]
    paid = df[df["has_price"]][cols].dropna(subset=["price_uah"])
    return paid.nlargest(top_n, "price_uah").reset_index(drop=True)


# ── Ціна: торг vs фіксована ───────────────────────────────────
def negotiable_stats(df: pd.DataFrame) -> pd.DataFrame:
    paid = df[df["has_price"]]
    result = (
        paid.groupby("negotiable")["price_uah"]
        .agg(count="count", mean="mean", median="median")
        .round(0)
        .reset_index()
    )
    result["label"] = result["negotiable"].map({True: "Торг", False: "Фіксована"})
    return result


# ── Бізнес vs приватні ────────────────────────────────────────
def business_vs_private(df: pd.DataFrame) -> pd.DataFrame:
    paid = df[df["has_price"]]
    result = (
        paid.groupby(["category_ua", "is_business"])["price_uah"]
        .agg(count="count", median="median")
        .round(0)
        .reset_index()
    )
    result["seller"] = result["is_business"].map({True: "Бізнес", False: "Приватний"})
    return result


# ── Теплова карта: місто × категорія ──────────────────────────
def heatmap_city_category(df: pd.DataFrame, top_cities: int = 8) -> pd.DataFrame:
    top = by_city(df, top_cities)["city"].tolist()
    filtered = df[df["city"].isin(top) & df["has_price"]]
    pivot = filtered.pivot_table(
        values="price_uah",
        index="city",
        columns="category_ua",
        aggfunc="median",
    ).round(0)
    pivot = pivot.reindex(top)
    return pivot


# ── Свіжість оголошень ────────────────────────────────────────
def freshness(df: pd.DataFrame) -> pd.DataFrame:
    bins = [0, 1, 3, 7, 14, 30, 9999]
    labels = ["Сьогодні", "2-3 дні", "4-7 днів", "8-14 днів", "15-30 днів", "Старіші"]
    df2 = df.copy()
    df2["age_group"] = pd.cut(df2["days_ago"], bins=bins, labels=labels, right=True)
    result = (
        df2.groupby("age_group", observed=True)
        .size()
        .rename("count")
        .reset_index()
    )
    return result


if __name__ == "__main__":
    df = clean(load_data())
    stats = summary_stats(df)
    print("=== Статистика ===")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    print("\n=== По категоріях ===")
    print(by_category(df)[["category_ua", "count", "avg_price", "share_pct"]].to_string(index=False))
    print("\n=== Топ міст ===")
    print(by_city(df, 6).to_string(index=False))
