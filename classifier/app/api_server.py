#!/usr/bin/env python3
import json
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests
from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from category_manager import load_categories, load_groups
from hybrid_runtime import READINESS_REPORT_PATH, load_json

APP = FastAPI(title="Local Document Classifier API", version="1.0.0")

API_TOKEN = os.environ.get("CLASSIFIER_API_TOKEN", "")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://ollama:11434")
INPUT_ROOT = Path("/input/api").resolve()
OUTPUT_ROOT = Path("/output").resolve()
VAULT_ROOT = Path("/vault").resolve()
MANIFEST_PATH = OUTPUT_ROOT / "manifest.jsonl"
INDEX_PATH = VAULT_ROOT / "Classification Index.md"
CLASSIFIER_SCRIPT = Path("/app/classify-to-obsidian.py")
SHADOW_WORKER_ENABLED = os.environ.get("ENABLE_SHADOW_WORKER", "1") != "0"
SHADOW_WORKER_INTERVAL_SECONDS = int(os.environ.get("SHADOW_WORKER_INTERVAL_SECONDS", "15"))

REQUEST_LOCK = threading.Lock()
SHADOW_WORKER_STARTED = False

SUPPORTED_EXTENSIONS = {
    ".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt",
    ".txt", ".md", ".markdown", ".csv", ".html", ".htm",
    ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"
}

def check_token(x_api_key: Optional[str]) -> None:
    if API_TOKEN and x_api_key != API_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")

def safe_filename(name: str) -> str:
    base = Path(name or "upload.bin").name
    base = re.sub(r"[^A-Za-z0-9._ -]+", "_", base).strip()
    return base[:160] or "upload.bin"

def ensure_inside(path: Path, root: Path) -> Path:
    resolved = path.resolve()
    if resolved != root and root not in resolved.parents:
        raise HTTPException(status_code=400, detail="Path outside allowed root")
    return resolved

def read_manifest_for_source(source_path: str):
    if not MANIFEST_PATH.exists():
        return None

    try:
        lines = MANIFEST_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return None

    for line in reversed(lines):
        try:
            record = json.loads(line)
        except Exception:
            continue

        if record.get("source_path") == source_path:
            return record

    return None

def tail_text(value: str, max_chars: int = 8000) -> str:
    if value is None:
        return ""
    return value[-max_chars:]

def elapsed_ms(started_at: float) -> float:
    return round((time.perf_counter() - started_at) * 1000, 3)

def load_worker_timing(path: Path) -> Optional[dict]:
    if not path.exists():
        return None

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    finally:
        try:
            path.unlink()
        except Exception:
            pass


def run_shadow_worker_cycle() -> None:
    cmd = [
        sys.executable,
        str(CLASSIFIER_SCRIPT),
        "--vault",
        str(VAULT_ROOT),
        "--output",
        str(OUTPUT_ROOT),
        "--process-shadow-queue",
    ]
    subprocess.run(
        cmd,
        cwd="/app",
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=1800,
    )


def shadow_worker_loop() -> None:
    while True:
        try:
            run_shadow_worker_cycle()
        except Exception:
            pass
        time.sleep(SHADOW_WORKER_INTERVAL_SECONDS)


def maybe_start_shadow_worker() -> None:
    global SHADOW_WORKER_STARTED
    if SHADOW_WORKER_STARTED:
        return
    if not SHADOW_WORKER_ENABLED:
        return
    if not CLASSIFIER_SCRIPT.exists():
        return
    if not Path("/app").exists():
        return
    thread = threading.Thread(target=shadow_worker_loop, name="shadow-worker", daemon=True)
    thread.start()
    SHADOW_WORKER_STARTED = True

async def stage_uploaded_file(file: UploadFile) -> dict:
    original_name = safe_filename(file.filename or "upload.bin")
    ext = Path(original_name).suffix.lower()

    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=415, detail=f"Unsupported extension: {ext}")

    INPUT_ROOT.mkdir(parents=True, exist_ok=True)
    staged_name = f"{uuid.uuid4().hex}-{original_name}"
    staged_path = ensure_inside(INPUT_ROOT / staged_name, INPUT_ROOT)

    bytes_received = 0
    upload_started_at = time.perf_counter()

    with staged_path.open("wb") as out:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)
            bytes_received += len(chunk)

    upload_ms = elapsed_ms(upload_started_at)
    upload_bytes_per_sec = round(bytes_received / (upload_ms / 1000), 3) if upload_ms > 0 else None

    return {
        "filename": original_name,
        "extension": ext,
        "staged_path": staged_path,
        "bytes_received": bytes_received,
        "upload_ms": upload_ms,
        "upload_bytes_per_sec": upload_bytes_per_sec,
    }

