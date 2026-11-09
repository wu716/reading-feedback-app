"""Select a small regression set from the files actually changed for one task.

Use --paths in a shared dirty checkout; --base is for an isolated checkout.
Unknown application files stop the gate for manual impact review.
"""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
AREAS = {
    "schedule": {
        "source": ("app/routers/schedule.py", "static/js/daily-schedule.js", "static/js/schedule-inline-editor.js"),
        "tests": ("tests/test_workspace_schedule.py", "tests/test_schedule_hierarchy_ui.js", "tests/test_schedule_inline_ui.js"),
    },
    "ledger": {
        "source": ("app/routers/long_term_details.py", "static/js/long-term.js", "static/js/meal-records.js"),
        "tests": ("tests/test_long_term_details.py", "tests/test_ledger_properties.py", "tests/test_meal_records_ui.js"),
    },
}
SHARED = {
    "static/index.html", "static/css/workspace.css", "static/css/long-term.css",
    "app/models.py", "main.py", "app/database.py",
}
SHARED_TESTS = (
    "tests/test_workspace_schedule.py", "tests/test_long_term_details.py",
    "tests/test_schedule_hierarchy_ui.js", "tests/test_mobile_long_term_navigation_ui.js",
)
NON_CODE = ("docs/", ".github/", "CHANGELOG.md", "AGENTS.md", "requirements-test.txt")


def changed_from(base):
    completed = subprocess.run(["git", "diff", "--name-only", base, "--"], cwd=ROOT,
                               capture_output=True, text=True, check=True)
    return completed.stdout.splitlines()


def select(paths):
    tests, areas, shared, unknown = set(), set(), set(), set()
    for raw in paths:
        path = raw.replace("\\", "/").removeprefix("./")
        if path in SHARED:
            shared.add(path)
            tests.update(SHARED_TESTS)
        elif path.startswith("tests/test_") and path.endswith((".py", ".js")):
            tests.add(path)
        elif any(path in area["source"] for area in AREAS.values()):
            for name, area in AREAS.items():
                if path in area["source"]:
                    areas.add(name)
                    tests.update(area["tests"])
        elif path.startswith(NON_CODE) or path.startswith("scripts/regression_gate.py"):
            continue
        elif path.startswith(("app/", "static/", "mobile/", "desktop/")):
            unknown.add(path)
    return sorted(tests), sorted(areas), sorted(shared), sorted(unknown)


def run_tests(tests):
    python_tests = [str(ROOT / path) for path in tests if path.endswith(".py")]
    js_tests = [str(ROOT / path) for path in tests if path.endswith(".js")]
    commands = []
    if python_tests:
        commands.append([sys.executable, "-m", "pytest", *python_tests, "-q", "--disable-warnings"])
    if js_tests:
        node = os.environ.get("SHURAN_NODE") or shutil.which("node")
        if not node:
            print("STOP: Node unavailable; set SHURAN_NODE to the Node executable", file=sys.stderr)
            return 2
        if not os.environ.get("PLAYWRIGHT_PACKAGE") and not (ROOT / "node_modules/playwright").exists():
            print("STOP: Playwright unavailable; set PLAYWRIGHT_PACKAGE to its installed package path", file=sys.stderr)
            return 2
        commands.extend([[node, path] for path in js_tests])
    for command in commands:
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        print("RUN", " ".join(Path(part).name if part.startswith(str(ROOT)) else part for part in command))
        if result.returncode:
            print(result.stdout[-3000:])
            print(result.stderr[-3000:], file=sys.stderr)
            return result.returncode
        print((result.stdout.strip().splitlines() or ["passed"])[-1][:300])
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--paths", nargs="+", help="task files in a dirty checkout")
    source.add_argument("--base", help="Git base in an isolated checkout")
    parser.add_argument("--run", action="store_true", help="run selected tests after reviewing the plan")
    parser.add_argument("--ack-shared", action="store_true", help="confirm shared-file consumers were inspected")
    args = parser.parse_args()
    paths = args.paths if args.paths is not None else changed_from(args.base)
    tests, areas, shared, unknown = select(paths)
    print("Changed:", ", ".join(paths) or "none")
    print("Areas:", ", ".join(areas) or "none")
    print("Tests:", ", ".join(tests) or "none")
    if shared:
        print("Shared review required:", ", ".join(shared))
    if unknown:
        print("STOP: unmapped application files:", ", ".join(unknown), file=sys.stderr)
        return 2
    if shared and not args.ack_shared:
        print("STOP: inspect shared-file consumers, then rerun with --ack-shared", file=sys.stderr)
        return 2
    return run_tests(tests) if args.run else 0


if __name__ == "__main__":
    raise SystemExit(main())
