import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "classifier" / "app"

if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))


import hybrid_runtime


class LightGbmTrainingTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.model_path = self.root / "lightgbm-classifier.joblib"
        self.report_path = self.root / "lightgbm-training-report.json"
        self.training_rows = [
            {
                "filename": "synthetic_vendor_service_agreement.pdf",
                "extension": ".pdf",
                "parser": "pdftotext",
                "text_preview": "service agreement confidentiality payment governing law contract terms vendor",
                "heuristic_primary": "legal",
                "taxonomy_candidates": ["legal", "contract", "policy", "work"],
                "accepted_primary": "legal",
                "used_inline_llm": False,
                "disagreement": False,
            },
            {
                "filename": "synthetic_network_incident_report.docx",
                "extension": ".docx",
                "parser": "docx-xml",
                "text_preview": "incident report severity timeline root cause network rollback corrective actions",
                "heuristic_primary": "report",
                "taxonomy_candidates": ["report", "technical", "work", "policy"],
                "accepted_primary": "report",
                "used_inline_llm": False,
                "disagreement": False,
            },
            {
                "filename": "ambiguous_document.txt",
                "extension": ".txt",
                "parser": "plain-text",
                "text_preview": "unclear summary mixed billing policy notes and status report",
                "heuristic_primary": "work",
                "taxonomy_candidates": ["work", "policy", "financial", "report"],
                "accepted_primary": "policy",
                "used_inline_llm": True,
                "disagreement": True,
            },
        ]

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_train_lightgbm_model_writes_model_and_report(self):
        report = hybrid_runtime.train_lightgbm_model(
            training_rows=self.training_rows,
            model_path=self.model_path,
            report_path=self.report_path,
        )

        self.assertTrue(self.model_path.exists())
        self.assertTrue(self.report_path.exists())
        self.assertTrue(report["ok"])
        self.assertEqual(report["training_rows"], 3)
        self.assertGreaterEqual(report["class_count"], 3)

    def test_predict_lightgbm_result_returns_top_label_and_gate_scores(self):
        hybrid_runtime.train_lightgbm_model(
            training_rows=self.training_rows,
            model_path=self.model_path,
            report_path=self.report_path,
        )

        result = hybrid_runtime.predict_lightgbm_result(
            payload={
                "filename": "new_service_agreement.pdf",
                "extension": ".pdf",
                "parser": "pdftotext",
                "text_preview": "vendor contract service agreement payment confidentiality governing law",
                "heuristic_primary": "legal",
                "taxonomy_candidates": ["legal", "contract", "policy", "work"],
            },
            model_path=self.model_path,
        )

        self.assertEqual(result["top_label"], "legal")
        self.assertGreater(result["top_probability"], 0.3)
        self.assertIn("needs_llm_probability", result)
        self.assertIn("disagreement_risk", result)
        self.assertIn("legal", result["top_labels"])


if __name__ == "__main__":
    unittest.main()
