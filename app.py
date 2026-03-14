"""
app.py — OLX Analytics Dashboard
Запуск: streamlit run app.py
"""

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from analysis import (
    load_data, clean, summary_stats, by_category, by_city,
    listings_by_date, price_distribution, top_listings,
    negotiable_stats, business_vs_private, heatmap_city_category, freshness,
)
from report import generate_pdf

# ── Конфігурація ───────────────────────────────────────────────
st.set_page_config(
    page_title="OLX Analytics",
    page_icon="🛒",
    layout="wide",
    initial_sidebar_state="expanded",
)

PALETTE = {
    "electronics": "#60A5FA",
    "real_estate":  "#34D399",
    "cars":         "#F59E0B",
    "clothes":      "#F472B6",
    "furniture":    "#A78BFA",
    "jobs":         "#FB923C",
    "services":     "#2DD4BF",
    "animals":      "#86EFAC",
}

st.markdown("""
<style>
[data-testid="stMetric"] {
    background: var(--secondary-background-color);
    border-radius: 10px;
    padding: 12px 16px;
    border: 1px solid rgba(255,255,255,0.07);
}
[data-testid="stMetricLabel"] { font-size: 12px !important; }
</style>
""", unsafe_allow_html=True)


# ── Дані ───────────────────────────────────────────────────────
@st.cache_data(ttl=1800, show_spinner="Завантажуємо дані...")
def get_data() -> pd.DataFrame:
    return clean(load_data())


df_raw = get_data()

# ── Сайдбар ────────────────────────────────────────────────────
with st.sidebar:
    st.title("🛒 OLX Analytics")
    st.caption("Аналіз оголошень OLX.ua")
    st.divider()

    all_cats = sorted(df_raw["category"].unique())
    cat_labels = df_raw.drop_duplicates("category").set_index("category")["category_ua"].to_dict()
    sel_cats = st.multiselect(
        "Категорія",
        options=all_cats,
        default=all_cats,
        format_func=lambda x: cat_labels.get(x, x),
    )

    all_cities = sorted(df_raw["city"].unique())
    sel_cities = st.multiselect(
        "Місто",
        options=all_cities,
        default=[c for c in ["Київ", "Львів", "Харків", "Дніпро", "Одеса"] if c in all_cities],
    )
    if not sel_cities:
        sel_cities = all_cities

    price_min, price_max = 0, int(min(df_raw["price_uah"].quantile(0.99), 500_000))
    price_range = st.slider(
        "Ціна (грн)",
        min_value=price_min,
        max_value=price_max,
        value=(price_min, price_max),
        step=500,
        format="%d₴",
    )

    show_business = st.checkbox("Показати бізнес-оголошення", value=True)
    show_negotiable = st.checkbox("Показати оголошення з торгом", value=True)

    st.divider()
    st.caption(f"Всього у базі: **{len(df_raw):,}** оголошень")

    # Кнопка оновлення
    if st.button("🔄 Оновити дані", use_container_width=True):
        st.cache_data.clear()
        st.rerun()


# ── Фільтрація ─────────────────────────────────────────────────
df = df_raw.copy()
if sel_cats:
    df = df[df["category"].isin(sel_cats)]
df = df[df["city"].isin(sel_cities)]
if not show_business:
    df = df[~df["is_business"]]
if not show_negotiable:
    df = df[~df["negotiable"]]
df = df[
    (~df["has_price"]) |
    df["price_uah"].between(price_range[0], price_range[1])
]

if df.empty:
    st.warning("⚠ Немає даних для вибраних фільтрів.")
    st.stop()

# ── Заголовок ──────────────────────────────────────────────────
st.title("🛒 OLX Ukraine — Аналітика оголошень")
st.caption(f"Дані: olx.ua · Оновлено: {df_raw['scraped_at'].iloc[0] if 'scraped_at' in df_raw.columns else 'н/д'}")

# ── Метрики ────────────────────────────────────────────────────
stats = summary_stats(df)
c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("Оголошень",    f"{stats['total']:,}")
c2.metric("Категорій",    stats["categories"])
c3.metric("Міст",         stats["cities"])
c4.metric("Середня ціна", f"₴{stats['avg_price']:,.0f}")
c5.metric("Медіана ціни", f"₴{stats['median_price']:,.0f}")
c6.metric("З торгом",     f"{stats['negotiable_pct']}%")

