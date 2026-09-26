import asyncio
from unittest import TestCase

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Ebook, EbookChapter, EbookNote, User
from app.routers.ebooks import list_all_book_notes, router


class EbookNoteCollectionTests(TestCase):
    def test_collection_route_precedes_book_id_route(self):
        paths = [route.path for route in router.routes]
        self.assertLess(paths.index('/ebooks/notes'), paths.index('/ebooks/{book_id}'))

    def test_collection_includes_source_and_excludes_other_users(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            owner = User(email="reader@example.test", name="读者", password_hash="test")
            other = User(email="other@example.test", name="其他人", password_hash="test")
            db.add_all([owner, other])
            db.flush()
            for user, title, type_name, relation in [
                (owner, "The Half Second", "concept", None),
                (owner, "Another Book", "relation", "causation"),
                (other, "Private Book", "process", None),
            ]:
                book = Ebook(user_id=user.id, title=title, original_filename="test.epub", storage_path="unused", file_size=1, chapter_count=1)
                db.add(book)
                db.flush()
                chapter = EbookChapter(ebook_id=book.id, chapter_index=0, title="First chapter", href="chapter.xhtml", text_content="Original quote")
                db.add(chapter)
                db.flush()
                db.add(EbookNote(user_id=user.id, ebook_id=book.id, chapter_id=chapter.id, selected_text="Original quote", note_text="My thought", thought_type=type_name, relation_type=relation))
            db.commit()

            items = asyncio.run(list_all_book_notes(current_user=owner, db=db))["items"]
            self.assertEqual({item["book_title"] for item in items}, {"The Half Second", "Another Book"})
            self.assertTrue(all(item["book_id"] and item["chapter_id"] for item in items))
            self.assertEqual(next(item for item in items if item["thought_type"] == "relation")["relation_type"], "causation")
        engine.dispose()
