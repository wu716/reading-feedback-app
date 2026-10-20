"""Manual UI preview with synthetic, in-memory data only.
Run: python tests/preview_long_term.py (localhost:8766).
This app is never imported by production.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datetime import date, datetime
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app import project_models
from app.database import Base, get_db
from app.auth import get_current_active_user
from app.models import User, TimeLogNode
from app.routers import long_term_details as ledger

root = Path(__file__).resolve().parents[1]
engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Base.metadata.create_all(engine)
with Session(engine) as db:
    user = User(email="preview@example.test", name="演示读者", password_hash="synthetic")
    db.add(user)
    db.commit()
    user_id = user.id
    day = ledger.beijing_today()
    ledger.save_day(ledger.LedgerInput(
        revision=0,
        activities=[
            ledger.Activity(id="book-a", category="reading", title="万物简史", seconds=2700, reading_kind="nonfiction", primary_topic="science", topics=["history"], note="把宏观时间尺度和生活经验联系起来。"),
            ledger.Activity(id="book-b", category="reading", title="故事集", seconds=1800, reading_kind="fiction", primary_topic="literature"),
            ledger.Activity(id="run", category="fitness", title="慢跑", seconds=1800, note="呼吸比昨天更平稳。"),
            ledger.Activity(id="family", category="family", title="陪家人吃晚饭", seconds=3600),
            ledger.Activity(id="write", category="writing", title="本周阅读随笔", seconds=2400, words=800),
            ledger.Activity(id="rest", category="relaxation", title="刷手机", seconds=900, unplanned=True),
            ledger.Activity(id="investment", category="investment", title="示例标的", amount_cents=50000),
        ],
        expenses=[
            ledger.Expense(id="dinner", category="food", amount_cents=16800, activity_id="family", note="晚餐"),
            ledger.Expense(id="book", category="learning", amount_cents=6800, activity_id="book-a", note="购书"),
            ledger.Expense(id="refund", category="shopping", kind="refund", amount_cents=3000, note="退货到账"),
        ], expense_confirmed=True, day_confirmed=True),day=day,user=user,db=db)
    db.add(TimeLogNode(user_id=user.id, log_date=day, logged_at=datetime.now(), label="整理周报", duration_seconds=1200))
    db.commit()

app = FastAPI()
app.include_router(ledger.router, prefix="/api")
app.mount("/static", StaticFiles(directory=root / "static"), name="static")
def session():
    with Session(engine) as db:
        yield db
def current_user():
    with Session(engine) as db:
        return db.get(User,user_id)
app.dependency_overrides[get_db] = session
app.dependency_overrides[get_current_active_user] = current_user

@app.get("/",response_class=HTMLResponse)
def page():
    source=(root/"static/index.html").read_text(encoding="utf-8")
    head=source[source.index("<head>"):source.index("</head>")+7]
    start=source.index('        <section id="long-term"')
    end=source.index('        <section id="time-log"',start)
    section=source[start:end].replace('class="content-section"','class="content-section active"',1)
    return '<!DOCTYPE html><html lang="zh-CN">'+head+"""
    <body><main style="padding:32px 20px;max-width:1300px;margin:auto">"""+section+"""</main>
    <script>
    localStorage.setItem('authToken','synthetic-preview-only');
    async function apiRequest(path,options={}) {
      const response=await fetch(path,{headers:{'Content-Type':'application/json'},...options});
      const data=await response.json();
      if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:JSON.stringify(data.detail));
      return data;
    }
    </script><script src="/static/js/long-term.js"></script>
    <script>document.addEventListener('DOMContentLoaded',()=>loadLongTerm());</script></body></html>"""

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app,host="127.0.0.1",port=8766)

