from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCHEDULE_JS = ROOT / "static" / "js" / "daily-schedule.js"
INDEX_HTML = ROOT / "static" / "index.html"
SCHEDULE_API = ROOT / "app" / "routers" / "schedule.py"
APP_TABBAR_JS = ROOT / "static" / "js" / "app-tabbar.js"


class ScheduleUiSeparationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SCHEDULE_JS.read_text(encoding="utf-8")
        cls.task = cls.source.split("function renderTask(task, isChild)", 1)[1].split(
            "function renderSortPlan", 1
        )[0]
        cls.sort = cls.source.split("function renderSortPlan", 1)[1].split(
            "function groupSiblings", 1
        )[0]
        cls.index = INDEX_HTML.read_text(encoding="utf-8")
        cls.api = SCHEDULE_API.read_text(encoding="utf-8")
        cls.tabbar = APP_TABBAR_JS.read_text(encoding="utf-8")

    def test_task_writing_and_feedback_do_not_require_attributes_mode(self):
        self.assertNotIn("function renderDesignPlan", self.source)
        self.assertNotIn('data-schedule-mode="design"', self.index)
        self.assertIn("if (addRow) addRow.hidden = false", self.source)
        self.assertIn("renderTitle(task)", self.task)
        self.assertIn("renderQuickAttributes(task)", self.task)
        self.assertIn("renderTimeFeedback(task)", self.task)
        self.assertNotIn("data-sort-handle", self.task)

    def test_sort_mode_contains_ordering_controls_but_no_attributes(self):
        self.assertIn("data-sort-handle", self.sort)
        self.assertIn('data-act="parallel"', self.sort)
        self.assertNotIn('data-act="fam"', self.sort)
        self.assertNotIn('data-act="priority"', self.sort)
        self.assertNotIn('data-act="edit"', self.sort)

    def test_new_task_composer_submits_attributes_and_list_shows_feedback(self):
        self.assertIn('data-new-act="fam"', self.index)
        self.assertNotIn('data-new-act="priority"', self.index)
        self.assertIn('schedulePractice', self.index)
        self.assertIn("familiarity: attributes?.familiarity", self.source)
        self.assertIn("priority: Number.isInteger(attributes?.priority)", self.source)
        self.assertIn("flow-feedback", self.source)
        self.assertIn("function renderQuickAttributes", self.source)
        self.assertIn("!e.isComposing && e.keyCode !== 229", self.source)
        self.assertIn("familiarity: Optional[str] = None", self.api)
        self.assertIn("familiarity=body.familiarity", self.api)

    def test_mobile_navigation_exposes_retained_tools_only(self):
        self.assertIn("{ id: 'projects'", self.tabbar)
        self.assertIn("{ id: 'capture'", self.tabbar)
        self.assertIn("{ id: 'schedule'", self.tabbar)
        self.assertIn("{ id: 'long-term'", self.tabbar)
        self.assertNotIn("{ id: 'methods'", self.tabbar)
        self.assertNotIn("navigateTo('actions')", self.index)
        self.assertNotIn("navigateTo('self-talk')", self.index)
        self.assertIn("const PRIMARY_TABS_PHONE = new Set(['schedule', 'capture', 'long-term', 'user-center'])", self.index)
        self.assertIn('data-section="long-term"', self.index)


if __name__ == "__main__":
    unittest.main()