st.divider()

# ── Ряд 1: Категорії + Динаміка ────────────────────────────────
col1, col2 = st.columns([2, 3])

with col1:
    st.subheader("По категоріях")
    cat_df = by_category(df)
    colors = [PALETTE.get(c, "#94A3B8") for c in cat_df["category"]]
    fig = go.Figure(go.Bar(
        x=cat_df["count"],
        y=cat_df["category_ua"],
        orientation="h",
        marker_color=colors,
        text=cat_df["count"],
        textposition="outside",
        hovertemplate="<b>%{y}</b><br>Оголошень: %{x}<br>Середня ціна: ₴%{customdata:,.0f}<extra></extra>",
        customdata=cat_df["avg_price"].fillna(0),
    ))
    fig.update_layout(
        height=340,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=0, r=60, t=10, b=0),
        yaxis=dict(categoryorder="total ascending"),
        showlegend=False,
        xaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)"),
    )
    st.plotly_chart(fig, use_container_width=True)

with col2:
    st.subheader("Динаміка оголошень (останні 30 днів)")
    date_df = listings_by_date(df, days=30)
    if not date_df.empty and len(date_df) > 2:
        fig2 = px.area(
            date_df,
            x="date_parsed",
            y="count",
            labels={"date_parsed": "", "count": "Оголошень"},
            color_discrete_sequence=["#60A5FA"],
        )
        fig2.update_traces(fill="tozeroy", line_width=2)
        fig2.update_layout(
            height=340,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=0, r=0, t=10, b=0),
            xaxis=dict(showgrid=False),
            yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)"),
        )
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("Недостатньо даних для графіку динаміки.")

# ── Ряд 2: Ціни ───────────────────────────────────────────────
st.subheader("Розподіл цін по категоріях")
price_df = price_distribution(df)
if not price_df.empty:
    fig3 = px.box(
        price_df,
        x="category_ua",
        y="price_uah",
        color="category_ua",
        color_discrete_sequence=list(PALETTE.values()),
        labels={"price_uah": "Ціна (грн)", "category_ua": ""},
        points=False,
    )
    fig3.update_layout(
        height=340,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
        margin=dict(l=0, r=0, t=10, b=0),
        xaxis_tickangle=-20,
        yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)"),
    )
    st.plotly_chart(fig3, use_container_width=True)

# ── Ряд 3: Міста + Свіжість ───────────────────────────────────
col3, col4 = st.columns(2)

with col3:
    st.subheader("Топ міст")
    city_df = by_city(df, 10)
    fig4 = px.bar(
        city_df,
        x="count",
        y="city",
        orientation="h",
        color="median_price",
        color_continuous_scale="Teal",
        text="count",
        labels={"count": "Оголошень", "city": "", "median_price": "Медіана ₴"},
    )
    fig4.update_layout(
        height=360,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=0, r=60, t=10, b=0),
        yaxis=dict(categoryorder="total ascending"),
        coloraxis_colorbar=dict(title="Медіана ₴", thickness=12),
    )
    fig4.update_traces(textposition="outside")
    st.plotly_chart(fig4, use_container_width=True)

with col4:
    st.subheader("Свіжість оголошень")
    fresh_df = freshness(df)
    fig5 = px.pie(
        fresh_df,
        values="count",
        names="age_group",
        color_discrete_sequence=px.colors.sequential.Blues_r,
        hole=0.4,
    )
    fig5.update_layout(
        height=360,
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=0, r=0, t=10, b=20),
        legend=dict(orientation="v", x=1, y=0.5),
    )
    fig5.update_traces(textposition="inside", textinfo="percent+label")
    st.plotly_chart(fig5, use_container_width=True)

# ── Ряд 4: Бізнес vs Приватні + Торг ─────────────────────────
col5, col6 = st.columns(2)

