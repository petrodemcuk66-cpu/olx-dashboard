"""
report.py — генерація PDF через fpdf2 з підтримкою кирилиці
Використовує Arial з Windows (підтримує українську без додаткових шрифтів)
"""

from __future__ import annotations
import io
import os
from datetime import datetime
import pandas as pd
from fpdf import FPDF, XPos, YPos

ORANGE   = (249, 115,  22)
DARK     = ( 15,  23,  42)
SLATE    = ( 71,  85, 105)
LIGHT_BG = (248, 250, 252)
BORDER   = (226, 232, 240)
WHITE    = (255, 255, 255)


def _find_font() -> tuple[str, str]:
    """Знаходить шрифт з підтримкою кирилиці."""

    # 1. DejaVu поруч зі скриптом (якщо поклав вручну)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    local_r = os.path.join(script_dir, "DejaVuSansCondensed.ttf")
    local_b = os.path.join(script_dir, "DejaVuSansCondensed-Bold.ttf")
    if os.path.isfile(local_r) and os.path.isfile(local_b):
        return local_r, local_b

    # 2. DejaVu всередині пакету fpdf2
    try:
        import fpdf as fpdf_module
        fpdf_dir = os.path.dirname(fpdf_module.__file__)
        for folder in [os.path.join(fpdf_dir, "fonts"), fpdf_dir]:
            for rname, bname in [
                ("DejaVuSansCondensed.ttf", "DejaVuSansCondensed-Bold.ttf"),
                ("DejaVuSans.ttf",          "DejaVuSans-Bold.ttf"),
            ]:
                r = os.path.join(folder, rname)
                b = os.path.join(folder, bname)
                if os.path.isfile(r) and os.path.isfile(b):
                    return r, b
        # Рекурсивний пошук
        for root, _, files in os.walk(fpdf_dir):
            ttfs = {f: os.path.join(root, f) for f in files if f.endswith(".ttf")}
            for rname, bname in [
                ("DejaVuSansCondensed.ttf", "DejaVuSansCondensed-Bold.ttf"),
                ("DejaVuSans.ttf",          "DejaVuSans-Bold.ttf"),
            ]:
                if rname in ttfs and bname in ttfs:
                    return ttfs[rname], ttfs[bname]
    except Exception:
        pass

    # 3. Arial з Windows (є на кожному Windows ПК, підтримує кирилицю)
    win_fonts = r"C:\Windows\Fonts"
    for rname, bname in [
        ("arial.ttf",   "arialbd.ttf"),
        ("Arial.ttf",   "Arial Bold.ttf"),
        ("tahoma.ttf",  "tahomabd.ttf"),
        ("calibri.ttf", "calibrib.ttf"),
    ]:
        r = os.path.join(win_fonts, rname)
        b = os.path.join(win_fonts, bname)
        if os.path.isfile(r) and os.path.isfile(b):
            return r, b

    # 4. Будь-який TTF з підтримкою кирилиці з Windows
    if os.path.isdir(win_fonts):
        ttfs = [f for f in os.listdir(win_fonts) if f.lower().endswith(".ttf")]
        if ttfs:
            # Повертаємо один і той самий для regular і bold (гірше але працює)
            path = os.path.join(win_fonts, ttfs[0])
            return path, path

    raise FileNotFoundError(
        "Не знайдено жодного TTF шрифту.\n"
        "Поклади файли DejaVuSansCondensed.ttf та DejaVuSansCondensed-Bold.ttf "
        "в папку проєкту:\n" + script_dir
    )


