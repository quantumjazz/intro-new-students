#!/usr/bin/env python3
"""Generate the program-scheme visuals for vavedenie.qmd.

    python3 tools/program_slides.py

Writes, next to the deck:
  _program/karta.qmd          credit map (one slide body, five fragments)
  _program/bars-1.qmd … -4    semester bars for the four year slides
  _program/semestar-2.qmd     six auto-animate slides: filling semester II

All course data lives in this file: edit the tables below when the scheme
or the catalog changes, run the script, re-render the deck. Colours come
from classes (.k-prog, .k-genb, .k-proj, .k-gen, .k-grad) in vavedenie.scss.

Source: Програмна схема, випуск 2025/2026 (Приложение 3 към Наредбата за
учебния процес на НБУ); курсове по електронния каталог 2026/2027.
"""

from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "_program"

PROG, GENB, PROJ, GEN, GRAD = "k-prog", "k-genb", "k-proj", "k-gen", "k-grad"

# ---------------------------------------------------------------------------
# The scheme: per semester, blocks of (kind, credits, courses, name, detail).
# ---------------------------------------------------------------------------

YEAR_1 = [
    (PROG, 15, 5, "Курсове от програмата", "5 от 6"),
    (GENB, 3, 1, "GENB", "1 от 2"),
    (GEN, 6, 1, "Чужд език", ""),
    (GEN, 3, 1, "Бълг. език", ""),
    (GEN, 3, 1, "Знания", ""),
]
YEAR_2 = [
    (PROG, 21, 7, "Курсове от програмата", "всички 7"),
    (GENB, 6, 2, "GENB", "2 от 4"),
    (GEN, 3, 1, "Знания", ""),
]
SEMESTERS = {
    "I": YEAR_1,
    "II": YEAR_1,
    "III": YEAR_2,
    "IV": YEAR_2,
    "V": [
        (PROG, 18, 6, "Курсове от програмата", "6 от 7"),
        (PROJ, 6, 1, "Семинар", "1 от 2"),
        (PROJ, 6, 1, "Практика", ""),
    ],
    "VI": [
        (PROG, 18, 6, "Курсове от програмата", "6 от 7"),
        (PROJ, 6, 1, "Семинар / проект", "1 от 2"),
        (PROJ, 6, 1, "Практика", ""),
    ],
    "VII": [
        (PROG, 18, 6, "Курсове от програмата", "6 от 8"),
        (PROJ, 6, 1, "Семинар", "1 от 2"),
        (PROJ, 6, 1, "Стаж I", ""),
    ],
    "VIII": [
        (PROG, 15, 5, "Курсове от програмата", "5 от 7"),
        (PROJ, 6, 1, "Семинар / проект", "1 от 2"),
        (PROJ, 9, 1, "Стаж II", ""),
    ],
}
GRADUATION = (GRAD, 10, 1, "Дипломиране", "теза или държавен изпит")

YEARS = [
    ("Първа<br>година", ["I", "II"]),
    ("Втора<br>година", ["III", "IV"]),
    ("Трета<br>година", ["V", "VI"]),
    ("Четвърта<br>година", ["VII", "VIII"]),
]
PARTS = {
    0: "Първа и втора година: Факултет за базово образование",
    2: "Трета и четвърта година: Бакалавърски факултет",
}

# Rough width of a 24px Sofia Sans label, used to decide whether the detail fits.
CHAR_PX = 12.6


def block_cells(blocks, credit_px, two_lines):
    """Cells on a 30-column grid (one column per credit) plus one label per block."""
    parts = []
    col = 1
    for kind, credits, courses, name, detail in blocks:
        per = credits // courses
        for i in range(courses):
            parts.append(
                f'<div class="cell {kind}" style="grid-column:{col + i * per} / span {per}"></div>'
            )
        credits_text = f"{credits} кр."
        if two_lines:
            sub = ", ".join(x for x in (credits_text, detail) if x)
            if len(sub) * CHAR_PX > credits * credit_px - 20:
                sub = detail or credits_text  # narrow cell: keep the more telling half
            label = f"<b>{escape(name)}</b><span>{escape(sub)}</span>"
        else:
            wide = f"{name} · {detail}" if detail else name
            fits = len(wide) * CHAR_PX <= credits * credit_px - 24
            label = f"<b>{escape(name)}</b>" + (f"<span> · {escape(detail)}</span>" if detail and fits else "")
        parts.append(
            f'<div class="blk-label {kind}" style="grid-column:{col} / span {credits}">{label}</div>'
        )
        col += credits
    return "".join(parts)


