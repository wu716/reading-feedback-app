# -*- coding: utf-8 -*-
"""Generate software-copyright deposit PDFs for 书然阅读实践反馈软件 V1.3.6."""

from __future__ import annotations

import re
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = Path(__file__).resolve().parent
SOFTWARE_NAME = "书然阅读实践反馈软件"
VERSION = "V1.3.6"
HEADER = f"{SOFTWARE_NAME} {VERSION}"
LINES_PER_PAGE = 50
FRONT_PAGES = 30
BACK_PAGES = 30
WRAP_WIDTH = 88

FONT_CANDIDATES = [
    (r"C:\Windows\Fonts\simsun.ttc", 0),
    (r"C:\Windows\Fonts\simsun.ttf", None),
    (r"C:\Windows\Fonts\msyh.ttc", 0),
]


def register_font() -> str:
    last_error = None
    for path, subfont in FONT_CANDIDATES:
        font_path = Path(path)
        if not font_path.exists():
            continue
        try:
            if subfont is None:
                pdfmetrics.registerFont(TTFont("Ruanzhu", str(font_path)))
            else:
                pdfmetrics.registerFont(TTFont("Ruanzhu", str(font_path), subfontIndex=subfont))
            return "Ruanzhu"
        except Exception as exc:  # noqa: BLE001
            last_error = exc
    raise RuntimeError(f"未找到可用中文字体: {last_error}")


def display_width(text: str) -> int:
    width = 0
    for char in text:
        width += 2 if ord(char) > 127 else 1
    return width


def wrap_line(text: str, max_width: int = WRAP_WIDTH) -> list[str]:
    text = text.replace("\t", "    ").replace("\r", "").rstrip()
    if text == "":
        return [""]
    lines: list[str] = []
    current = ""
    current_width = 0
    for char in text:
        char_width = 2 if ord(char) > 127 else 1
        if current_width + char_width > max_width and current:
            lines.append(current)
            current = char
            current_width = char_width
        else:
            current += char
            current_width += char_width
    if current:
        lines.append(current)
    return lines


def collect_source_files() -> list[Path]:
    files: list[Path] = []
    main_py = ROOT / "main.py"
    if main_py.is_file():
        files.append(main_py)

    app_dir = ROOT / "app"
    if app_dir.is_dir():
        files.extend(
            sorted(
                p
                for p in app_dir.rglob("*.py")
                if "__pycache__" not in p.parts and p.name != "__init__.py"
            )
        )

    static_dir = ROOT / "static"
    if static_dir.is_dir():
        files.extend(sorted(static_dir.rglob("*.js")))

    java_dir = ROOT / "mobile" / "android" / "app" / "src" / "main" / "java"
    if java_dir.is_dir():
        files.extend(sorted(java_dir.rglob("*.java")))

    if static_dir.is_dir():
        files.extend(sorted(static_dir.rglob("*.html")))

    unique: list[Path] = []
    seen: set[Path] = set()
    for path in files:
        resolved = path.resolve()
        if resolved in seen or not path.is_file():
            continue
        seen.add(resolved)
        unique.append(path)
    return unique


def collapse_blank_lines(lines: list[str]) -> list[str]:
    result: list[str] = []
    blank = False
    for line in lines:
        if line.strip() == "":
            if not blank:
                result.append("")
            blank = True
        else:
            result.append(line)
            blank = False
    return result


def build_source_lines() -> list[str]:
    lines: list[str] = []
    for path in collect_source_files():
        rel = path.relative_to(ROOT).as_posix()
        header = f"# ===== {rel} ====="
        lines.extend(wrap_line(header))
        text = path.read_text(encoding="utf-8", errors="replace")
        file_lines: list[str] = []
        for raw in text.splitlines():
            file_lines.extend(wrap_line(raw))
        lines.extend(collapse_blank_lines(file_lines))
        if not lines or lines[-1] != "":
            lines.append("")
    return collapse_blank_lines(lines)


def paginate(lines: list[str], lines_per_page: int = LINES_PER_PAGE) -> list[list[str]]:
    pages: list[list[str]] = []
    for index in range(0, len(lines), lines_per_page):
        chunk = lines[index : index + lines_per_page]
        if len(chunk) < lines_per_page:
            chunk = chunk + [""] * (lines_per_page - len(chunk))
        pages.append(chunk)
    return pages


def select_deposit_pages(pages: list[list[str]]) -> list[list[str]]:
    if len(pages) <= FRONT_PAGES + BACK_PAGES:
        return pages
    return pages[:FRONT_PAGES] + pages[-BACK_PAGES:]


def draw_header_footer(pdf: canvas.Canvas, page_no: int, total: int, font_name: str) -> None:
    width, height = A4
    pdf.setFont(font_name, 9)
    pdf.drawCentredString(width / 2, height - 12 * mm, HEADER)
    pdf.setLineWidth(0.4)
    pdf.line(18 * mm, height - 14 * mm, width - 18 * mm, height - 14 * mm)
    pdf.line(18 * mm, 14 * mm, width - 18 * mm, 14 * mm)
    pdf.setFont(font_name, 9)
    pdf.drawCentredString(width / 2, 8 * mm, f"{page_no} / {total}")


