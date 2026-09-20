# -*- coding: utf-8 -*-
from datetime import date
from types import SimpleNamespace
from unittest import TestCase

from pydantic import ValidationError

from app.habit_service import summarize_events
from app.routers.habit_programs import HabitProgramCreate


def event(day, *, outcome=None, event_type="check_in", effort=None, urge=None, deleted=False):
    return SimpleNamespace(
        event_date=day,
        outcome=outcome,
        event_type=event_type,
        effort=effort,
        urge=urge,
        deleted_at=date(2026, 9, 20) if deleted else None,
    )


class HabitSummaryTests(TestCase):
    def test_program_name_and_anchor_cannot_be_whitespace(self):
        with self.assertRaises(ValidationError):
            HabitProgramCreate(
                title="   ",
                anchor_text="晚饭后",
                minimum_action="下楼",
            )
        with self.assertRaises(ValidationError):
            HabitProgramCreate(
                title="散步",
                anchor_text="   ",
                minimum_action="下楼",
            )

    def test_multiple_sources_on_one_day_count_once(self):
        today = date(2026, 9, 20)
        summary = summarize_events(
            [
                event(today, outcome="completed", event_type="execution"),
                event(today, outcome="completed", event_type="practice"),
            ],
            target_days=5,
            today=today,
        )
        self.assertEqual(summary["completed_days"], 1)

    def test_best_outcome_wins_when_sources_disagree(self):
        today = date(2026, 9, 20)
        summary = summarize_events(
            [
                event(today, outcome="missed"),
                event(today, outcome="partial"),
                event(today, outcome="completed"),
            ],
            target_days=5,
            today=today,
        )
        self.assertEqual(summary["today_outcome"], "completed")
        self.assertEqual(summary["missed_days"], 0)

    def test_capture_signals_are_context_not_completions(self):
        today = date(2026, 9, 20)
        summary = summarize_events(
            [event(today, event_type="signal"), event(today, outcome="partial")],
            target_days=3,
            today=today,
        )
        self.assertEqual(summary["signal_count"], 1)
        self.assertEqual(summary["partial_days"], 1)
        self.assertEqual(summary["completed_days"], 0)

    def test_deleted_and_old_events_are_ignored(self):
        today = date(2026, 9, 20)
        summary = summarize_events(
            [
                event(date(2026, 9, 10), outcome="completed"),
                event(today, outcome="completed", deleted=True),
            ],
            target_days=9,
            today=today,
        )
        self.assertEqual(summary["completed_days"], 0)
        self.assertEqual(summary["target_days"], 7)

    def test_effort_and_urge_averages_are_kept_separate(self):
        today = date(2026, 9, 20)
        summary = summarize_events(
            [
                event(today, outcome="partial", effort=2),
                event(date(2026, 9, 19), outcome="completed", effort=4),
                event(date(2026, 9, 18), outcome="missed", urge=5),
            ],
            target_days=5,
            today=today,
        )
        self.assertEqual(summary["average_effort"], 3.0)
        self.assertEqual(summary["average_urge"], 5.0)
