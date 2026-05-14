import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "classifier" / "app"
FIXTURE_PATH = REPO_ROOT / "tests" / "fixtures" / "synthetic_snowy_industrial_waystation_reference.jpg"

if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from category_manager import normalize_image_classification_result


def load_classifier_module():
    module_path = APP_DIR / "classify-to-obsidian.py"
    spec = importlib.util.spec_from_file_location("classify_to_obsidian", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class ImageLabelPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.classifier_module = load_classifier_module()
        cls.categories = [
            "reference-image",
            "concept-art",
            "environment-art",
            "architecture",
            "industrial",
            "sci-fi",
            "snow-ice",
            "facility",
            "waystation",
            "image-only",
            "technical",
            "marketing",
            "unknown",
            "needs-review",
        ]

    def test_normalizer_rewrites_marketing_waystation_to_reference_image(self):
        result = normalize_image_classification_result(
            {
                "primary_label": "marketing",
                "secondary_labels": ["image-only"],
                "summary": "A snowy industrial way station with pipes and structures.",
                "reason": "The image depicts an industrial sci-fi facility exterior.",
            }
        )

        self.assertEqual(result["primary_label"], "reference-image")
        self.assertEqual(
            result["secondary_labels"],
            [
                "concept-art",
                "environment-art",
                "industrial",
                "sci-fi",
                "snow-ice",
                "facility",
                "waystation",
                "architecture",
            ],
        )

    def test_normalizer_keeps_true_technical_image_as_technical(self):
        result = normalize_image_classification_result(
            {
                "primary_label": "technical",
                "secondary_labels": ["image-only"],
                "summary": "A terminal screenshot showing a configuration error and log file output.",
                "reason": "The image is a UI capture with code and an error message.",
            }
        )

        self.assertEqual(result["primary_label"], "technical")
        self.assertEqual(result["secondary_labels"], ["image-only"])

    def test_classify_image_applies_normalizer_before_returning(self):
        mocked_model_result = {
            "primary_label": "marketing",
            "secondary_labels": ["image-only"],
            "confidence": 0.62,
            "summary": "Snowy industrial sci-fi waystation exterior at night.",
            "reason": "Pipes, structures, and a frozen facility suggest a branded industrial scene.",
            "sensitive_flags": ["none"],
            "recommended_action": "keep",
            "file_date_guess": "unknown",
            "language": "unknown",
        }

        with patch.object(
            self.classifier_module,
            "ollama_chat",
            return_value=json.dumps(mocked_model_result),
        ):
            result = self.classifier_module.classify_image(
                source_path=FIXTURE_PATH,
                categories=self.categories,
                ollama_url="http://127.0.0.1:9",
                vision_model="fake-model",
            )

        self.assertEqual(result["primary_label"], "reference-image")
        self.assertIn("waystation", result["secondary_labels"])
        self.assertIn("architecture", result["secondary_labels"])


if __name__ == "__main__":
    unittest.main()
