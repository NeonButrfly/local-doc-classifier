#!/usr/bin/env python3
import json
import os
import re
import subprocess
import sys
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests
from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from category_manager import load_categories, load_groups

APP = FastAPI(title="Local Document Classifier API", version="1.0.0")

API_TOKEN = os.environ.get("CLASSIFIER_API_TOKEN", "")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://ollama:11434")
INPUT_ROOT = Path("/input/api").resolve()
OUTPUT_ROOT = Path("/output").resolve()
VAULT_ROOT = Path("/vault").resolve()
MANIFEST_PATH = OUTPUT_ROOT / "manifest.jsonl"
INDEX_PATH = VAULT_ROOT / "Classification Index.md"
CLASSIFIER_SCRIPT = Path("/app/classify-to-obsidian.py")

LOCK = threading.Lock()

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

@APP.get("/health")
def health(x_api_key: Optional[str] = Header(default=None)):
    check_token(x_api_key)

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
    x_api_key: Optional[str] = Header(default=None),
):
    check_token(x_api_key)

    original_name = safe_filename(file.filename or "upload.bin")
    ext = Path(original_name).suffix.lower()

    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=415, detail=f"Unsupported extension: {ext}")

    INPUT_ROOT.mkdir(parents=True, exist_ok=True)
    staged_name = f"{uuid.uuid4().hex}-{original_name}"
    staged_path = ensure_inside(INPUT_ROOT / staged_name, INPUT_ROOT)

    with staged_path.open("wb") as out:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)

    cmd = [
        sys.executable,
        str(CLASSIFIER_SCRIPT),
        str(staged_path),
        "--vault",
        str(VAULT_ROOT),
        "--output",
        str(OUTPUT_ROOT),
    ]

    if attach_originals:
        cmd.append("--attach-originals")

    if no_vision:
        cmd.append("--no-vision")

    if categories:
        cmd.extend(["--categories", categories])

    with LOCK:
        proc = subprocess.run(
            cmd,
            cwd="/app",
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=1800,
        )

    record = read_manifest_for_source(str(staged_path))

    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "staged_path": str(staged_path),
        "manifest": str(MANIFEST_PATH),
        "classification_index": str(INDEX_PATH),
        "record": record,
        "stdout_tail": tail_text(proc.stdout),
        "stderr_tail": tail_text(proc.stderr),
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
