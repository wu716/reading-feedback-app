# -*- coding: utf-8 -*-
from unittest import TestCase

from pydantic import ValidationError

from app.routers.capture import CaptureIn, PreferenceUpdate, normalize_kind, normalize_todo_when


class CaptureGuardTests(TestCase):
    def test_unknown_kind_falls_back_to_moment(self):
        self.assertEqual(normalize_kind(None), "moment")
        self.assertEqual(normalize_kind(""), "moment")
        self.assertEqual(normalize_kind("diary"), "moment")

    def test_known_kinds_pass_through(self):
        self.assertEqual(normalize_kind("IDEA"), "idea")
        self.assertEqual(normalize_kind("todo"), "todo")
        self.assertEqual(normalize_kind("moment"), "moment")

    def test_todo_when_defaults_to_today(self):
        self.assertEqual(normalize_todo_when(None), "today")
        self.assertEqual(normalize_todo_when("later"), "later")
        self.assertEqual(normalize_todo_when("tomorrow"), "today")

    def test_preference_rejects_unknown_kind(self):
        with self.assertRaises(ValidationError):
            PreferenceUpdate(kind="diary")

    def test_capture_requires_text(self):
        with self.assertRaises(ValidationError):
            CaptureIn(kind="idea", text="  ")

    def test_todo_when_must_be_today_or_later(self):
        with self.assertRaises(ValidationError):
            CaptureIn(kind="todo", text="买牛奶", todo_when="someday")
        body = CaptureIn(kind="todo", text="买牛奶", todo_when="later")
        self.assertEqual(body.todo_when, "later")
