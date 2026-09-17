# -*- coding: utf-8 -*-
from datetime import date
from types import SimpleNamespace
from unittest import TestCase

from app.habit_due import is_due, suggest_for_day


def action(**kwargs):
    defaults = dict(
        id=1,
        action_text="晨间阅读",
        action_type="habit",
        status="todo",
        deleted_at=None,
        start_date=None,
        end_date=None,
        target_frequency="daily",
        frequency="daily",
        custom_frequency_days=None,
        created_at=None,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def task(**kwargs):
    defaults = dict(action_id=None, text="", task_date=date(2026, 9, 17))
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


class HabitDueTests(TestCase):
    def test_daily_habit_is_due(self):
        self.assertTrue(is_due(action(), date(2026, 9, 17), []))

    def test_already_scheduled_today_is_hidden(self):
        item = action()
        scheduled = [task(action_id=1, text="晨间阅读", task_date=date(2026, 9, 17))]
        self.assertFalse(is_due(item, date(2026, 9, 17), scheduled))
        self.assertEqual(suggest_for_day([item], scheduled, date(2026, 9, 17)), [])

    def test_weekly_habit_only_on_weekend(self):
        item = action(target_frequency="weekly")
        thursday = date(2026, 9, 17)
        saturday = date(2026, 9, 19)
        self.assertFalse(is_due(item, thursday, []))
        self.assertTrue(is_due(item, saturday, []))

    def test_trigger_without_end_date_still_fills_schedule(self):
        item = action(action_type="trigger", target_frequency="daily", end_date=None)
        thursday = date(2026, 9, 17)
        self.assertFalse(is_due(item, thursday, []))
        suggestions = suggest_for_day([item], [], thursday)
        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0].reason, "还未排进今天")
        self.assertEqual(suggestions[0].text, "晨间阅读")

    def test_trigger_with_end_date_is_due_in_window(self):
        item = action(
            action_type="trigger",
            start_date=date(2026, 9, 1),
            end_date=date(2026, 9, 30),
        )
        self.assertTrue(is_due(item, date(2026, 9, 17), []))

    def test_done_action_never_appears(self):
        item = action(status="done", action_type="trigger")
        self.assertEqual(suggest_for_day([item], [], date(2026, 9, 17)), [])
