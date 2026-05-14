import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "tests" / "run_synthetic_readiness_sweep.py"
SUITE_PATH = REPO_ROOT / "tests" / "fixtures" / "synthetic-readiness-cases.json"


def load_sweep_module():
    spec = importlib.util.spec_from_file_location("synthetic_readiness_sweep", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class SyntheticReadinessSweepTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_sweep_module()
        cls.suite = json.loads(SUITE_PATH.read_text(encoding="utf-8"))

    def test_render_generated_csv_case_creates_valid_csv_bytes(self):
        case = next(item for item in self.suite["cases"] if item["id"] == "generated-budget-csv")

        rendered = self.module.render_generated_case(case["source"]).decode("utf-8")

        self.assertIn("Department,Category,Q1 Actual", rendered)
        self.assertIn("Operations,Cloud Hosting", rendered)

    def test_materialize_case_uses_existing_fixture_paths(self):
        case = next(item for item in self.suite["cases"] if item["id"] == "fixture-reference-image")

        with tempfile.TemporaryDirectory() as temp_dir:
            path = self.module.materialize_case(case, repo_root=REPO_ROOT, temp_root=Path(temp_dir))

        self.assertTrue(path.exists())
        self.assertEqual(path.name, "synthetic_snowy_industrial_waystation_reference.jpg")

    def test_assert_case_accepts_expected_primary_and_secondary(self):
        case = next(item for item in self.suite["cases"] if item["id"] == "generated-policy-markdown")
        response = {
            "ok": True,
            "record": {
                "classification": {
                    "primary_label": "policy",
                    "secondary_labels": ["work", "technical"],
                }
            },
        }

        self.module.assert_case(case, response)

    def test_assert_case_rejects_forbidden_primary(self):
        case = next(item for item in self.suite["cases"] if item["id"] == "generated-policy-markdown")
        response = {
            "ok": True,
            "record": {
                "classification": {
                    "primary_label": "reference-image",
                    "secondary_labels": ["policy"],
                }
            },
        }

        with self.assertRaises(AssertionError):
            self.module.assert_case(case, response)


if __name__ == "__main__":
    unittest.main()
