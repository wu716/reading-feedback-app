"""轻量 EPUB 阅读闭环：上传、解析章节、记录读书想法、生成行动项。"""

import html
import json
import os
import posixpath
import re
import uuid
import zipfile
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote
from xml.etree import ElementTree as ET

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.ai_quota import enforce_ai_quota
from app.ai_service import AIExtractionError, AIValidationError, extract_actions_from_notes
from app.auth import get_current_active_user
from app.database import get_db
from app.models import Action, Ebook, EbookChapter, EbookNote, User

router = APIRouter(prefix="/ebooks", tags=["EPUB阅读"])

MAX_BOOK_BYTES = 120 * 1024 * 1024
MAX_USER_BYTES = 500 * 1024 * 1024
MAX_CHAPTER_TEXT = 2_000_000
BOOK_ROOT = Path("uploads") / "ebooks"


class NoteCreate(BaseModel):
    chapter_id: int
    selected_text: str = Field(..., min_length=1, max_length=10_000)
    note_text: str = Field(..., min_length=1, max_length=10_000)


class ActionFromNote(BaseModel):
    chapter_id: int
    selected_text: str = Field(..., min_length=1, max_length=10_000)
    note_text: str = Field(..., min_length=1, max_length=10_000)


class TextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.title = ""
        self.in_title = False

    def handle_starttag(self, tag, attrs):
        if tag.lower() in {"br", "p", "div", "li", "h1", "h2", "h3", "h4", "section"}:
            self.parts.append("\n")
        if tag.lower() == "title":
            self.in_title = True

    def handle_endtag(self, tag):
        if tag.lower() == "title":
            self.in_title = False
        if tag.lower() in {"p", "div", "li", "h1", "h2", "h3", "h4", "section"}:
            self.parts.append("\n")

    def handle_data(self, data):
        value = html.unescape(data).strip()
        if not value:
            return
        if self.in_title and not self.title:
            self.title = value
        self.parts.append(value)

    @property
    def text(self):
        return re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]+", " ", " ".join(self.parts))).strip()


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _find(root, name):
    return [node for node in root.iter() if _local_name(node.tag) == name]


def _parse_epub(path: Path):
    try:
        with zipfile.ZipFile(path) as book:
            names = set(book.namelist())
            if "mimetype" not in names or book.read("mimetype").decode("utf-8", "ignore").strip() != "application/epub+zip":
                raise ValueError("文件不是有效的 EPUB")
            container = ET.fromstring(book.read("META-INF/container.xml"))
            rootfile = next((x for x in _find(container, "rootfile") if x.attrib.get("full-path")), None)
            if rootfile is None:
                raise ValueError("EPUB 缺少目录文件")
            opf_path = rootfile.attrib["full-path"]
            opf_dir = posixpath.dirname(opf_path)
            opf = ET.fromstring(book.read(opf_path))
            metadata = _find(opf, "title")
            title = (metadata[0].text or "").strip() if metadata else ""
            manifest = {}
            for item in _find(opf, "item"):
                item_id = item.attrib.get("id")
                href = item.attrib.get("href")
                media = item.attrib.get("media-type", "")
                if item_id and href and ("html" in media or "xhtml" in media):
                    manifest[item_id] = posixpath.normpath(posixpath.join(opf_dir, unquote(href)))
            spine = []
            for itemref in _find(opf, "itemref"):
                href = manifest.get(itemref.attrib.get("idref"))
                if href:
                    spine.append(href)
            chapters = []
            for index, href in enumerate(spine):
                if href not in names:
                    continue
                parser = TextParser()
                parser.feed(book.read(href).decode("utf-8", "replace"))
                text = parser.text[:MAX_CHAPTER_TEXT]
                if text:
                    chapters.append({"chapter_index": len(chapters), "title": parser.title or f"第 {index + 1} 章", "href": href, "text_content": text})
            if not chapters:
                raise ValueError("EPUB 中没有可阅读的章节")
            return title, chapters
    except (KeyError, ET.ParseError, zipfile.BadZipFile) as exc:
        raise ValueError("EPUB 文件结构无法解析") from exc


def _book_response(book: Ebook):
    return {
        "id": book.id,
        "title": book.title,
        "original_filename": book.original_filename,
        "file_size": book.file_size,
        "chapter_count": book.chapter_count,
        "created_at": book.created_at,
        "chapters": [{"id": c.id, "index": c.chapter_index, "title": c.title} for c in book.chapters],
    }


