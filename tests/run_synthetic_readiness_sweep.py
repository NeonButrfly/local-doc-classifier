#!/usr/bin/env python3
import argparse
import csv
import json
import mimetypes
import os
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, Tuple
from urllib import error, request


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SUITE_PATH = REPO_ROOT / "tests" / "fixtures" / "synthetic-readiness-cases.json"
DEFAULT_API_BASE = "http://192.168.50.196:4319"

MIME_OVERRIDES = {
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".csv": "text/csv",
    ".html": "text/html",
    ".htm": "text/html",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def csv_bytes(rows: Iterable[Iterable[Any]]) -> bytes:
    from io import StringIO

    buffer = StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    for row in rows:
        writer.writerow(list(row))
    return buffer.getvalue().encode("utf-8")


def render_generated_case(source: Dict[str, Any]) -> bytes:
    kind = str(source.get("kind", "")).lower()
    if kind in {"text", "markdown", "html"}:
        return str(source.get("content", "")).encode("utf-8")
    if kind == "csv":
        return csv_bytes(source.get("rows", []))
    raise ValueError(f"Unsupported generated source kind: {kind}")


def materialize_case(case: Dict[str, Any], repo_root: Path, temp_root: Path) -> Path:
    source = case["source"]
    kind = str(source.get("kind", "")).lower()
    if kind == "fixture":
        return repo_root / Path(str(source["path"]))

    filename = str(source["filename"])
    path = temp_root / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(render_generated_case(source))
    return path


def guess_mime_type(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in MIME_OVERRIDES:
        return MIME_OVERRIDES[ext]
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def build_multipart_body(fields: Dict[str, str], file_path: Path) -> Tuple[bytes, str]:
    boundary = f"----LocalDocClassifier{uuid.uuid4().hex}"
    chunks = []

    for key, value in fields.items():
        chunks.append(f"--{boundary}\r\n".encode("utf-8"))
        chunks.append(f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode("utf-8"))
        chunks.append(str(value).encode("utf-8"))
        chunks.append(b"\r\n")

    mime_type = guess_mime_type(file_path)
    chunks.append(f"--{boundary}\r\n".encode("utf-8"))
    chunks.append(
        (
            f'Content-Disposition: form-data; name="file"; filename="{file_path.name}"\r\n'
            f"Content-Type: {mime_type}\r\n\r\n"
        ).encode("utf-8")
    )
    chunks.append(file_path.read_bytes())
    chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(chunks), boundary


def http_json(url: str, token: str) -> Tuple[int, Dict[str, Any]]:
    req = request.Request(url, method="GET", headers={"X-API-Key": token})
    try:
        with request.urlopen(req, timeout=30) as response:
            payload = response.read().decode("utf-8")
            return response.status, json.loads(payload)
    except error.HTTPError as exc:
        payload = exc.read().decode("utf-8", errors="replace")
        return exc.code, json.loads(payload)


def upload_case(api_base: str, token: str, file_path: Path) -> Tuple[int, Dict[str, Any]]:
    body, boundary = build_multipart_body({"ingestion_mode": "adhoc"}, file_path)
    req = request.Request(
        f"{api_base}/classify/upload",
        data=body,
        method="POST",
        headers={
            "X-API-Key": token,
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(body)),
        },
    )
    try:
        with request.urlopen(req, timeout=180) as response:
            payload = response.read().decode("utf-8")
            return response.status, json.loads(payload)
    except error.HTTPError as exc:
        payload = exc.read().decode("utf-8", errors="replace")
        return exc.code, json.loads(payload)


def assert_case(case: Dict[str, Any], response: Dict[str, Any]) -> None:
    if response.get("ok") is not True:
        raise AssertionError(f"{case['id']} did not return ok=true")

    primary = str(((response.get("record") or {}).get("classification") or {}).get("primary_label") or "")
    if not primary:
        raise AssertionError(f"{case['id']} produced no primary_label")

    acceptable = case.get("acceptable_primary_labels", []) or []
    forbidden = case.get("forbidden_primary_labels", []) or []
    expected_secondary = case.get("expected_secondary_any", []) or []
    secondary = ((response.get("record") or {}).get("classification") or {}).get("secondary_labels") or []

    if acceptable and primary not in acceptable:
        raise AssertionError(f"{case['id']} primary_label '{primary}' not in acceptable set")
    if forbidden and primary in forbidden:
        raise AssertionError(f"{case['id']} primary_label '{primary}' is forbidden")

    if expected_secondary:
        seen = set(secondary)
        seen.add(primary)
        if not any(label in seen for label in expected_secondary):
            raise AssertionError(f"{case['id']} missed all expected secondary labels")


def poll_readiness(
    api_base: str,
    token: str,
    initial_reviewed_rows: int,
    expected_new_rows: int,
    timeout_seconds: int,
    poll_interval_seconds: float,
) -> Dict[str, Any]:
    deadline = time.time() + timeout_seconds
    latest: Dict[str, Any] = {}
    target = initial_reviewed_rows + expected_new_rows

    while time.time() < deadline:
        status_code, payload = http_json(f"{api_base}/readiness", token)
        if status_code == 200:
            latest = payload
            report = payload.get("report") or {}
            reviewed_rows = int(report.get("teacher_reviewed_rows", 0) or 0)
            queue_depth = int(report.get("queue_depth", 0) or 0)
            if reviewed_rows >= target and queue_depth == 0:
                return latest
        time.sleep(poll_interval_seconds)

    return latest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a broader synthetic readiness sweep against the classifier API.")
    parser.add_argument("--api-base", default=DEFAULT_API_BASE, help="Classifier API base URL.")
    parser.add_argument("--token", default="", help="Classifier API token.")
    parser.add_argument("--token-env", default="TOKEN", help="Environment variable to read when --token is omitted.")
    parser.add_argument("--suite-path", default=str(DEFAULT_SUITE_PATH), help="Path to the synthetic readiness suite JSON.")
    parser.add_argument("--repo-root", default=str(REPO_ROOT), help="Repo root for resolving committed fixtures.")
    parser.add_argument("--output", default="", help="Optional path for a JSON report artifact.")
    parser.add_argument("--wait-for-shadow", action="store_true", help="Poll /readiness until shadow review catches up.")
    parser.add_argument("--wait-timeout", type=int, default=180, help="Seconds to wait when --wait-for-shadow is enabled.")
    parser.add_argument("--wait-poll", type=float, default=5.0, help="Polling interval for /readiness.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    token = args.token or os.environ.get(args.token_env, "")
    if not token:
        print("Missing token. Provide --token or set the token environment variable.", file=sys.stderr)
        return 2

    repo_root = Path(args.repo_root).resolve()
    suite = load_json(Path(args.suite_path))
    cases = suite.get("cases", []) or []

    readiness_before = {}
    status_code, payload = http_json(f"{args.api_base}/readiness", token)
    if status_code == 200:
        readiness_before = payload.get("report") or {}

    results = []
    failures = []

    with tempfile.TemporaryDirectory(prefix="synthetic-readiness-") as temp_dir:
        temp_root = Path(temp_dir)
        for case in cases:
            file_path = materialize_case(case, repo_root=repo_root, temp_root=temp_root)
            status_code, response = upload_case(args.api_base, token, file_path)
            result = {
                "id": case["id"],
                "filename": file_path.name,
                "status_code": status_code,
                "primary_label": ((response.get("record") or {}).get("classification") or {}).get("primary_label"),
                "secondary_labels": ((response.get("record") or {}).get("classification") or {}).get("secondary_labels") or [],
                "ok": response.get("ok") is True,
                "response": response,
            }
            try:
                assert_case(case, response)
            except AssertionError as exc:
                result["assertion_error"] = str(exc)
                failures.append({"id": case["id"], "error": str(exc)})
            results.append(result)

    readiness_after = {}
    if args.wait_for_shadow:
        readiness_payload = poll_readiness(
            args.api_base,
            token,
            initial_reviewed_rows=int(readiness_before.get("teacher_reviewed_rows", 0) or 0),
            expected_new_rows=len(results),
            timeout_seconds=args.wait_timeout,
            poll_interval_seconds=args.wait_poll,
        )
        readiness_after = readiness_payload.get("report") or {}

    summary = {
        "suite_name": suite.get("suite_name"),
        "api_base": args.api_base,
        "case_count": len(results),
        "passed_count": len(results) - len(failures),
        "failed_count": len(failures),
        "observed_primary_labels": sorted({str(item.get("primary_label")) for item in results if item.get("primary_label")}),
        "observed_extensions": sorted({Path(item["filename"]).suffix.lower() for item in results}),
        "readiness_before": readiness_before,
        "readiness_after": readiness_after,
        "failures": failures,
        "results": results,
    }

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(json.dumps({
        "suite_name": summary["suite_name"],
        "case_count": summary["case_count"],
        "passed_count": summary["passed_count"],
        "failed_count": summary["failed_count"],
        "observed_primary_labels": summary["observed_primary_labels"],
        "observed_extensions": summary["observed_extensions"],
        "readiness_after": summary["readiness_after"],
    }, indent=2, ensure_ascii=False))

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
