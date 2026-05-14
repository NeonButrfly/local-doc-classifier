import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "classifier" / "app"
FIXTURE_PATH = REPO_ROOT / "tests" / "fixtures" / "synthetic_quarterly_budget_forecast.xlsx"

if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))


def load_classifier_module():
    module_path = APP_DIR / "classify-to-obsidian.py"
    spec = importlib.util.spec_from_file_location("classify_to_obsidian", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class SpreadsheetFastPathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.classifier_module = load_classifier_module()
        cls.categories = [
            "financial",
            "spreadsheet",
            "work",
            "report",
            "tax",
            "legal",
            "medical",
            "insurance",
            "technical",
            "unknown",
            "needs-review",
        ]

    def test_parse_spreadsheet_fast_builds_compact_workbook_summary(self):
        markdown, parser_name, metadata = self.classifier_module.parse_spreadsheet_fast(FIXTURE_PATH)

        self.assertEqual(parser_name, "spreadsheet-openpyxl")
        self.assertLess(len(markdown), 2200)
        self.assertIn("Budget Forecast", markdown)
        self.assertIn("Classifier Expectations", markdown)
        self.assertIn("Cloud Hosting", markdown)
        self.assertEqual(metadata["sheet_count"], 2)

    def test_classify_spreadsheet_fast_avoids_model_call_and_returns_expected_domain(self):
        with patch.object(
            self.classifier_module,
            "ollama_chat",
            side_effect=AssertionError("spreadsheet fast path should not call ollama"),
        ):
            markdown, classification, metadata = self.classifier_module.classify_spreadsheet_fast(
                source_path=FIXTURE_PATH,
                categories=self.categories,
            )

        self.assertEqual(classification["primary_label"], "spreadsheet")
        self.assertIn("financial", classification["secondary_labels"])
        self.assertIn("work", classification["secondary_labels"])
        self.assertIn("report", classification["secondary_labels"])
        self.assertNotIn("medical", classification["secondary_labels"])
        self.assertNotIn("medical", classification["sensitive_flags"])
        self.assertGreaterEqual(classification["confidence"], 0.9)
        self.assertEqual(metadata["parser"], "spreadsheet-openpyxl")
        self.assertIn("budget", classification["reason"].lower())
        self.assertTrue(markdown)


if __name__ == "__main__":
    unittest.main()
