"""Rebuild editable SVG and ready-to-post PNG campaign cards."""
from pathlib import Path
from xml.sax.saxutils import escape


OUT = Path(__file__).resolve().parent
INK = "#213E52"
MUTED = "#697E81"
RUST = "#A96D50"
PAPER = "#F7F5EF"
LINE = "#D9DDD6"
FONT = "Microsoft YaHei, Noto Sans CJK SC, sans-serif"


def txt(x, y, value, size=36, color=INK, weight=400, spacing=0):
    return (f'<text x="{x}" y="{y}" fill="{color}" font-size="{size}" '
            f'font-weight="{weight}" letter-spacing="{spacing}" font-family="{FONT}">'
            f'{escape(value)}</text>')


def base(width, height, body):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}"><defs><pattern id="dots" width="18" height="18" '
            f'patternUnits="userSpaceOnUse"><circle cx="2" cy="2" r="1" fill="#DCE2DD"/></pattern></defs>'
            f'<rect width="100%" height="100%" fill="{PAPER}"/>'
            f'<rect width="100%" height="100%" fill="url(#dots)" opacity=".42"/>{body}</svg>')


def brand(width, tag):
    return (f'<path d="M76 96h90" stroke="{RUST}" stroke-width="6"/>'
            + txt(76, 158, "书然", 45, INK, 650, 5)
            + txt(width - 78, 150, tag, 24, MUTED, 500, 2).replace(
                f'x="{width - 78}"', f'x="{width - 78}" text-anchor="end"'))


def footer(width, height, label):
    return (f'<path d="M76 {height - 166}H{width - 76}" stroke="{LINE}" stroke-width="3"/>'
            + txt(76, height - 92, label, 28, MUTED)
            + txt(width - 76, height - 92, "SHURAN", 22, RUST, 700, 5).replace(
                f'x="{width - 76}"', f'x="{width - 76}" text-anchor="end"'))


def moments():
    w = h = 1080
    body = brand(w, "给生活一份可回看的答案")
    body += txt(76, 290, "每天都很忙，", 73, INK, 670)
    body += txt(76, 392, "这一周究竟", 73, INK, 670)
    body += txt(76, 494, "走向了哪里？", 73, INK, 670)
    body += f'<path d="M76 527H598" stroke="{RUST}" stroke-width="10" stroke-linecap="round"/>'
    body += txt(77, 608, "记录项目、阅读、运动、消费", 33, MUTED)
    body += txt(77, 662, "再用日报、周报和深度复盘看清方向", 33, MUTED)
    body += f'<rect x="76" y="746" width="928" height="164" rx="22" fill="{INK}"/>'
    body += txt(112, 817, "书然产品群", 38, "#F8F7F1", 650)
    body += txt(112, 872, "先免费体验 · 付费由站长人工开通", 27, "#D4E0DD")
    body += footer(w, h, "私信「复盘」进群")
    return base(w, h, body)


def xhs_shell(tag, lines, subtitle, art):
    w, h = 1080, 1440
    body = brand(w, tag)
    for index, line in enumerate(lines):
        body += txt(76, 332 + 116 * index, line, 81, INK, 700)
    body += f'<path d="M76 706H438" stroke="{RUST}" stroke-width="11" stroke-linecap="round"/>'
    body += txt(76, 795, subtitle, 31, MUTED)
    body += art
    body += footer(w, h, "真实记录 → 分类汇总 → 周期复盘")
    return base(w, h, body)


def week_art():
    art = f'<rect x="76" y="872" width="928" height="352" rx="22" fill="#EDF0E9" stroke="{LINE}" stroke-width="2"/>'
    art += txt(112, 932, "这一周，时间花在哪里", 30, INK, 580)
    rows = [("项目", 540, "#52758B"), ("阅读", 377, "#7D9581"), ("家人与朋友", 256, "#B8876B")]
    for index, (label, width, color) in enumerate(rows):
        y = 1005 + index * 71
        art += txt(112, y + 12, label, 26, MUTED)
        art += f'<rect x="325" y="{y - 13}" width="560" height="29" rx="14" fill="#DCE3DE"/>'
        art += f'<rect x="325" y="{y - 13}" width="{width}" height="29" rx="14" fill="{color}"/>'
    art += txt(880, 1193, "示意", 18, MUTED)
    return art


def spending_art():
    art = f'<rect x="76" y="872" width="928" height="352" rx="22" fill="#EEF0E9" stroke="{LINE}" stroke-width="2"/>'
    art += txt(112, 932, "消费分类 · 净支出", 30, INK, 580)
    rows = [("餐饮", 480, "#B8876B"), ("交通", 300, "#6C8996"), ("购物", 190, "#8C9976")]
    for index, (label, width, color) in enumerate(rows):
        y = 1005 + index * 71
        art += txt(112, y + 12, label, 26, MUTED)
        art += f'<rect x="292" y="{y - 13}" width="590" height="29" rx="14" fill="#DCE3DE"/>'
        art += f'<rect x="292" y="{y - 13}" width="{width}" height="29" rx="14" fill="{color}"/>'
    art += txt(880, 1193, "示意", 18, MUTED)
    return art


def reading_art():
    art = f'<rect x="76" y="872" width="928" height="352" rx="22" fill="#EDF0E9" stroke="{LINE}" stroke-width="2"/>'
    art += txt(112, 932, "阅读主题地图", 30, INK, 580)
    for index, (label, width, color) in enumerate([
        ("心理与成长", 515, "#52758B"), ("文学小说", 345, "#A97B67"), ("社会与历史", 210, "#829579")
    ]):
        y = 1005 + index * 71
        art += txt(112, y + 12, label, 24, MUTED)
        art += f'<rect x="335" y="{y - 13}" width="546" height="29" rx="14" fill="#DCE3DE"/>'
        art += f'<rect x="335" y="{y - 13}" width="{width}" height="29" rx="14" fill="{color}"/>'
    art += txt(880, 1193, "示意", 18, MUTED)
    return art


CARDS = {
    "moments-group": moments(),
    "xhs-weekly-review": xhs_shell("生活复盘 / 01", ["记录了很多，", "为什么还是说不清", "这一周？"], "先把每天具体做过的事放在一起看。", week_art()),
    "xhs-spending": xhs_shell("生活复盘 / 02", ["一周消费摊开后，", "真正花钱的", "是哪一类？"], "看每类花了多少，也看哪些日子没记全。", spending_art()),
    "xhs-reading": xhs_shell("生活复盘 / 03", ["读了不少书，", "你的阅读时间", "流向了哪儿？"], "按书的主题回看，而不是只数读完几本。", reading_art()),
}


def main():
    for name, svg in CARDS.items():
        (OUT / f"{name}.svg").write_text(svg, encoding="utf-8")
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=True,
                executable_path=r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            )
            for name in CARDS:
                size = 1080 if name == "moments-group" else 1440
                page = browser.new_page(viewport={"width": 1080, "height": size}, device_scale_factor=1)
                page.goto((OUT / f"{name}.svg").as_uri())
                page.screenshot(path=str(OUT / f"{name}.png"))
                page.close()
            browser.close()
    except ImportError:
        print("Playwright unavailable; SVG files were generated and remain usable.")


if __name__ == "__main__":
    main()
