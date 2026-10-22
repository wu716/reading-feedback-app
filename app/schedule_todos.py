"""Keep old todo/reminder clients attached to the canonical schedule task.

The original todo and reminder IDs survive. Text is never used as identity.
Callers commit the task and reminder changes in the same transaction.
"""
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import DailyTask, DailyTodo, User


def task_for_todo(db: Session, todo: DailyTodo) -> DailyTask | None:
    return db.query(DailyTask).filter(DailyTask.user_id == todo.user_id,
                                     DailyTask.legacy_todo_id == todo.id).first()


def attach_todo(db: Session, todo: DailyTodo) -> DailyTask:
    db.query(User).filter(User.id == todo.user_id).with_for_update().first()
    task = task_for_todo(db, todo)
    if task is None:
        order = db.query(func.max(DailyTask.sort_order)).filter(
            DailyTask.user_id == todo.user_id, DailyTask.task_date == todo.todo_date).scalar()
        task = DailyTask(user_id=todo.user_id, legacy_todo_id=todo.id,
                         task_date=todo.todo_date, text=todo.text, completed=todo.completed,
                         sort_order=(order or 0) + 1, flow_order=(order or 0) + 1,
                         created_at=todo.created_at, deleted_at=todo.deleted_at)
        db.add(task)
        db.flush()
    return task


def import_day_todos(db: Session, user_id: int, day) -> None:
    db.query(User).filter(User.id == user_id).with_for_update().first()
    rows = db.query(DailyTodo).filter(DailyTodo.user_id == user_id,
        DailyTodo.todo_date == day, DailyTodo.deleted_at.is_(None)).order_by(DailyTodo.id).all()
    for todo in rows:
        attach_todo(db, todo)


def sync_task_reminder(db: Session, task: DailyTask, *, remind_time=...) -> DailyTodo | None:
    todo = db.query(DailyTodo).filter(DailyTodo.id == task.legacy_todo_id,
                                     DailyTodo.user_id == task.user_id).first() if task.legacy_todo_id else None
    if todo is None and remind_time is not ... and remind_time:
        todo = DailyTodo(user_id=task.user_id, text=task.text, completed=task.completed,
                         todo_date=task.task_date)
        db.add(todo)
        db.flush()
        task.legacy_todo_id = todo.id
    if todo is not None:
        todo.text, todo.completed, todo.deleted_at = task.text, task.completed, task.deleted_at
        if remind_time is not ...:
            if todo.remind_time != remind_time:
                todo.reminded_at = None
            todo.remind_time = remind_time
    return todo
