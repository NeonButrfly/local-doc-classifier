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


class HybridRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_choose_live_decision_prefers_fast_path_when_heuristic_and_model_align(self):
        gating = {
            "heuristic_fast_confidence": 0.92,
            "lightgbm_fast_confidence": 0.80,
            "needs_llm_threshold": 0.45,
            "disagreement_risk_threshold": 0.35,
        }
        heuristic = {
            "primary_label": "legal",
            "confidence": 0.97,
            "secondary_labels": ["contract", "work"],
        }
        lightgbm_result = {
            "top_label": "legal",
            "top_probability": 0.91,
            "needs_llm_probability": 0.18,
            "disagreement_risk": 0.08,
        }

        decision = hybrid_runtime.choose_live_decision(
            heuristic_result=heuristic,
            lightgbm_result=lightgbm_result,
            gating_config=gating,
            candidate_categories=["legal", "contract", "work", "policy"],
        )

        self.assertFalse(decision["use_inline_llm"])
        self.assertEqual(decision["live_source"], "heuristic-fast-path")
        self.assertEqual(decision["selected_primary_hint"], "legal")
        self.assertEqual(decision["decision_reason"], "fast-path-aligned")

    def test_choose_live_decision_requires_llm_on_confidence_conflict(self):
        gating = {
            "heuristic_fast_confidence": 0.92,
            "lightgbm_fast_confidence": 0.80,
            "aligned_soft_confidence": 0.60,
            "needs_llm_threshold": 0.45,
            "disagreement_risk_threshold": 0.35,
        }
        heuristic = {
            "primary_label": "legal",
            "confidence": 0.94,
            "secondary_labels": ["contract"],
        }
        lightgbm_result = {
            "top_label": "technical",
            "top_probability": 0.88,
            "needs_llm_probability": 0.61,
            "disagreement_risk": 0.72,
        }

        decision = hybrid_runtime.choose_live_decision(
            heuristic_result=heuristic,
            lightgbm_result=lightgbm_result,
            gating_config=gating,
            candidate_categories=["legal", "technical", "report", "policy"],
        )

        self.assertTrue(decision["use_inline_llm"])
        self.assertEqual(decision["live_source"], "inline-llm")
        self.assertEqual(decision["selected_primary_hint"], "technical")
        self.assertEqual(decision["decision_reason"], "model-required")

    def test_choose_live_decision_keeps_fast_path_for_aligned_soft_confidence(self):
        gating = {
            "heuristic_fast_confidence": 0.92,
            "lightgbm_fast_confidence": 0.80,
            "aligned_soft_confidence": 0.60,
            "needs_llm_threshold": 0.45,
            "disagreement_risk_threshold": 0.35,
        }
        heuristic = {
            "primary_label": "spreadsheet",
            "confidence": 0.98,
            "secondary_labels": ["financial", "work", "report"],
        }
        lightgbm_result = {
            "top_label": "spreadsheet",
            "top_probability": 0.68,
            "needs_llm_probability": 0.01,
            "disagreement_risk": 0.01,
        }

        decision = hybrid_runtime.choose_live_decision(
            heuristic_result=heuristic,
            lightgbm_result=lightgbm_result,
            gating_config=gating,
            candidate_categories=["spreadsheet", "financial", "work", "report"],
        )

        self.assertFalse(decision["use_inline_llm"])
        self.assertEqual(decision["live_source"], "heuristic-fast-path")
        self.assertEqual(decision["decision_reason"], "fast-path-aligned")

    def test_choose_live_decision_keeps_fast_path_when_label_model_is_strong(self):
        gating = {
            "heuristic_fast_confidence": 0.92,
            "lightgbm_fast_confidence": 0.80,
            "aligned_soft_confidence": 0.60,
            "needs_llm_threshold": 0.45,
            "disagreement_risk_threshold": 0.35,
        }
        heuristic = {
            "primary_label": "spreadsheet",
            "confidence": 0.98,
            "secondary_labels": ["financial", "work", "report"],
        }
        lightgbm_result = {
            "top_label": "spreadsheet",
            "top_probability": 0.999,
            "needs_llm_probability": 1.0,
            "disagreement_risk": 0.0,
        }

        decision = hybrid_runtime.choose_live_decision(
            heuristic_result=heuristic,
            lightgbm_result=lightgbm_result,
            gating_config=gating,
            candidate_categories=["spreadsheet", "financial", "work", "report"],
        )

        self.assertFalse(decision["use_inline_llm"])
        self.assertEqual(decision["live_source"], "heuristic-fast-path")
        self.assertEqual(decision["decision_reason"], "fast-path-aligned")

    def test_build_shadow_record_marks_disagreement(self):
        shadow = hybrid_runtime.build_shadow_record(
            filename="fixture.pdf",
            extension=".pdf",
            parser="pdftotext",
            heuristic_result={"primary_label": "legal", "confidence": 0.97},
            lightgbm_result={"top_label": "legal", "top_probability": 0.92},
            live_result={"primary_label": "legal", "secondary_labels": ["contract"]},
            llm_result={"primary_label": "technical", "secondary_labels": ["report"], "confidence": 0.91},
            taxonomy_candidates=["legal", "contract", "technical", "report"],
            text_preview="Synthetic Vendor Service Agreement",
        )

        self.assertTrue(shadow["disagreement"])
        self.assertEqual(shadow["heuristic_primary"], "legal")
        self.assertEqual(shadow["shadow_primary"], "technical")
        self.assertEqual(shadow["live_primary"], "legal")
        self.assertIn("technical", shadow["taxonomy_candidates"])
        self.assertEqual(shadow["teacher_review_status"], "teacher-approved")
        self.assertTrue(shadow["teacher_approved_for_training"])

    def test_evaluate_teacher_result_rejects_low_confidence_labels(self):
        teacher = hybrid_runtime.evaluate_teacher_result(
            llm_result={"primary_label": "legal", "confidence": 0.4},
            taxonomy_candidates=["legal", "contract", "policy"],
            live_result={"primary_label": "legal"},
            gating_config={"teacher_confidence_threshold": 0.85},
        )

        self.assertEqual(teacher["review_status"], "teacher-low-confidence")
        self.assertFalse(teacher["teacher_approved_for_training"])

    def test_build_readiness_report_requires_manual_enable_even_after_thresholds(self):
        queue_dir = self.root / "shadow-queue"
        queue_dir.mkdir(parents=True, exist_ok=True)
        comparisons_path = self.root / "shadow-comparisons.jsonl"
        model_path = self.root / "lightgbm-classifier.joblib"
        model_path.write_text("model", encoding="utf-8")

        rows = [
            {
                "teacher_approved_for_training": True,
                "teacher_supports_live_result": True,
            }
            for _ in range(8)
        ]
        comparisons_path.write_text(
            "\n".join(json.dumps(row) for row in rows) + "\n",
            encoding="utf-8",
        )

        report = hybrid_runtime.build_readiness_report(
            gating_config={
                "readiness_min_teacher_samples": 8,
                "readiness_min_teacher_agreement_rate": 0.80,
                "readiness_min_teacher_approval_rate": 0.70,
                "readiness_max_queue_depth": 25,
                "allow_real_ingestion": False,
            },
            comparisons_path=comparisons_path,
            queue_dir=queue_dir,
            model_path=model_path,
        )

        self.assertTrue(report["thresholds_pass"])
        self.assertFalse(report["real_ingestion_allowed"])
        self.assertIn("manual-real-ingestion-enable-still-required", report["warnings"])

    def test_load_and_save_hybrid_config_round_trip(self):
        path = self.root / "hybrid-gating.json"
        config = {
            "mode": "hybrid",
            "heuristic_fast_confidence": 0.91,
        }

        hybrid_runtime.save_json(path, config)
        loaded = hybrid_runtime.load_json(path, default={})

        self.assertEqual(loaded["mode"], "hybrid")
        self.assertEqual(loaded["heuristic_fast_confidence"], 0.91)


if __name__ == "__main__":
    unittest.main()
