import csv
import io
import zipfile
from datetime import date
from unittest import TestCase

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.backup import build_backup_zip
from app.database import Base
from app.models import Ebook, EbookChapter, EbookNote, ReadingEntry, User
from app.project_models import Goal


class ArchivePreservationTests(TestCase):
    def test_legacy_reading_and_ebook_history_stays_in_backup(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            user = User(email="reader@example.test", name="读者", password_hash="test")
            db.add(user)
            db.flush()
            db.add(ReadingEntry(user_id=user.id, content="历史阅读", entry_date=date(2026, 1, 1)))
            book = Ebook(user_id=user.id, title="旧书", original_filename="old.epub",
                         storage_path="uploads/old.epub", file_size=1, chapter_count=1)
            db.add(book)
            db.flush()
            chapter = EbookChapter(ebook_id=book.id, chapter_index=0, title="第一章",
                                   href="a.xhtml", text_content="原文")
            db.add(chapter)
            db.flush()
            db.add(EbookNote(user_id=user.id, ebook_id=book.id, chapter_id=chapter.id,
                             selected_text="原文", note_text="想法"))
            db.add(Goal(user_id=user.id, title="近期目标"))
            db.commit()
            raw = build_backup_zip(db)
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                self.assertIn("uploads", archive.read("README.txt").decode("utf-8"))
                for filename, expected in [("readings.csv", "历史阅读"),
                                           ("ebooks.csv", "old.epub"),
                                           ("ebook_notes.csv", "想法"),
                                           ("goals.csv", "近期目标")]:
                    rows = list(csv.reader(io.StringIO(archive.read(filename).decode("utf-8-sig"))))
                    self.assertIn(expected, rows[1])
        engine.dispose()