@APP.get("/health")
def health(x_api_key: Optional[str] = Header(default=None)):
    check_token(x_api_key)
    maybe_start_shadow_worker()

    INPUT_ROOT.mkdir(parents=True, exist_ok=True)
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    VAULT_ROOT.mkdir(parents=True, exist_ok=True)

    ollama_ok = False
    ollama_error = None

    try:
        response = requests.get(f"{OLLAMA_URL.rstrip('/')}/api/tags", timeout=5)
        ollama_ok = response.ok
        if not response.ok:
            ollama_error = f"HTTP {response.status_code}"
    except Exception as e:
        ollama_error = str(e)

    return {
        "ok": ollama_ok and CLASSIFIER_SCRIPT.exists(),
        "ollama_ok": ollama_ok,
        "ollama_error": ollama_error,
        "ollama_url": OLLAMA_URL,
        "input_root": str(INPUT_ROOT),
        "output_root": str(OUTPUT_ROOT),
        "vault_root": str(VAULT_ROOT),
        "classification_index": str(INDEX_PATH),
        "manifest": str(MANIFEST_PATH),
        "classifier_script_exists": CLASSIFIER_SCRIPT.exists(),
        "category_count": len(load_categories()),
    }

@APP.post("/classify/upload")
async def classify_upload(
    file: UploadFile = File(...),
    categories: Optional[str] = Form(default=None),
    attach_originals: bool = Form(default=True),
    no_vision: bool = Form(default=False),
    ingestion_mode: str = Form(default="adhoc"),
    canonical_source_path: Optional[str] = Form(default=None),
    canonical_source_hash: Optional[str] = Form(default=None),
    last_seen_filename: Optional[str] = Form(default=None),
    x_api_key: Optional[str] = Header(default=None),
):
    check_token(x_api_key)
    maybe_start_shadow_worker()
    if ingestion_mode == "real-folder":
        readiness = load_json(READINESS_REPORT_PATH, default={}) or {}
        if not readiness.get("real_ingestion_allowed"):
            reason = ", ".join(readiness.get("warnings", []) or ["readiness-report-missing-or-blocked"])
            raise HTTPException(
                status_code=409,
                detail=f"Real-folder ingestion is blocked until readiness thresholds pass and allow_real_ingestion is enabled: {reason}",
            )
    total_started_at = time.perf_counter()
    staged = await stage_uploaded_file(file)
    staged_path = staged["staged_path"]
    timing_output = ensure_inside(OUTPUT_ROOT / "_timing" / f"{uuid.uuid4().hex}.json", OUTPUT_ROOT)
    timing_output.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        str(CLASSIFIER_SCRIPT),
        str(staged_path),
        "--vault",
        str(VAULT_ROOT),
        "--output",
        str(OUTPUT_ROOT),
        "--timing-output",
        str(timing_output),
    ]

    if attach_originals:
        cmd.append("--attach-originals")

    if no_vision:
        cmd.append("--no-vision")

    if categories:
        cmd.extend(["--categories", categories])
    if canonical_source_path:
        cmd.extend(["--canonical-source-path", canonical_source_path])
    if canonical_source_hash:
        cmd.extend(["--canonical-source-hash", canonical_source_hash])
    if last_seen_filename:
        cmd.extend(["--last-seen-filename", last_seen_filename])

    classify_started_at = time.perf_counter()
    with REQUEST_LOCK:
        proc = subprocess.run(
            cmd,
            cwd="/app",
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=1800,
        )
    classify_ms = elapsed_ms(classify_started_at)
    worker_timing = load_worker_timing(timing_output)

    record = read_manifest_for_source(str(staged_path))

    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "filename": staged["filename"],
        "staged_path": str(staged_path),
        "bytes_received": staged["bytes_received"],
        "upload_ms": staged["upload_ms"],
        "upload_bytes_per_sec": staged["upload_bytes_per_sec"],
        "classify_ms": classify_ms,
        "total_ms": elapsed_ms(total_started_at),
        "worker_timing": worker_timing,
        "manifest": str(MANIFEST_PATH),
        "classification_index": str(INDEX_PATH),
        "ingestion_mode": ingestion_mode,
        "record": record,
        "stdout_tail": tail_text(proc.stdout),
        "stderr_tail": tail_text(proc.stderr),
    }

