import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "classifier" / "app"

if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import api_server


class UploadBenchmarkApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)

        api_server.API_TOKEN = "test-token"
        api_server.INPUT_ROOT = root / "input"
        api_server.OUTPUT_ROOT = root / "output"
        api_server.VAULT_ROOT = root / "vault"
        api_server.MANIFEST_PATH = api_server.OUTPUT_ROOT / "manifest.jsonl"
        api_server.INDEX_PATH = api_server.VAULT_ROOT / "Classification Index.md"
        api_server.READINESS_REPORT_PATH = api_server.OUTPUT_ROOT / "readiness-report.json"

        api_server.INPUT_ROOT.mkdir(parents=True, exist_ok=True)
        api_server.OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
        api_server.VAULT_ROOT.mkdir(parents=True, exist_ok=True)
        api_server.INDEX_PATH.write_text("# Index\n", encoding="utf-8")

        self.client = TestClient(api_server.APP)
        self.headers = {"X-API-Key": "test-token"}

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_upload_only_route_reports_transfer_metrics_and_cleans_up(self):
        payload = b"benchmark-data" * 2048
        response = self.client.post(
            "/benchmark/upload-only",
            headers=self.headers,
            data={"cleanup": "true"},
            files={"file": ("fixture.pdf", payload, "application/pdf")},
        )

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()

        self.assertTrue(body["ok"])
        self.assertEqual(body["bytes_received"], len(payload))
        self.assertEqual(body["filename"], "fixture.pdf")
        self.assertGreaterEqual(body["upload_ms"], 0)
        self.assertGreaterEqual(body["total_ms"], body["upload_ms"])
        self.assertFalse(body["staged_file_exists_after_response"])
        self.assertFalse(Path(body["staged_path"]).exists())

    def test_upload_only_route_can_keep_staged_file_for_inspection(self):
        payload = b"keep-me" * 1024
        response = self.client.post(
            "/benchmark/upload-only",
            headers=self.headers,
            data={"cleanup": "false"},
            files={"file": ("fixture.xlsx", payload, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        staged_path = Path(body["staged_path"])

        self.assertTrue(body["staged_file_exists_after_response"])
        self.assertTrue(staged_path.exists())
        self.assertEqual(staged_path.read_bytes(), payload)

    def test_classify_upload_reports_upload_and_classify_timing_breakdown(self):
        payload = b"classify-me" * 2048

        def fake_run(cmd, **kwargs):
            timing_output = Path(cmd[cmd.index("--timing-output") + 1])
            timing_output.parent.mkdir(parents=True, exist_ok=True)
            timing_output.write_text(
                json.dumps(
                    {
                        "mode": "document",
                        "parser": "docling",
                        "parse_ms": 12.5,
                        "model_ms": 345.6,
                        "note_write_ms": 7.8,
                        "total_ms": 366.2,
                    }
                ),
                encoding="utf-8",
            )
            return SimpleNamespace(returncode=0, stdout="ok", stderr="")

        with patch.object(
            api_server.subprocess,
            "run",
            side_effect=fake_run,
        ), patch.object(
            api_server,
            "read_manifest_for_source",
            side_effect=lambda source_path: {
                "source_path": source_path,
                "classification": {"primary_label": "legal"},
            },
        ):
            response = self.client.post(
                "/classify/upload",
                headers=self.headers,
                data={"attach_originals": "false"},
                files={"file": ("fixture.pdf", payload, "application/pdf")},
            )

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()

        self.assertTrue(body["ok"])
        self.assertGreaterEqual(body["upload_ms"], 0)
        self.assertGreaterEqual(body["classify_ms"], 0)
        self.assertGreaterEqual(body["total_ms"], body["upload_ms"])
        self.assertGreaterEqual(body["total_ms"], body["classify_ms"])
        self.assertEqual(body["record"]["classification"]["primary_label"], "legal")
        self.assertEqual(body["worker_timing"]["parser"], "docling")
        self.assertEqual(body["worker_timing"]["parse_ms"], 12.5)
        self.assertEqual(body["worker_timing"]["model_ms"], 345.6)

    def test_shadow_worker_cycle_does_not_wait_for_request_lock(self):
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append((cmd, kwargs))
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        with api_server.REQUEST_LOCK:
            with patch.object(api_server.subprocess, "run", side_effect=fake_run):
                api_server.run_shadow_worker_cycle()

        self.assertEqual(len(calls), 1)
        self.assertIn("--process-shadow-queue", calls[0][0])

    def test_classify_upload_blocks_real_folder_ingestion_when_readiness_is_not_allowed(self):
        payload = b"classify-me" * 1024
        readiness_path = api_server.READINESS_REPORT_PATH
        readiness_path.parent.mkdir(parents=True, exist_ok=True)
        readiness_path.write_text(
            json.dumps(
                {
                    "real_ingestion_allowed": False,
                    "warnings": ["manual-real-ingestion-enable-still-required"],
                }
            ),
            encoding="utf-8",
        )

        response = self.client.post(
            "/classify/upload",
            headers=self.headers,
            data={"ingestion_mode": "real-folder"},
            files={"file": ("fixture.pdf", payload, "application/pdf")},
        )

        self.assertEqual(response.status_code, 409, response.text)
        self.assertIn("Real-folder ingestion is blocked", response.text)

    def test_readiness_endpoint_returns_current_report(self):
        readiness_path = api_server.READINESS_REPORT_PATH
        readiness_path.parent.mkdir(parents=True, exist_ok=True)
        readiness_path.write_text(
            json.dumps({"thresholds_pass": True, "real_ingestion_allowed": False}),
            encoding="utf-8",
        )

        response = self.client.get("/readiness", headers=self.headers)

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertTrue(body["report"]["thresholds_pass"])


if __name__ == "__main__":
    unittest.main()