with col5:
    st.subheader("Бізнес vs приватні продавці")
    bv_df = business_vs_private(df)
    if not bv_df.empty:
        fig6 = px.bar(
            bv_df,
            x="category_ua",
            y="count",
            color="seller",
            barmode="group",
            color_discrete_map={"Бізнес": "#F59E0B", "Приватний": "#60A5FA"},
            labels={"count": "Оголошень", "category_ua": "", "seller": ""},
        )
        fig6.update_layout(
            height=300,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=0, r=0, t=10, b=0),
            xaxis_tickangle=-25,
            legend=dict(orientation="h", y=1.1),
        )
        st.plotly_chart(fig6, use_container_width=True)

with col6:
    st.subheader("Торг: вплив на ціну")
    neg_df = negotiable_stats(df)
    if not neg_df.empty:
        fig7 = px.bar(
            neg_df,
            x="label",
            y="median",
            color="label",
            color_discrete_map={"Торг": "#34D399", "Фіксована": "#F472B6"},
            text=neg_df["median"].apply(lambda x: f"₴{x:,.0f}"),
            labels={"median": "Медіана ціни (грн)", "label": ""},
        )
        fig7.update_layout(
            height=300,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            showlegend=False,
            margin=dict(l=0, r=0, t=10, b=0),
        )
        fig7.update_traces(textposition="outside")
        st.plotly_chart(fig7, use_container_width=True)

# ── Теплова карта ─────────────────────────────────────────────
st.subheader("Медіана ціни (грн): місто × категорія")
hm_df = heatmap_city_category(df)
if not hm_df.empty:
    fig8 = go.Figure(go.Heatmap(
        z=hm_df.values,
        x=hm_df.columns.tolist(),
        y=hm_df.index.tolist(),
        colorscale="Teal",
        text=hm_df.values,
        texttemplate="₴%{text:,.0f}",
        textfont={"size": 10},
        hoverongaps=False,
        colorbar=dict(title="₴", thickness=12),
    ))
    fig8.update_layout(
        height=300,
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=0, r=0, t=10, b=0),
        xaxis_tickangle=-25,
    )
    st.plotly_chart(fig8, use_container_width=True)

# ── Таблиця оголошень ──────────────────────────────────────────
st.subheader("📋 Оголошення")
tab1, tab2 = st.tabs(["Топ за ціною", "Всі оголошення"])

with tab1:
    top_df = top_listings(df, top_n=20)
    st.dataframe(
        top_df.rename(columns={
            "title": "Назва", "category_ua": "Категорія",
            "city": "Місто", "price_uah": "Ціна (грн)",
            "negotiable": "Торг", "is_business": "Бізнес",
            "date_parsed": "Дата",
        }),
        use_container_width=True, hide_index=True, height=380,
        column_config={
            "Ціна (грн)": st.column_config.NumberColumn(format="₴%d"),
        },
    )

with tab2:
    show_cols = ["title", "category_ua", "city", "price_uah", "price_raw",
                 "negotiable", "is_business", "date_parsed"]
    show_cols = [c for c in show_cols if c in df.columns]
    st.dataframe(
        df[show_cols].rename(columns={
            "title": "Назва", "category_ua": "Категорія",
            "city": "Місто", "price_uah": "Ціна (грн)",
            "price_raw": "Ціна (сирова)", "negotiable": "Торг",
            "is_business": "Бізнес", "date_parsed": "Дата",
        }),
        use_container_width=True, hide_index=True, height=420,
        column_config={
            "Ціна (грн)": st.column_config.NumberColumn(format="₴%d"),
        },
    )

# ── PDF ────────────────────────────────────────────────────────
st.divider()
st.subheader("📄 PDF-звіт")
col_a, col_b = st.columns([1, 2])
with col_a:
    if st.button("Згенерувати PDF", type="primary", use_container_width=True):
        with st.spinner("Генеруємо звіт..."):
            pdf_bytes = generate_pdf(df, stats, by_category(df), by_city(df, 10))
        st.download_button(
            label="⬇ Завантажити PDF",
            data=pdf_bytes,
            file_name=f"olx_report_{pd.Timestamp.now().strftime('%Y%m%d')}.pdf",
            mime="application/pdf",
            use_container_width=True,
        )
with col_b:
    st.caption(
        "Звіт включає: загальну статистику, топ категорій, "
        "топ міст, аналіз цін та таблицю найдорожчих оголошень."
    )

st.divider()
st.caption("OLX Analytics · Портфоліо-проєкт · [GitHub](https://github.com/yourusername/olx-dashboard)")