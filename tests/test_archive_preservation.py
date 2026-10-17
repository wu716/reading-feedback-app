import csv
import io
import zipfile
from datetime import date
from unittest import TestCase

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.backup import build_backup_zip
from app.database import Base
from app.models import DailyTodo, ReadingEntry, User
from app.project_models import Goal


class ArchivePreservationTests(TestCase):
    def test_current_backup_keeps_protected_data_without_retired_exports(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            user = User(email="reader@example.test", name="读者", password_hash="test")
            db.add(user)
            db.flush()
            db.add(ReadingEntry(user_id=user.id, content="历史阅读", entry_date=date(2026, 1, 1)))
            db.add(DailyTodo(user_id=user.id, todo_date=date(2026, 1, 1), text="保留待办"))
            db.add(Goal(user_id=user.id, title="近期目标"))
            db.commit()
            raw = build_backup_zip(db)
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                self.assertIn("uploads", archive.read("README.txt").decode("utf-8"))
                for filename, expected in [("todos.csv", "保留待办"),
                                           ("goals.csv", "近期目标")]:
                    rows = list(csv.reader(io.StringIO(archive.read(filename).decode("utf-8-sig"))))
                    self.assertIn(expected, rows[1])
                self.assertNotIn("readings.csv", archive.namelist())
                self.assertNotIn("ebooks.csv", archive.namelist())
        engine.dispose()
