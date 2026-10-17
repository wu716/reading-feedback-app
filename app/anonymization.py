"""Keep a minimal anonymous account deletion marker for historical counts."""
import hashlib
import json
from datetime import datetime

from sqlalchemy.orm import Session

from app.models import AnonymizedData, User


def anonymize_user_data_on_deletion(db: Session, user_id: int) -> None:
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        return
    anonymous_id = hashlib.sha256(f"{user_id}_reading_feedback_app_salt_2024".encode()).hexdigest()[:16]
    marker = AnonymizedData(
        original_user_id=user_id,
        data_type="user_profile",
        anonymized_data=json.dumps({
            "anonymous_id": anonymous_id,
            "anonymized_at": datetime.utcnow().isoformat(),
            "data_type": "user_profile",
        }),
    )
    db.add(marker)
    db.flush()
