import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "classifier" / "app"

if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))


import hybrid_runtime


class AutonomousUpdatesTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.gating_path = self.root / "hybrid-gating.json"
        self.rules_path = self.root / "heuristic-rules.json"
        self.comparisons_path = self.root / "shadow-comparisons.jsonl"
        hybrid_runtime.save_json(self.gating_path, dict(hybrid_runtime.DEFAULT_HYBRID_GATING))
        hybrid_runtime.save_json(self.rules_path, dict(hybrid_runtime.DEFAULT_HEURISTIC_RULES))

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_apply_disagreement_updates_adjusts_thresholds(self):
        disagreements = [
            {"parser": "pdftotext", "heuristic_primary": "legal", "shadow_primary": "policy", "disagreement": True},
            {"parser": "pdftotext", "heuristic_primary": "legal", "shadow_primary": "policy", "disagreement": True},
            {"parser": "pdftotext", "heuristic_primary": "legal", "shadow_primary": "policy", "disagreement": True},
        ]

        updated = hybrid_runtime.apply_disagreement_updates(
            comparisons=disagreements,
            gating_path=self.gating_path,
            rules_path=self.rules_path,
        )

        self.assertTrue(updated["updated"])
        gating = hybrid_runtime.load_json(self.gating_path, {})
        rules = hybrid_runtime.load_json(self.rules_path, {})
        self.assertLess(gating["heuristic_fast_confidence"], hybrid_runtime.DEFAULT_HYBRID_GATING["heuristic_fast_confidence"])
        self.assertIn("pdftotext|legal", rules["force_inline_llm_for"])

    def test_process_shadow_queue_triggers_retrain_when_threshold_is_met(self):
        self.comparisons_path.write_text(
            "\n".join(
                json.dumps(
                    {
                        "filename": f"fixture-{index}.pdf",
                        "extension": ".pdf",
                        "parser": "pdftotext",
                        "heuristic_primary": "legal",
                        "lightgbm_primary": "legal",
                        "live_primary": "legal",
                        "shadow_primary": "contract",
                        "taxonomy_candidates": ["legal", "contract", "policy"],
                        "text_preview": "agreement confidentiality payment governing law",
                        "disagreement": True,
                    }
                )
                for index in range(3)
            )
            + "\n",
            encoding="utf-8",
        )

        with patch.object(
            hybrid_runtime,
            "train_lightgbm_model",
            return_value={"ok": True, "training_rows": 3},
        ) as mocked_train:
            result = hybrid_runtime.maybe_retrain_from_shadow_data(
                comparisons_path=self.comparisons_path,
                model_path=self.root / "lightgbm-classifier.joblib",
                report_path=self.root / "lightgbm-training-report.json",
                min_rows=3,
            )

        self.assertTrue(result["retrained"])
        mocked_train.assert_called_once()


if __name__ == "__main__":
    unittest.main()