def row_html(sem, blocks, credit_px, two_lines, total="30 кр."):
    return (
        f'<div class="cmap-row"><div class="cmap-sem">{sem}</div>'
        f'<div class="cmap-cells">{block_cells(blocks, credit_px, two_lines)}</div>'
        f'<div class="cmap-total">{total}</div></div>'
    )


def graduation_row(credit_px, two_lines, note):
    kind, credits, _, name, detail = GRADUATION
    label = (
        f"<b>{name}</b><span>{credits} кр., {detail}</span>" if two_lines
        else f"<b>{name}</b><span> · {credits} кр.</span>"
    )
    return (
        '<div class="cmap-row"><div class="cmap-sem"></div><div class="cmap-cells">'
        f'<div class="cell {kind}" style="grid-column:1 / span {credits}"></div>'
        f'<div class="blk-label {kind}" style="grid-column:1 / span {credits}">{label}</div>'
        f'<div class="cmap-sum" style="grid-column:{credits + 2} / span {29 - credits}">{note}</div>'
        '</div><div class="cmap-total"></div></div>'
    )


def raw(html):
    return f"```{{=html}}\n{html}\n```\n"


# ---------------------------------------------------------------------------
# Credit map: all eight semesters, one fragment per year, then graduation.
# ---------------------------------------------------------------------------


def credit_map():
    credit_px = 43.5
    out = ['<div class="cmap">']
    for i, (year, sems) in enumerate(YEARS):
        frag = f'fragment" data-fragment-index="{i + 1}'
        if i in PARTS:
            out.append(f'<div class="cmap-part {frag}">{PARTS[i]}</div>')
        rows = "".join(row_html(s, SEMESTERS[s], credit_px, False) for s in sems)
        out.append(
            f'<div class="cmap-year {frag}"><div class="cmap-ylabel">{year}</div>'
            f'<div class="cmap-rows">{rows}</div></div>'
        )
    note = (
        '<b>Общо 250 кредита</b>'
        '<span>8 семестъра × 30 кр. + 10 кр.; спортът е без кредити</span>'
    )
    out.append(
        '<div class="cmap-year cmap-grad fragment" data-fragment-index="5">'
        '<div class="cmap-ylabel">Накрая</div>'
        f'<div class="cmap-rows">{graduation_row(credit_px, False, note)}</div></div>'
    )
    out.append("</div>")
    return raw("".join(out))


def year_bars(index):
    credit_px = 47.5
    _, sems = YEARS[index]
    rows = "".join(row_html(s, SEMESTERS[s], credit_px, True) for s in sems)
    return raw(f'<div class="cmap big">{rows}</div>')


# ---------------------------------------------------------------------------
# Semester II, from the catalog to one student's program (auto-animate).
# ---------------------------------------------------------------------------

U, G = 158, 8          # card width for a 3-credit course, gap
P = U + G              # one unit of the student's row
RIGHT = 1040           # x of the right-hand shelves (GENB, Bulgarian)
H = 120                # card height
S1, S2, S3 = 226, 414, 602   # shelf card tops
ROW = 824              # student row, steps 0–4
ROW_END = 660          # student row, last step
SEG_TOP = 408          # scheme row, last step

# (code, credits label, title, kind, size, shelf, x, width)
CARDS = [
    ("ADMB041", "3 кр.", "Управленска етика", PROG, "", S1, 0 * P, U),
    ("ADMB834", "3 кр.", "Политики на ЕС", PROG, "", S1, 1 * P, U),
    ("BAEB035", "3 кр.", "Икономическа (бизнес) статистика", PROG, "long", S1, 2 * P, U),
    ("BAEB045", "3 кр.", "Вземане на бизнес решения на базата на данни", PROG, "xlong", S1, 3 * P, U),
    ("BUBB201", "3 кр.", "Принципи на макро­икономиката", PROG, "long", S1, 4 * P, U),
    ("BUBB401", "3 кр.", "Правни анализи", PROG, "", S1, 5 * P, U),
    ("GENB015", "2/2", "Държавно и публично управление", GENB, "long", S1, RIGHT, U),
    ("GENB091", "2/2", "Право, политика, цивилизация", GENB, "long", S1, RIGHT + P, U),
    ("OOLE312", "6 кр.", "Английски език, B1", GEN, "", S2, 0 * (2 * P), 2 * U + G),
    ("OOLE511", "6 кр.", "Английски език, B2", GEN, "", S2, 1 * (2 * P), 2 * U + G),
    ("OOLE221", "6 кр.", "Немски език, A2", GEN, "", S2, 2 * (2 * P), 2 * U + G),
    ("OOOK800", "2/2", "Български език", GEN, "", S2, RIGHT, U),
    ("OOOK805", "2/2", "Бълг. език – академично писане и говорене", GEN, "xlong", S2, RIGHT + P, U),
    ("OOOK051", "3 кр.", "Старогръцка култура", GEN, "", S3, 0 * P, U),
    ("OOOK109", "3 кр.", "Що е фотография", GEN, "", S3, 1 * P, U),
    ("OOOK064", "3 кр.", "Астрономия и астрофизика", GEN, "", S3, 2 * P, U),
    ("OOOK159", "3 кр.", "Между­културна комуникация", GEN, "", S3, 3 * P, U),
    ("OOOK233", "3 кр.", "История на музиката", GEN, "", S3, 4 * P, U),
    ("OOOK287", "3 кр.", "Геология за всеки", GEN, "", S3, 5 * P, U),
    ("OOOK325", "3 кр.", "Ораторско майсторство", GEN, "long", S3, 6 * P, U),
    ("OOOK107", "3 кр.", "Съкровищата на България", GEN, "long", S3, 7 * P, U),
]