def write_source_pdf(pages: list[list[str]], output: Path, font_name: str) -> None:
    width, height = A4
    top = height - 20 * mm
    left = 16 * mm
    line_height = 5.0 * mm
    pdf = canvas.Canvas(str(output), pagesize=A4)
    total = len(pages)
    for page_no, page_lines in enumerate(pages, start=1):
        draw_header_footer(pdf, page_no, total, font_name)
        pdf.setFont(font_name, 8)
        y = top
        for line in page_lines[:LINES_PER_PAGE]:
            pdf.drawString(left, y, line[:200])
            y -= line_height
        pdf.showPage()
    pdf.save()


def escape_xml(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def inline_markdown(text: str) -> str:
    text = escape_xml(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"`(.+?)`", r"<font face='Ruanzhu'>\1</font>", text)
    return text


def parse_manual(md_path: Path) -> list:
    styles = {
        "h1": ParagraphStyle(
            "h1",
            fontName="Ruanzhu",
            fontSize=16,
            leading=24,
            spaceBefore=8,
            spaceAfter=12,
            alignment=1,
        ),
        "h2": ParagraphStyle(
            "h2",
            fontName="Ruanzhu",
            fontSize=13,
            leading=20,
            spaceBefore=12,
            spaceAfter=8,
        ),
        "h3": ParagraphStyle(
            "h3",
            fontName="Ruanzhu",
            fontSize=11,
            leading=18,
            spaceBefore=8,
            spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "body",
            fontName="Ruanzhu",
            fontSize=10.5,
            leading=18,
            firstLineIndent=22,
            spaceAfter=6,
        ),
        "li": ParagraphStyle(
            "li",
            fontName="Ruanzhu",
            fontSize=10.5,
            leading=18,
            leftIndent=18,
            spaceAfter=3,
        ),
    }

    story: list = []
    for raw in md_path.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        if not line:
            story.append(Spacer(1, 4))
            continue
        if line.startswith("# "):
            story.append(Paragraph(inline_markdown(line[2:]), styles["h1"]))
        elif line.startswith("## "):
            story.append(Paragraph(inline_markdown(line[3:]), styles["h2"]))
        elif line.startswith("### "):
            story.append(Paragraph(inline_markdown(line[4:]), styles["h3"]))
        elif re.match(r"^\d+\.\s+", line):
            story.append(Paragraph(inline_markdown(line), styles["li"]))
        elif line.startswith("- "):
            story.append(Paragraph(inline_markdown("· " + line[2:]), styles["li"]))
        else:
            story.append(Paragraph(inline_markdown(line), styles["body"]))
    return story


def write_manual_pdf(md_path: Path, output: Path, font_name: str) -> int:
    def on_page(pdf: canvas.Canvas, doc) -> None:  # noqa: ARG001
        width, height = A4
        pdf.setFont(font_name, 9)
        pdf.drawCentredString(width / 2, height - 12 * mm, HEADER)
        pdf.setLineWidth(0.4)
        pdf.line(18 * mm, height - 14 * mm, width - 18 * mm, height - 14 * mm)
        pdf.line(18 * mm, 14 * mm, width - 18 * mm, 14 * mm)
        pdf.setFont(font_name, 9)
        pdf.drawCentredString(width / 2, 8 * mm, str(doc.page))

    doc = SimpleDocTemplate(
        str(output),
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=18 * mm,
        title=f"{SOFTWARE_NAME} {VERSION} 软件说明书",
        author=SOFTWARE_NAME,
    )
    story = parse_manual(md_path)
    # Keep a trailing page marker so short manuals still look complete.
    story.append(Spacer(1, 12))
    story.append(
        Paragraph(
            inline_markdown(f"（全文完。{SOFTWARE_NAME} {VERSION}）"),
            ParagraphStyle("end", fontName=font_name, fontSize=10.5, leading=18, alignment=1),
        )
    )
    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    return doc.page


def main() -> None:
    font_name = register_font()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    source_lines = build_source_lines()
    all_pages = paginate(source_lines)
    deposit_pages = select_deposit_pages(all_pages)
    source_pdf = OUT_DIR / f"{SOFTWARE_NAME}_{VERSION}_源程序鉴别材料.pdf"
    write_source_pdf(deposit_pages, source_pdf, font_name)

    manual_md = OUT_DIR / "软件说明书.md"
    manual_pdf = OUT_DIR / f"{SOFTWARE_NAME}_{VERSION}_操作说明书.pdf"
    manual_pages = write_manual_pdf(manual_md, manual_pdf, font_name)

    print(f"source_files={len(collect_source_files())}")
    print(f"source_lines={len(source_lines)}")
    print(f"source_total_pages={len(all_pages)}")
    print(f"source_deposit_pages={len(deposit_pages)}")
    print(f"source_pdf={source_pdf}")
    print(f"manual_pages={manual_pages}")
    print(f"manual_pdf={manual_pdf}")


if __name__ == "__main__":
    main()
