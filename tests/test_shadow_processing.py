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


class ShadowProcessingTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.queue_dir = self.root / "shadow-queue"
        self.comparisons_path = self.root / "shadow-comparisons.jsonl"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_enqueue_shadow_job_writes_queue_file(self):
        payload = {
            "filename": "fixture.pdf",
            "extension": ".pdf",
            "parser": "pdftotext",
            "heuristic_result": {"primary_label": "legal", "confidence": 0.97},
            "lightgbm_result": {"top_label": "legal", "top_probability": 0.91},
            "live_result": {"primary_label": "legal"},
            "taxonomy_candidates": ["legal", "contract", "policy"],
            "text_preview": "Synthetic Vendor Service Agreement",
        }

        job_path = hybrid_runtime.enqueue_shadow_job(payload, queue_dir=self.queue_dir)

        self.assertTrue(job_path.exists())
        stored = json.loads(job_path.read_text(encoding="utf-8"))
        self.assertEqual(stored["filename"], "fixture.pdf")
        self.assertEqual(stored["heuristic_result"]["primary_label"], "legal")

    def test_process_shadow_queue_writes_comparison_record(self):
        hybrid_runtime.enqueue_shadow_job(
            {
                "filename": "fixture.pdf",
                "extension": ".pdf",
                "parser": "pdftotext",
                "heuristic_result": {"primary_label": "legal", "confidence": 0.97},
                "lightgbm_result": {"top_label": "legal", "top_probability": 0.91},
                "live_result": {"primary_label": "legal"},
                "taxonomy_candidates": ["legal", "contract", "policy"],
                "text_preview": "Synthetic Vendor Service Agreement",
            },
            queue_dir=self.queue_dir,
        )

        processed = hybrid_runtime.process_shadow_queue_once(
            queue_dir=self.queue_dir,
            comparisons_path=self.comparisons_path,
            shadow_classifier=lambda job: {
                "primary_label": "contract",
                "secondary_labels": ["legal"],
                "confidence": 0.86,
            },
        )

        self.assertEqual(processed, 1)
        self.assertTrue(self.comparisons_path.exists())
        lines = self.comparisons_path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        record = json.loads(lines[0])
        self.assertEqual(record["live_primary"], "legal")
        self.assertEqual(record["shadow_primary"], "contract")
        self.assertTrue(record["disagreement"])


if __name__ == "__main__":
    unittest.main()
