# -*- coding: utf-8 -*-
from datetime import date, datetime
from types import SimpleNamespace
from unittest import TestCase

from app.routers.time_log import (
    BEIJING_TZ,
    belongs_to_day,
    is_written_node,
    soft_delete_node,
)


class TimeLogGuardTests(TestCase):
    def test_blank_label_without_task_is_unwritten(self):
        self.assertFalse(is_written_node(SimpleNamespace(label="  ", task_id=None)))

    def test_label_counts_as_written(self):
        self.assertTrue(is_written_node(SimpleNamespace(label="读书", task_id=None)))

    def test_task_without_label_counts_as_written(self):
        self.assertTrue(is_written_node(SimpleNamespace(label="", task_id=12)))

    def test_wrong_log_date_still_belongs_to_logged_at_day(self):
        node = SimpleNamespace(
            log_date=date(2026, 9, 17),
            logged_at=datetime(2026, 9, 16, 23, 30, tzinfo=BEIJING_TZ),
        )
        self.assertTrue(belongs_to_day(node, date(2026, 9, 16)))
        self.assertTrue(belongs_to_day(node, date(2026, 9, 17)))

    def test_soft_delete_does_not_clear_label(self):
        node = SimpleNamespace(label="今早跑步", task_id=None, deleted_at=None)
        soft_delete_node(node)
        self.assertIsNotNone(node.deleted_at)
        self.assertEqual(node.label, "今早跑步")

    def test_purge_candidates_never_include_written_nodes(self):
        written = SimpleNamespace(label="已写", task_id=None)
        draft = SimpleNamespace(label="", task_id=None)
        to_purge = [node for node in (written, draft) if not is_written_node(node)]
        self.assertEqual(to_purge, [draft])