@APP.get("/readiness")
def get_readiness(x_api_key: Optional[str] = Header(default=None)):
    check_token(x_api_key)
    report = load_json(READINESS_REPORT_PATH, default={}) or {}
    return {
        "ok": True,
        "readiness_path": str(READINESS_REPORT_PATH),
        "report": report,
    }

@APP.post("/benchmark/upload-only")
async def benchmark_upload_only(
    file: UploadFile = File(...),
    cleanup: bool = Form(default=True),
    x_api_key: Optional[str] = Header(default=None),
):
    check_token(x_api_key)
    total_started_at = time.perf_counter()
    staged = await stage_uploaded_file(file)
    staged_path = staged["staged_path"]

    if cleanup and staged_path.exists():
        staged_path.unlink()

    return {
        "ok": True,
        "filename": staged["filename"],
        "extension": staged["extension"],
        "staged_path": str(staged_path),
        "bytes_received": staged["bytes_received"],
        "upload_ms": staged["upload_ms"],
        "upload_bytes_per_sec": staged["upload_bytes_per_sec"],
        "cleanup": cleanup,
        "staged_file_exists_after_response": staged_path.exists(),
        "total_ms": elapsed_ms(total_started_at),
    }

@APP.get("/index", response_class=PlainTextResponse)
def get_index(max_chars: int = 30000, x_api_key: Optional[str] = Header(default=None)):
    check_token(x_api_key)

    if not INDEX_PATH.exists():
        raise HTTPException(status_code=404, detail="Classification Index.md not found")

    text = INDEX_PATH.read_text(encoding="utf-8", errors="replace")
    return text[:max_chars]

@APP.get("/note", response_class=PlainTextResponse)
def get_note(path: str, max_chars: int = 30000, x_api_key: Optional[str] = Header(default=None)):
    check_token(x_api_key)

    candidate = ensure_inside(VAULT_ROOT / path, VAULT_ROOT)

    if not candidate.exists() or not candidate.is_file():
        raise HTTPException(status_code=404, detail="Markdown note not found")

    text = candidate.read_text(encoding="utf-8", errors="replace")
    return text[:max_chars]

@APP.get("/recent")
def recent(limit: int = 20, x_api_key: Optional[str] = Header(default=None)):
    check_token(x_api_key)

    if not MANIFEST_PATH.exists():
        return {
            "ok": True,
            "records": [],
            "manifest": str(MANIFEST_PATH),
        }

    lines = MANIFEST_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
    records = []

    for line in lines[-max(1, limit * 5):]:
        try:
            records.append(json.loads(line))
        except Exception:
            pass

    return {
        "ok": True,
        "records": records[-limit:],
        "manifest": str(MANIFEST_PATH),
        "classification_index": str(INDEX_PATH),
    }

@APP.get("/categories")
def get_categories(x_api_key: Optional[str] = Header(default=None)):
    check_token(x_api_key)
    categories = load_categories()
    return {
        "ok": True,
        "categories_file": "/config/categories.txt",
        "category_count": len(categories),
        "categories": categories,
        "groups_file": "/config/category-groups.json",
        "groups": load_groups(),
    }

class CorrectionRecord(BaseModel):
    filename: str = ""
    extension: str = ""
    kind: str = ""
    old_label: str = ""
    correct_label: str
    secondary_labels: list[str] = []
    note: str = ""
    summary: str = ""

@APP.get("/corrections")
def get_corrections(limit: int = 50, x_api_key: Optional[str] = Header(default=None)):
    check_token(x_api_key)

    path = Path("/config/corrections.jsonl")
    if not path.exists():
        return {"ok": True, "records": [], "path": str(path)}

    records = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]:
        try:
            records.append(json.loads(line))
        except Exception:
            pass

    return {"ok": True, "records": records, "path": str(path)}

@APP.post("/corrections")
def add_correction(record: CorrectionRecord, x_api_key: Optional[str] = Header(default=None)):
    check_token(x_api_key)

    path = Path("/config/corrections.jsonl")
    path.parent.mkdir(parents=True, exist_ok=True)

    data = record.model_dump()
    data["recorded_at"] = datetime.now().astimezone().isoformat(timespec="seconds")

    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False) + "\n")

    return {"ok": True, "record": data, "path": str(path)}
