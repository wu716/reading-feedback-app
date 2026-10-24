"""Live per-book projection into the existing ledger, never a second time total."""
import hashlib
import json
from app.project_models import ReaderReadingDay, ReaderBinding


def source_days(db, user_id, start, end):
    bindings = {b.id: b for b in db.query(ReaderBinding).filter_by(user_id=user_id)}
    result = {}
    for row in db.query(ReaderReadingDay).filter(ReaderReadingDay.user_id == user_id,
            ReaderReadingDay.record_date >= start, ReaderReadingDay.record_date <= end):
        b = bindings[row.binding_id]
        entries = result.setdefault(row.record_date, [])
        for book in json.loads(row.books_json):
            key = f"reader_{b.id}_" + hashlib.sha256(book["source_book_id"].encode()).hexdigest()[:32]
            entries.append({"id": key, "reader_book_key": key, "title": book["title"][:200], "seconds": book["active_seconds"],
                "reader_source": {"instance_id": b.source_instance_id, "book_id": book["source_book_id"],
                    "label": b.source_label, "revision": row.revision, "active_binding": b.active,
                    "title": book["title"], "document_deleted": book.get("document_deleted", False)}})
    return result


def merge(data, incoming, activity_cls):
    incoming = {a["reader_book_key"]: a for a in incoming}
    existing_keys = set()
    for item in data["activities"]:
        key = item.get("reader_book_key")
        if not key:
            continue
        existing_keys.add(key)
        source = incoming.get(key)
        item["seconds"] = source["seconds"] if source else 0
        item["source_missing"] = source is None
        if source:
            item["title"] = source["title"]
            item["reader_source"] = source["reader_source"]
    for key, source in incoming.items():
        if key not in existing_keys:
            data["activities"].append({**activity_cls(id=key, category="reading", reader_book_key=key,
                title=source["title"], seconds=source["seconds"]).model_dump(),
                "reader_source": source["reader_source"], "source_missing": False})