class OLXReport(FPDF):
    def __init__(self):
        super().__init__()
        self.set_auto_page_break(auto=True, margin=18)
        self.set_margins(14, 14, 14)
        regular, bold = _find_font()
        self.add_font("Custom", style="",  fname=regular)
        self.add_font("Custom", style="B", fname=bold)
        self._fname = "Custom"

    def _set(self, bold=False, size=10):
        self.set_font(self._fname, "B" if bold else "", size)

    def header(self):
        self._set(bold=True, size=18)
        self.set_text_color(*ORANGE)
        self.cell(22, 10, "OLX.", new_x=XPos.RIGHT, new_y=YPos.TOP)
        self._set(size=9)
        self.set_text_color(*SLATE)
        self.set_y(self.get_y() + 4)
        self.cell(0, 6, "Аналітика оголошень · olx.ua",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*ORANGE)
        self.set_line_width(0.8)
        self.line(14, self.get_y(), 196, self.get_y())
        self.set_line_width(0.2)
        self.set_draw_color(*BORDER)
        self.ln(4)

    def footer(self):
        self.set_y(-14)
        self._set(size=8)
        self.set_text_color(*SLATE)
        self.cell(0, 6,
            f"OLX Analytics · Портфоліо-проєкт Python · Стор. {self.page_no()}/{{nb}}",
            align="C")

    def section_title(self, text: str):
        self.ln(3)
        self.set_fill_color(*ORANGE)
        self.rect(14, self.get_y(), 3, 7, style="F")
        self.set_x(19)
        self._set(bold=True, size=12)
        self.set_text_color(*DARK)
        self.cell(0, 7, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(2)

    def kpi_grid(self, items: list):
        cols = 4
        w = (self.w - 28) / cols
        h = 17
        for i, (label, value) in enumerate(items):
            col = i % cols
            if col == 0 and i > 0:
                self.ln(h + 2)
            x = 14 + col * (w + 2)
            y = self.get_y()
            self.set_fill_color(255, 247, 237)
            self.set_draw_color(254, 215, 170)
            self.rect(x, y, w, h, style="FD")
            self.set_xy(x, y + 1)
            self._set(bold=True, size=12)
            self.set_text_color(*ORANGE)
            self.cell(w, 7, value, align="C", new_x=XPos.RIGHT, new_y=YPos.TOP)
            self.set_xy(x, y + 9)
            self._set(size=7)
            self.set_text_color(*SLATE)
            self.cell(w, 5, label, align="C", new_x=XPos.RIGHT, new_y=YPos.TOP)
        self.ln(h + 4)

    def table(self, headers, rows, col_widths, aligns=None):
        if aligns is None:
            aligns = ["L"] * len(headers)
        row_h = 7
        self.set_fill_color(*DARK)
        self.set_text_color(*WHITE)
        self._set(bold=True, size=8)
        for h, w in zip(headers, col_widths):
            self.cell(w, row_h, h, border=0, fill=True,
                      new_x=XPos.RIGHT, new_y=YPos.TOP)
        self.ln(row_h)
        self._set(size=8)
        for ri, row in enumerate(rows):
            if self.get_y() + row_h > self.h - 20:
                self.add_page()
            fill = ri % 2 == 0
            self.set_fill_color(*LIGHT_BG if fill else WHITE)
            self.set_text_color(*DARK)
            self.set_draw_color(*BORDER)
            for cell, w, align in zip(row, col_widths, aligns):
                self.cell(w, row_h, str(cell), border="B", fill=fill,
                          align=align, new_x=XPos.RIGHT, new_y=YPos.TOP)
            self.ln(row_h)
        self.ln(2)

    def progress_bar(self, x, y, w, pct):
        self.set_fill_color(*BORDER)
        self.rect(x, y, w, 4, style="F")
        self.set_fill_color(*ORANGE)
        self.rect(x, y, max(1, w * pct / 100), 4, style="F")


def generate_pdf(df, stats, cat_df, city_df) -> bytes:
    from analysis import top_listings

    pdf = OLXReport()
    pdf.alias_nb_pages()
    pdf.add_page()

    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    pdf._set(size=8)
    pdf.set_text_color(*SLATE)
    pdf.cell(0, 5, f"Звіт згенеровано: {now}",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(2)

    pdf.section_title("Ключові показники")
    pdf.kpi_grid([
        ("Оголошень",     str(stats["total"])),
        ("Категорій",     str(stats["categories"])),
        ("Міст",          str(stats["cities"])),
        ("Середня ціна",  f"грн {stats['avg_price']:,.0f}".replace(",", " ")),
        ("Медіана ціни",  f"грн {stats['median_price']:,.0f}".replace(",", " ")),
        ("З торгом",      f"{stats['negotiable_pct']}%"),
        ("Бізнес",        f"{stats['business_pct']}%"),
        ("Нові сьогодні", str(stats["new_today"])),
    ])

    pdf.section_title("Оголошення по категоріях")
    cat_rows = cat_df.to_dict("records")
    max_count = cat_rows[0]["count"] if cat_rows else 1
    headers = ["#", "Категорія", "Оголошень", "Частка", "Медіана грн", "Розподіл"]
    col_w   = [8, 48, 28, 22, 36, 40]
    pdf.set_fill_color(*DARK)
    pdf.set_text_color(*WHITE)
    pdf._set(bold=True, size=8)
    for h, w in zip(headers, col_w):
        pdf.cell(w, 7, h, border=0, fill=True, new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf.ln(7)
    for ri, r in enumerate(cat_rows):
        if pdf.get_y() + 8 > pdf.h - 20:
            pdf.add_page()
        fill = ri % 2 == 0
        pdf.set_fill_color(*LIGHT_BG if fill else WHITE)
        pdf.set_text_color(*DARK)
        pdf._set(size=8)
        y0 = pdf.get_y()
        med = f"грн {r['median_price']:,.0f}".replace(",", " ") \
              if r.get("median_price") else "-"
        for txt, w, align in [
            (str(ri + 1),                          col_w[0], "C"),
            (r.get("category_ua", r["category"]), col_w[1], "L"),
            (str(r["count"]),                      col_w[2], "R"),
            (f"{r['share_pct']:.1f}%",             col_w[3], "R"),
            (med,                                  col_w[4], "R"),
        ]:
            pdf.cell(w, 7, txt, border="B", fill=fill, align=align,
                     new_x=XPos.RIGHT, new_y=YPos.TOP)
        bar_x = pdf.get_x()
        pdf.cell(col_w[5], 7, "", border="B", fill=fill,
                 new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.progress_bar(bar_x + 1, y0 + 2, col_w[5] - 4,
                         r["count"] / max_count * 100)
        pdf.ln(7)
    pdf.ln(4)

    pdf.section_title("Топ міст")
    city_rows = []
    for _, r in city_df.head(10).iterrows():
        med = f"грн {r['median_price']:,.0f}".replace(",", " ") \
              if r.get("median_price") else "-"
        city_rows.append([str(len(city_rows)+1), r["city"], str(r["count"]), med])
    pdf.table(["#", "Місто", "Оголошень", "Медіана ціни"],
              city_rows, [10, 60, 35, 77], ["C", "L", "R", "R"])

    pdf.section_title("Топ-10 найдорожчих оголошень")
    top_df = top_listings(df, top_n=10)
    top_rows = []
    for _, r in top_df.iterrows():
        title = str(r.get("title", ""))
        title = title[:36] + "..." if len(title) > 36 else title
        price = f"грн {r['price_uah']:,.0f}".replace(",", " ") \
                if pd.notna(r.get("price_uah")) else "-"
        flags = ("Бізнес " if r.get("is_business") else "") + \
                ("Торг"   if r.get("negotiable")   else "")
        top_rows.append([title, str(r.get("category_ua", "")),
                         str(r.get("city", "")), price, flags.strip()])
    pdf.table(["Назва", "Категорія", "Місто", "Ціна", "Тип"],
              top_rows, [62, 28, 28, 38, 26], ["L", "L", "L", "R", "C"])

    result = pdf.output()
    return bytes(result) if not isinstance(result, bytes) else result