# Slots in the student's row: (unit, units wide, kind, label)
SLOTS = [(u, 1, PROG, "курс от програмата<br><b>3 кр.</b>") for u in range(5)] + [
    (5, 1, GENB, "GENB<br><b>2/2</b>"),
    (6, 2, GEN, "чужд език<br><b>6 кр.</b>"),
    (8, 1, GEN, "български език<br><b>2/2</b>"),
    (9, 1, GEN, "курс за знания<br><b>3 кр.</b>"),
]

# Which card lands in which unit, and at which step.
PICKS = {
    1: {"ADMB041": 0, "ADMB834": 1, "BAEB035": 2, "BUBB201": 3, "BUBB401": 4},
    2: {"GENB015": 5, "OOOK800": 8},
    3: {"OOLE511": 6},
    4: {"OOOK064": 9},
}
# Cards greyed out at a step: the ones the student passed over.
PASSED = {
    1: ["BAEB045"],
    2: ["GENB091", "OOOK805"],
    3: ["OOLE312", "OOLE221"],
    4: ["OOOK051", "OOOK109", "OOOK159", "OOOK233", "OOOK287", "OOOK325", "OOOK107"],
}
CONTINUES = ["GENB015", "OOOK800"]   # two-semester courses carried over from I
COUNTER = ["0 / 30 кр.", "15 / 30 кр.", "21 / 30 кр.", "27 / 30 кр.", "30 / 30 кр.", "30 / 30 кр."]

TITLES = [
    ("title-0", "II семестър: от каталога към програмата на студента"),
    ("title-0", "II семестър: от каталога към програмата на студента"),
    ("title-0", "II семестър: от каталога към програмата на студента"),
    ("title-0", "II семестър: от каталога към програмата на студента"),
    ("title-0", "II семестър: от каталога към програмата на студента"),
    ("title-1", "Схемата казва колко, каталогът казва кои"),
]
CAPTIONS = [
    "Каталогът предлага курсове; програмната схема казва колко и от какъв вид. Общо 30 кредита.",
    "1. Курсове от програмата: 5 от предложените 6, общо 15 кредита.",
    "2. Двусеместриалните курсове продължават от I семестър: GENB и български език.",
    "3. Чужд език според нивото: 6 кредита.",
    "4. Един курс за знания, по правило от друга област: 3 кредита. Семестърът е пълен.",
    "Същият ред като II семестър в картата, но с курсовете на един студент.",
]
SHELVES = [
    ("sh-prog", 0, S1 - 34, "Курсове от програмата: избират се 5 от 6"),
    ("sh-genb", RIGHT, S1 - 34, "GENB: продължава от I семестър"),
    ("sh-fl", 0, S2 - 34, "Чужд език според нивото (6 езика, A1–C2)"),
    ("sh-bg", RIGHT, S2 - 34, "Български език: продължава"),
    ("sh-kn", 0, S3 - 34, "Курсове за знания: 1 по избор (77 в каталога)"),
]
SEGMENTS = [
    (0, 5, PROG, "Курсове от програмата", "15 кр., 5 от 6 курса"),
    (5, 1, GENB, "GENB", "1 от 2"),
    (6, 2, GEN, "Чужд език", "6 кр."),
    (8, 1, GEN, "Бълг. език", "3 кр."),
    (9, 1, GEN, "Знания", "3 кр."),
]


