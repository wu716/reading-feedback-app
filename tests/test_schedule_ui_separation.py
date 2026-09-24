from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCHEDULE_JS = ROOT / "static" / "js" / "daily-schedule.js"
INDEX_HTML = ROOT / "static" / "index.html"
SCHEDULE_API = ROOT / "app" / "routers" / "schedule.py"


class ScheduleUiSeparationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SCHEDULE_JS.read_text(encoding="utf-8")
        cls.design = cls.source.split("function renderDesignPlan", 1)[1].split(
            "function renderSortPlan", 1
        )[0]
        cls.sort = cls.source.split("function renderSortPlan", 1)[1].split(
            "function groupSiblings", 1
        )[0]
        cls.index = INDEX_HTML.read_text(encoding="utf-8")
        cls.api = SCHEDULE_API.read_text(encoding="utf-8")

    def test_design_mode_contains_attributes_but_no_ordering_controls(self):
        self.assertIn("flow-task-attributes", self.design)
        self.assertIn('data-act="fam"', self.design)
        self.assertIn('data-act="priority"', self.design)
        self.assertNotIn('data-act="parallel"', self.design)
        self.assertNotIn("data-sort-handle", self.design)
        self.assertNotIn('data-act="edit"', self.design)
        self.assertNotIn('data-act="delete"', self.design)

    def test_sort_mode_contains_ordering_controls_but_no_attributes(self):
        self.assertIn("data-sort-handle", self.sort)
        self.assertIn('data-act="parallel"', self.sort)
        self.assertNotIn('data-act="fam"', self.sort)
        self.assertNotIn('data-act="priority"', self.sort)
        self.assertNotIn('data-act="edit"', self.sort)

    def test_new_task_composer_submits_attributes_and_list_shows_feedback(self):
        self.assertIn('data-new-act="fam"', self.index)
        self.assertIn('data-new-act="priority"', self.index)
        self.assertIn("familiarity: attributes?.familiarity", self.source)
        self.assertIn("priority: Number.isInteger(attributes?.priority)", self.source)
        self.assertIn("flow-feedback", self.source)
        self.assertIn("function renderQuickAttributes", self.source)
        self.assertIn("mode !== 'list' && !task.completed", self.source)
        self.assertIn("familiarity: Optional[str] = None", self.api)
        self.assertIn("familiarity=body.familiarity", self.api)


if __name__ == "__main__":
    unittest.main()
