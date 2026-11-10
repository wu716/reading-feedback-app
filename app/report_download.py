"""Readable, account-scoped exports of an already saved report snapshot."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path


PERIODS = {"day": "日报", "week": "周报", "month": "月报", "quarter": "季报", "year": "年报"}
ACTIVITIES = {"reading": "读书", "fitness": "运动", "friends": "帮朋友", "family": "陪家人",
              "investment": "定投", "writing": "写作", "work": "工作", "relaxation": "放松"}
MEALS = {"breakfast": "早饭", "lunch": "午饭", "dinner": "晚饭", "snack": "加餐"}


def readable_lines(report: dict, revision: int) -> list[str]:
    day = report.get("period") == "day"
    lines = [f"书然{PERIODS.get(report.get('period'), '报告')}",
             f"日期：{report.get('start', '')}" + ("" if day else f" 至 {report.get('effective_end') or report.get('end', '')}"),
             f"保存版本：{revision}", "", "这份内容来自服务器已保存的报告。未核对和未填写不代表零投入或零消费。", ""]
    elapsed = report.get("elapsed_days", 0)
    lines += ["一、记录状态", f"活动已核对：{report.get('day_confirmed_days', 0)}/{elapsed} 天",
              f"注意力已核对：{report.get('attention_confirmed_days', 0)}/{elapsed} 天",
              f"消费已核对：{report.get('expense_confirmed_days', 0)}/{elapsed} 天", ""]
    lines.append("二、投入与生活记录")
    totals = report.get("total_seconds") or {}
    counts = report.get("counts") or {}
    for key, name in ACTIVITIES.items():
        if key == "investment":
            lines.append(f"{name}：{report.get('investment_cents', 0) / 100:.2f} 元（已记录金额）")
        elif counts.get(key) or (report.get("category_confirmed_days") or {}).get(key):
            lines.append(f"{name}：{round(totals.get(key, 0) / 60)} 分钟，{counts.get(key, 0)} 条记录")
        else:
            lines.append(f"{name}：未填写或未核对")
    if report.get("attention_confirmed_days") or report.get("attention_by_name"):
        lines.append(f"注意力浪费：{report.get('attention_waste_minutes', 0)} 分钟（已记录）")
        for name, minutes in (report.get("attention_by_name") or {}).items():
            lines.append(f"  {name}：{minutes} 分钟")
    else:
        lines.append("注意力浪费：未填写或未核对")
    if report.get("expense_record_count") or report.get("expense_confirmed_days"):
        lines.append(f"消费净支出：{report.get('money_cents', 0) / 100:.2f} 元（已记录，退款已扣除）")
    else:
        lines.append("消费：未填写或未核对")
    if report.get("premium_locked") and not report.get("personal_details_included"):
        lines.append("活动、饮食与消费明细：当前报告仅展示可查看的汇总。")
    else:
        for meal in report.get("meals") or []:
            lines.append(f"饮食 · {MEALS.get(meal.get('type'), '其他')}：{meal.get('text') or '未填写内容'}；照片 {len(meal.get('photo_ids') or [])} 张")
        for expense in report.get("expenses") or []:
            category = (report.get("expense_category_names") or {}).get(expense.get("category"), expense.get("category", "未分类"))
            sign = "退款" if expense.get("kind") == "refund" else "消费"
            lines.append(f"{sign} · {category}：{expense.get('amount_cents', 0) / 100:.2f} 元；{expense.get('note') or '未填写说明'}；照片 {len(expense.get('photo_ids') or [])} 张")
        for activity in report.get("activities") or []:
            lines.append(f"活动 · {activity.get('title') or '未填写名称'}：{round((activity.get('seconds') or 0) / 60)} 分钟；{activity.get('note') or '未填写说明'}")
    if day:
        lines += ["", "三、今日任务与核心任务"]
        if "daily_tasks" not in report:
            lines.append("这一历史报告版本未收录日程任务。")
        elif not report["daily_tasks"]:
            lines.append("当前报告没有已保存的日程任务。")
        for task in report.get("daily_tasks") or []:
            name = task.get("title") or "未命名任务"
            lines.append(f"任务：{name}；日程状态：{'已完成' if task.get('completed') else '未完成'}")
            lines.append(f"  预期结果：{task.get('expected_result') or '未填写'}；完成依据：{task.get('completion_basis') or '未填写'}")
            if task.get("core_selected"):
                state = {True: "已完成", False: "未完成", None: "待核对"}[task.get("core_review_completed")]
                lines.append(f"  今日核心任务：{state}；原因：{task.get('core_review_reason') or '未填写（选填）'}")
        lines += ["", "四、实际结果与当日反馈"]
        practice = report.get("practice") or {}
        names = {task.get("id"): task.get("title") for task in report.get("daily_tasks") or []}
        feedback = practice.get("feedback") or []
        if not feedback:
            lines.append("没有已保存的任务实际结果反馈。")
        for item in feedback:
            title = names.get(item.get("task_id")) if item.get("kind") == "daily" else None
            lines.append(f"任务：{title or '项目任务或历史任务'}；实际结果：{item.get('outcome') or '未填写'}；偏差原因：{item.get('reason') or '未填写'}")
        reflection = (practice.get("reflections") or {}).get(report.get("start"))
        if reflection:
            lines.append(f"当日反思：{reflection.get('reflection') or reflection.get('note') or '已保存，内容见应用内日报'}")
    lines += ["", "五、项目推进" if day else "三、项目推进"]
    projects = report.get("projects") or []
    if not projects:
        lines.append("当前报告没有项目推进记录。")
    for project in projects:
        lines.append(f"项目：{project.get('title') or '未命名'}；实际投入 {round(project.get('actual_seconds', 0) / 60)} 分钟")
        for task in project.get("completed_tasks") or []:
            lines.append(f"  完成任务：{task.get('title') or '未命名'}；结果：{task.get('result') or '未填写'}")
        for update in project.get("updates") or []:
            lines.append(f"  推进：{update.get('title') or '未命名'}；卡点：{update.get('blocker') or '未填写'}；下一步：{update.get('next_step') or '未填写'}")
    lines += ["", "可把这份 TXT 交给自己的 AI，请它基于已记录内容帮助回顾；未填写项请继续保持未知。"]
    return lines


def as_text(report: dict, revision: int) -> str:
    return "\n".join(readable_lines(report, revision)) + "\n"


def as_pdf(report: dict, revision: int) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from xml.sax.saxutils import escape

    candidates = (Path("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"),
                  Path("C:/Windows/Fonts/msyh.ttc"), Path("C:/Windows/Fonts/simsun.ttc"))
    font_path = next((path for path in candidates if path.is_file()), None)
    if font_path is None:
        raise RuntimeError("PDF 中文字体不可用")
    pdfmetrics.registerFont(TTFont("ShuranReport", str(font_path), subfontIndex=0))
    output = BytesIO()
    document = SimpleDocTemplate(output, pagesize=A4, leftMargin=48, rightMargin=48, topMargin=44, bottomMargin=44)
    style = ParagraphStyle("body", fontName="ShuranReport", fontSize=10, leading=17, textColor=colors.HexColor("#263c4a"), wordWrap="CJK")
    title = ParagraphStyle("title", parent=style, fontSize=17, leading=24, spaceAfter=8)
    section = ParagraphStyle("section", parent=style, fontSize=12, leading=20, spaceBefore=12)
    story = []
    for index, line in enumerate(readable_lines(report, revision)):
        if not line:
            story.append(Spacer(1, 7))
        else:
            chosen = title if index == 0 else section if line[:2] in ("一、", "二、", "三、", "四、", "五、") else style
            story.append(Paragraph(escape(line), chosen))
    document.build(story)
    return output.getvalue()