def unit_x(unit):
    return unit * P


def card_html(card, left, top, extra=""):
    code, credits, title, kind, size, _, _, width = card
    classes = " ".join(x for x in ("c", kind, size, extra) if x)
    return (
        f'<div class="{classes}" data-id="{code}" style="left:{left}px;top:{top}px;width:{width}px;">'
        f'<div class="code">{code} · {credits}</div><div class="t">{escape(title)}</div></div>'
    )


def anim_step(step):
    last = step == 5
    row_top = ROW_END if last else ROW
    placed = {}
    for s in range(1, min(step, 4) + 1):
        placed.update(PICKS[s])
    moving = set(PICKS.get(step, {}))
    passed = {c for s in range(1, min(step, 4) + 1) for c in PASSED[s]}

    items = []
    title_id, title = TITLES[step]
    items.append('<div class="a-eyebrow" data-id="eyebrow">Пример</div>')
    items.append(f'<div class="a-title" data-id="{title_id}">{escape(title)}</div>')
    items.append(f'<div class="a-cap" data-id="cap-{step}">{escape(CAPTIONS[step])}</div>')

    gone = " gone" if last else ""
    for sid, left, top, text in SHELVES:
        items.append(f'<div class="shelf-h{gone}" data-id="{sid}" style="left:{left}px;top:{top}px;">{escape(text)}</div>')
    items.append(f'<div class="more{gone}" data-id="more" style="left:{8 * P + 16}px;top:{S3 + 38}px;">+ още 69</div>')

    for unit, span, kind, label in SLOTS:
        width = span * U + (span - 1) * G
        items.append(
            f'<div class="slot {kind}{gone}" data-id="slot-{unit}" '
            f'style="left:{unit_x(unit)}px;top:{ROW}px;width:{width}px;">{label}</div>'
        )

    for card in CARDS:
        code, _, _, _, _, shelf_top, shelf_x, _ = card
        if code in placed:
            extra = "moving" if code in moving else ""
            items.append(card_html(card, unit_x(placed[code]), row_top, extra))
        else:
            extra = "off gone" if (last and code in passed) else "off" if code in passed else ("gone" if last else "")
            items.append(card_html(card, shelf_x, shelf_top, extra))

    if step >= 1:
        cls = "badge gone" if last else "badge"
        items.append(f'<div class="{cls}" data-id="b-BAEB045" style="left:{3 * P}px;top:{S1 + H + 4}px;">не е избран (5 от 6)</div>')
    if step >= 2:
        for code in CONTINUES:
            items.append(
                f'<div class="badge cont" data-id="b-{code}" '
                f'style="left:{unit_x(placed[code])}px;top:{row_top - 30}px;">от I семестър</div>'
            )

    row_label = "Програма на студента: кои курсове" if last else "Програма на студента"
    items.append(f'<div class="row-h" data-id="rowlabel" style="left:0px;top:{row_top - 68}px;">{row_label}</div>')
    full = " full" if step >= 4 else ""
    items.append(f'<div class="counter{full}" data-id="counter" style="top:{row_top - 100}px;">{COUNTER[step]}</div>')

    if last:
        items.append(f'<div class="row-h" data-id="schemalabel" style="left:0px;top:{SEG_TOP - 36}px;">Програмна схема: колко и от какъв вид</div>')
        for i, (unit, span, kind, name, sub) in enumerate(SEGMENTS):
            width = span * U + (span - 1) * G
            items.append(
                f'<div class="seg {kind}" data-id="seg-{i}" style="left:{unit_x(unit)}px;top:{SEG_TOP}px;width:{width}px;">'
                f'<b>{escape(name)}</b><span>{escape(sub)}</span></div>'
            )

    return '<div class="anim">' + "".join(items) + "</div>"


def semester_2():
    out = []
    for step in range(6):
        out.append(f"## {{#s2-{step} .anim-slide auto-animate=true}}\n")
        out.append(raw(anim_step(step)))
        out.append("\n")
    return "".join(out)


def main():
    OUT.mkdir(exist_ok=True)
    header = "<!-- Generated by tools/program_slides.py; edit the data there, not here. -->\n\n"
    files = {"karta.qmd": credit_map(), "semestar-2.qmd": semester_2()}
    for i in range(4):
        files[f"bars-{i + 1}.qmd"] = year_bars(i)
    for name, content in files.items():
        (OUT / name).write_text(header + content, encoding="utf-8")
        print(f"wrote _program/{name}")


if __name__ == "__main__":
    main()
