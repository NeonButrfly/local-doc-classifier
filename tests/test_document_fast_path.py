import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "classifier" / "app"
PDF_FIXTURE_PATH = REPO_ROOT / "tests" / "fixtures" / "synthetic_vendor_service_agreement.pdf"
DOCX_FIXTURE_PATH = REPO_ROOT / "tests" / "fixtures" / "synthetic_network_incident_report.docx"

if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))


def load_classifier_module():
    module_path = APP_DIR / "classify-to-obsidian.py"
    spec = importlib.util.spec_from_file_location("classify_to_obsidian", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class DocumentFastPathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.classifier_module = load_classifier_module()
        cls.categories = [
            "legal",
            "contract",
            "policy",
            "work",
            "technical",
            "report",
            "unknown",
            "needs-review",
        ]
        cls.synthetic_pdf_text = (
            "Synthetic Vendor Service Agreement\n"
            "Agreement Summary\n"
            "This mock agreement is between Northstar Demo Systems LLC and Aurora Test Services Inc.\n"
            "1. Scope of Services\n"
            "2. Term\n"
            "3. Confidentiality\n"
            "4. Payment\n"
            "5. Limitation of Liability\n"
            "6. Governing Law\n"
            "Expected Classifier Behavior\n"
            "Primary target label: legal or contract.\n"
        )

    def test_parse_docx_fast_extracts_fixture_text(self):
        markdown, parser_name = self.classifier_module.parse_docx_fast(DOCX_FIXTURE_PATH)

        self.assertEqual(parser_name, "docx-xml")
        self.assertIn("Synthetic Network Incident Report", markdown)
        self.assertIn("Root Cause", markdown)
        self.assertIn("Corrective Actions", markdown)

    def test_parse_pdf_fast_uses_pdftotext_output(self):
        class FakeCompleted:
            returncode = 0
            stdout = self.synthetic_pdf_text
            stderr = ""

        with patch.object(
            self.classifier_module.subprocess,
            "run",
            return_value=FakeCompleted(),
        ):
            markdown, parser_name = self.classifier_module.parse_pdf_fast(PDF_FIXTURE_PATH)

        self.assertEqual(parser_name, "pdftotext")
        self.assertIn("Synthetic Vendor Service Agreement", markdown)
        self.assertIn("Governing Law", markdown)

    def test_classify_document_fast_classifies_legal_agreement_without_model(self):
        with patch.object(
            self.classifier_module,
            "ollama_chat",
            side_effect=AssertionError("document fast path should not call ollama"),
        ):
            classification = self.classifier_module.classify_document_fast(
                source_path=PDF_FIXTURE_PATH,
                markdown=self.synthetic_pdf_text,
                categories=self.categories,
            )

        self.assertIsNotNone(classification)
        self.assertEqual(classification["primary_label"], "legal")
        self.assertIn("contract", classification["secondary_labels"])
        self.assertIn("work", classification["secondary_labels"])

    def test_classify_document_fast_classifies_incident_report_without_model(self):
        markdown, _ = self.classifier_module.parse_docx_fast(DOCX_FIXTURE_PATH)

        with patch.object(
            self.classifier_module,
            "ollama_chat",
            side_effect=AssertionError("document fast path should not call ollama"),
        ):
            classification = self.classifier_module.classify_document_fast(
                source_path=DOCX_FIXTURE_PATH,
                markdown=markdown,
                categories=self.categories,
            )

        self.assertIsNotNone(classification)
        self.assertEqual(classification["primary_label"], "report")
        self.assertIn("technical", classification["secondary_labels"])
        self.assertIn("work", classification["secondary_labels"])
        self.assertIn("policy", classification["secondary_labels"])

    def test_hybrid_document_path_uses_inline_model_when_gate_requires_llm(self):
        heuristic = {
            "primary_label": "legal",
            "secondary_labels": ["contract", "work"],
            "confidence": 0.96,
        }
        model_result = {
            "primary_label": "policy",
            "secondary_labels": ["legal", "work"],
            "confidence": 0.88,
            "summary": "Taxonomy-aware model result",
            "reason": "Model overrode heuristic due to conflict.",
            "sensitive_flags": ["legal"],
            "recommended_action": "review",
            "file_date_guess": "unknown",
            "language": "English",
        }

        with patch.object(
            self.classifier_module,
            "classify_markdown",
            return_value=model_result,
        ), patch.object(
            self.classifier_module,
            "predict_lightgbm_result",
            return_value={
                "top_label": "policy",
                "top_probability": 0.91,
                "needs_llm_probability": 0.82,
                "disagreement_risk": 0.71,
                "top_labels": ["policy", "legal"],
            },
        ):
            classification, hybrid_meta = self.classifier_module.resolve_hybrid_document_decision(
                source_path=PDF_FIXTURE_PATH,
                markdown=self.synthetic_pdf_text,
                parser_name="pdftotext",
                categories=self.categories,
                heuristic_result=heuristic,
                ollama_url="http://127.0.0.1:9",
                model="fake-model",
                max_chars=16000,
            )

        self.assertEqual(classification["primary_label"], "policy")
        self.assertEqual(hybrid_meta["decision"]["live_source"], "inline-llm")
        self.assertTrue(hybrid_meta["decision"]["use_inline_llm"])

    def test_hybrid_document_path_records_fast_path_metadata_when_accepted(self):
        heuristic = {
            "primary_label": "legal",
            "secondary_labels": ["contract", "work"],
            "confidence": 0.96,
        }

        with patch.object(
            self.classifier_module,
            "predict_lightgbm_result",
            return_value={
                "top_label": "legal",
                "top_probability": 0.95,
                "needs_llm_probability": 0.11,
                "disagreement_risk": 0.09,
                "top_labels": ["legal", "contract"],
            },
        ):
            classification, hybrid_meta = self.classifier_module.resolve_hybrid_document_decision(
                source_path=PDF_FIXTURE_PATH,
                markdown=self.synthetic_pdf_text,
                parser_name="pdftotext",
                categories=self.categories,
                heuristic_result=heuristic,
                ollama_url="http://127.0.0.1:9",
                model="fake-model",
                max_chars=16000,
            )

        self.assertEqual(classification["primary_label"], "legal")
        self.assertEqual(hybrid_meta["decision"]["live_source"], "heuristic-fast-path")
        self.assertEqual(hybrid_meta["lightgbm"]["top_label"], "legal")
        self.assertIn("legal", hybrid_meta["taxonomy_candidates"])


if __name__ == "__main__":
    unittest.main()
