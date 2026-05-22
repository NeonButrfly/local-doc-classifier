import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "classifier" / "app"

if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))


def load_classifier_module():
    module_path = APP_DIR / "classify-to-obsidian.py"
    spec = importlib.util.spec_from_file_location("classify_to_obsidian", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class ObsidianNoteOutputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.classifier_module = load_classifier_module()

    def test_write_obsidian_note_emits_canonical_source_metadata(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            vault = root / "vault"
            source_path = root / "Inbox" / "Budget Draft.pdf"
            source_path.parent.mkdir(parents=True, exist_ok=True)
            source_path.write_bytes(b"pdf-bytes")
            self.classifier_module.ensure_vault(vault)

            note_path = self.classifier_module.write_obsidian_note(
                vault=vault,
                source_path=source_path,
                file_hash="abc123def4567890",
                markdown="Budget draft preview",
                classification={
                    "primary_label": "financial",
                    "secondary_labels": ["work"],
                    "confidence": 0.92,
                    "summary": "Quarterly budget draft.",
                    "reason": "Contains cost planning details.",
                    "sensitive_flags": [],
                    "recommended_action": "retain",
                    "file_date_guess": "2026-05-22",
                    "language": "English",
                },
                attach_originals=True,
            )

            note_text = note_path.read_text(encoding="utf-8")

        self.assertIn('canonical_source_path: ', note_text)
        self.assertIn(json.dumps(str(source_path)), note_text)
        self.assertIn('canonical_source_hash: "abc123def4567890"', note_text)
        self.assertIn('last_seen_filename: "Budget Draft.pdf"', note_text)
        self.assertIn('attachment_mode: "copied-compatibility"', note_text)
        self.assertIn('compatibility_attachment_path: "[[90 Attachments/financial/Budget Draft.pdf]]"', note_text)

    def test_write_obsidian_note_fills_blank_summary_and_reason_for_unknown_review_items(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            vault = root / "vault"
            source_path = root / "Inbox" / "Mystery Statement.pdf"
            source_path.parent.mkdir(parents=True, exist_ok=True)
            source_path.write_bytes(b"statement-bytes")
            self.classifier_module.ensure_vault(vault)

            note_path = self.classifier_module.write_obsidian_note(
                vault=vault,
                source_path=source_path,
                file_hash="feedfacecafebeef",
                markdown=None,
                classification={
                    "primary_label": "unknown",
                    "secondary_labels": [],
                    "confidence": 0.0,
                    "summary": "",
                    "reason": "",
                    "sensitive_flags": [],
                    "recommended_action": "review",
                    "file_date_guess": "unknown",
                    "language": "unknown",
                },
                attach_originals=False,
            )

            note_text = note_path.read_text(encoding="utf-8")

        self.assertIn("Review needed for Mystery Statement.pdf", note_text)
        self.assertIn("classifier confidence was 0.00", note_text)
        self.assertIn("routed to Needs Review because the classifier could not make a confident decision", note_text)

    def test_write_obsidian_note_accepts_canonical_source_override(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            vault = root / "vault"
            staged_path = root / "input" / "api" / "uuid-Budget Draft.pdf"
            staged_path.parent.mkdir(parents=True, exist_ok=True)
            staged_path.write_bytes(b"pdf-bytes")
            self.classifier_module.ensure_vault(vault)

            note_path = self.classifier_module.write_obsidian_note(
                vault=vault,
                source_path=staged_path,
                file_hash="1234567890abcdef",
                markdown="Budget draft preview",
                classification={
                    "primary_label": "financial",
                    "secondary_labels": [],
                    "confidence": 0.91,
                    "summary": "Budget draft.",
                    "reason": "Looks like a budget file.",
                    "sensitive_flags": [],
                    "recommended_action": "retain",
                    "file_date_guess": "2026-05-22",
                    "language": "English",
                },
                attach_originals=False,
                canonical_source_path="/srv/cloud-vault/mirrors/icloud/Documents/Budget Draft.pdf",
                canonical_source_hash="livehash-001",
                last_seen_filename="Budget Draft.pdf",
            )

            note_text = note_path.read_text(encoding="utf-8")

        self.assertIn('canonical_source_path: "/srv/cloud-vault/mirrors/icloud/Documents/Budget Draft.pdf"', note_text)
        self.assertIn('canonical_source_hash: "livehash-001"', note_text)
        self.assertIn('last_seen_filename: "Budget Draft.pdf"', note_text)


if __name__ == "__main__":
    unittest.main()
