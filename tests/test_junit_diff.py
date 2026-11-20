import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from junit_diff import ReportError, classify, compare, read_report


ROOT = Path(__file__).resolve().parents[1]
BEFORE = ROOT / "examples" / "before.xml"
AFTER = ROOT / "examples" / "after.xml"


class ReportTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / "report.xml"

    def parse(self, xml):
        self.path.write_text(xml, encoding="utf-8")
        return read_report(self.path)

    def test_nested_suites_and_namespaces(self):
        results = self.parse("""
            <testsuites xmlns="urn:results"><testsuite name="catalog"><testsuite>
                <testcase classname="inventory" name="test_price[€]"><failure/></testcase>
                <testcase name="plain"><skipped/></testcase>
            </testsuite></testsuite></testsuites>
        """)
        self.assertEqual(results, {("inventory", "test_price[€]"): "failed", ("", "plain"): "skipped"})

    def test_error_takes_precedence_over_failure(self):
        results = self.parse("""
            <testsuite><testcase name="charge">
                <failure/><error/><system-out>diagnostics</system-out>
            </testcase></testsuite>
        """)
        self.assertEqual(results[("", "charge")], "error")

    def test_output_content_does_not_set_the_outcome(self):
        results = self.parse("""
            <testsuite><testcase name="messages">
                <system-out><![CDATA[<failure/>]]></system-out>
            </testcase></testsuite>
        """)
        self.assertEqual(results[("", "messages")], "passed")

    def test_same_name_in_different_classes(self):
        results = self.parse("""
            <testsuite><testcase classname="A" name="save"/>
                       <testcase classname="B" name="save"/></testsuite>
        """)
        self.assertEqual(len(results), 2)

    def test_duplicate_identity_is_reported(self):
        with self.assertRaisesRegex(ReportError, "duplicate testcase"):
            self.parse('<testsuite><testcase name="save"/><testcase name="save"/></testsuite>')

    def test_missing_or_blank_test_name_is_reported(self):
        for attributes in ("", 'name="  "'):
            with self.subTest(attributes=attributes), self.assertRaisesRegex(ReportError, "without a name"):
                self.parse(f"<testsuite><testcase {attributes}/></testsuite>")

    def test_invalid_reports_identify_the_file(self):
        for xml in ("<testsuite>", "<inventory/>"):
            with self.subTest(xml=xml), self.assertRaises(ReportError) as raised:
                self.parse(xml)
            self.assertIn(str(self.path), str(raised.exception))

    def test_empty_suite(self):
        self.assertEqual(self.parse("<testsuites><testsuite/></testsuites>"), {})


class ComparisonTests(unittest.TestCase):
    def test_every_possible_transition(self):
        # Each row gives the expected group for every possible current outcome.
        outcomes = [None, "passed", "skipped", "failed", "error"]
        rows = {
            None:      [None,      "added",     "added",          "new_failures",  "new_failures"],
            "passed":  ["removed", None,        "status_changes", "new_failures",  "new_failures"],
            "skipped": ["removed", "status_changes", None,        "new_failures",  "new_failures"],
            "failed":  ["removed", "recovered", "status_changes", "still_failing", "still_failing"],
            "error":   ["removed", "recovered", "status_changes", "still_failing", "still_failing"],
        }
        for old, row in rows.items():
            for new, expected in zip(outcomes, row):
                if old is None and new is None:
                    continue  # A testcase must exist in at least one report.
                with self.subTest(before=old, after=new):
                    self.assertEqual(classify(old, new), expected)

    def test_stable_order_and_total_counts(self):
        after = {("Z", "run"): "error", ("A", "run"): "failed", ("B", "stable"): "skipped"}
        before = {("B", "stable"): "skipped", ("A", "run"): "passed"}
        result = compare(before, after)
        self.assertEqual((result.before_count, result.after_count, result.unchanged), (2, 3, 1))
        self.assertEqual([c.classname for c in result.groups["new_failures"]], ["A", "Z"])


class CommandTests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, str(ROOT / "junit_diff.py"), *map(str, args)],
            capture_output=True, text=True, encoding="utf-8", check=False,
        )

    def test_example_in_text_mode(self):
        process = self.run_cli(BEFORE, AFTER)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertIn("6 tests before, 6 after", process.stdout)
        self.assertIn("shipping.TestQuote::test_priority  absent -> error", process.stdout)
        self.assertIn("shipping.TestQuote::test_remote_area  failed -> passed", process.stdout)
        self.assertIn("1 unchanged (passed or skipped)", process.stdout)

    def test_json_preserves_identity_and_missing_state(self):
        process = self.run_cli(BEFORE, AFTER, "--format", "json", "--fail-on-new")
        self.assertEqual(process.returncode, 1, process.stderr)
        report = json.loads(process.stdout)
        self.assertEqual(report["groups"]["new_failures"][1], {
            "classname": "shipping.TestQuote", "name": "test_priority",
            "before": None, "after": "error",
        })
        self.assertEqual(report["groups"]["removed"][0]["after"], None)
        self.assertEqual(report["groups"]["added"], [])

    def test_existing_failures_do_not_trip_ci(self):
        process = self.run_cli(AFTER, AFTER, "--fail-on-new")
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertIn("Still failing (3)", process.stdout)

    def test_missing_file_uses_stderr_and_exit_two(self):
        with tempfile.TemporaryDirectory() as folder:
            process = self.run_cli(Path(folder) / "missing.xml", AFTER)
        self.assertEqual(process.returncode, 2)
        self.assertIn("missing.xml", process.stderr)
        self.assertEqual(process.stdout, "")


if __name__ == "__main__":
    unittest.main()