@router.get("")
async def list_books(current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    books = db.query(Ebook).filter(Ebook.user_id == current_user.id).order_by(Ebook.created_at.desc()).all()
    used = sum(int(book.file_size or 0) for book in books)
    return {"items": [_book_response(book) for book in books], "used_bytes": used, "limit_bytes": MAX_USER_BYTES}


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_book(file: UploadFile = File(...), current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    filename = os.path.basename(file.filename or "book.epub")
    if not filename.lower().endswith(".epub"):
        raise HTTPException(400, "目前只支持 EPUB 文件")
    used = sum(int(row[0] or 0) for row in db.query(Ebook.file_size).filter(Ebook.user_id == current_user.id).all())
    if used >= MAX_USER_BYTES:
        raise HTTPException(413, "已达到个人书籍容量上限 500MB")
    target_dir = BOOK_ROOT / str(current_user.id)
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"{uuid.uuid4().hex}.epub"
    size = 0
    try:
        with path.open("wb") as output:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_BOOK_BYTES or used + size > MAX_USER_BYTES:
                    raise HTTPException(413, "单本 EPUB 上限为 120MB，个人总容量上限为 500MB")
                output.write(chunk)
        title, chapters = _parse_epub(path)
        book = Ebook(user_id=current_user.id, title=(title or Path(filename).stem)[:255], original_filename=filename[:255], storage_path=str(path), file_size=size, chapter_count=len(chapters))
        db.add(book)
        db.flush()
        for chapter in chapters:
            db.add(EbookChapter(ebook_id=book.id, **chapter))
        db.commit()
        db.refresh(book)
        return _book_response(book)
    except HTTPException:
        if path.exists(): path.unlink()
        raise
    except ValueError as exc:
        if path.exists(): path.unlink()
        raise HTTPException(422, str(exc))
    except Exception:
        db.rollback()
        if path.exists(): path.unlink()
        raise HTTPException(500, "EPUB 上传失败，请稍后重试")


def _owned_book(db, book_id, user_id):
    book = db.query(Ebook).filter(Ebook.id == book_id, Ebook.user_id == user_id).first()
    if not book:
        raise HTTPException(404, "书籍不存在")
    return book


@router.get("/{book_id}")
async def get_book(book_id: int, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    return _book_response(_owned_book(db, book_id, current_user.id))


@router.get("/{book_id}/chapters/{chapter_id}")
async def get_chapter(book_id: int, chapter_id: int, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    book = _owned_book(db, book_id, current_user.id)
    chapter = db.query(EbookChapter).filter(EbookChapter.id == chapter_id, EbookChapter.ebook_id == book.id).first()
    if not chapter:
        raise HTTPException(404, "章节不存在")
    return {"id": chapter.id, "title": chapter.title, "index": chapter.chapter_index, "text": chapter.text_content}


@router.post("/{book_id}/notes", status_code=status.HTTP_201_CREATED)
async def create_note(book_id: int, payload: NoteCreate, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    book = _owned_book(db, book_id, current_user.id)
    chapter = db.query(EbookChapter).filter(EbookChapter.id == payload.chapter_id, EbookChapter.ebook_id == book.id).first()
    if not chapter:
        raise HTTPException(404, "章节不存在")
    note = EbookNote(user_id=current_user.id, ebook_id=book.id, chapter_id=chapter.id, selected_text=payload.selected_text.strip(), note_text=payload.note_text.strip())
    db.add(note)
    db.commit()
    db.refresh(note)
    return {"id": note.id, "selected_text": note.selected_text, "note_text": note.note_text, "created_at": note.created_at}


@router.post("/{book_id}/action", status_code=status.HTTP_201_CREATED)
async def create_action_from_note(book_id: int, payload: ActionFromNote, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    book = _owned_book(db, book_id, current_user.id)
    chapter = db.query(EbookChapter).filter(EbookChapter.id == payload.chapter_id, EbookChapter.ebook_id == book.id).first()
    if not chapter:
        raise HTTPException(404, "章节不存在")
    enforce_ai_quota(db, current_user, kind="upload-notes")
    content = f"原文：{payload.selected_text.strip()}\n我的想法：{payload.note_text.strip()}\n\n请回答：这段内容如果用于我的生活，具体可以做什么？"
    try:
        extracted = await extract_actions_from_notes(content, book.title)
    except (AIExtractionError, AIValidationError) as exc:
        raise HTTPException(422, f"行动项生成失败：{exc}")
    if not extracted:
        raise HTTPException(422, "这段内容暂时没有生成明确行动，请把想法写得更具体一些")
    item = extracted[0]
    action = Action(user_id=current_user.id, book_title=book.title, source_excerpt=payload.selected_text.strip(), action_text=item.action, tags=json.dumps(item.tags, ensure_ascii=False), frequency=item.frequency.value, duration_type="short_term", target_duration_days=30, target_frequency="daily", start_date=date.today())
    db.add(action)
    db.commit()
    db.refresh(action)
    return {"id": action.id, "action_text": action.action_text, "book_title": action.book_title, "source_excerpt": action.source_excerpt}
