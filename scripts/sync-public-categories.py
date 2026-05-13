#!/usr/bin/env python3
import csv
import json
import re
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Iterable, List

APP_DIR = Path("/opt/local-doc-classifier")
CONFIG_DIR = APP_DIR / "config"
CACHE_DIR = CONFIG_DIR / "taxonomy-cache"

SOURCES_FILE = CONFIG_DIR / "taxonomy-sources.json"
LOCAL_FILE = CONFIG_DIR / "categories.local.txt"
ACTIVE_FILE = CONFIG_DIR / "categories.txt"
FULL_FILE = CONFIG_DIR / "categories.full.txt"
PUBLIC_CLEAN_FILE = CONFIG_DIR / "categories.public.clean.txt"
REPORT_FILE = CONFIG_DIR / "taxonomy-sync-report.json"

PUBLIC_PROMPT_CAP = 1000
DOWNLOAD_TIMEOUT = 45

PRIORITY_ALWAYS = [
    "receipt", "invoice", "reimbursement-packet", "legal", "medical",
    "insurance", "tax", "financial", "identity-document", "fsa", "hsa",
    "sunscreen", "spf-product", "cosmetic-spf", "reference-image",
    "concept-art", "environment-art", "game-reference", "architecture",
    "industrial", "sci-fi", "snow-ice", "frozen-environment",
    "post-apocalyptic", "waystation", "facility", "screenshot",
    "product-photo", "image-only", "unknown", "needs-review"
]

def clean_label(value: str) -> str:
    value = value.strip()
    value = value.split("#", 1)[0].strip()
    value = value.replace("&", " and ")
    value = re.sub(r"\([^)]*\)", " ", value)
    value = value.lower()
    value = re.sub(r"[^a-z0-9._/ -]", " ", value)
    value = re.sub(r"\s+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value

def valid_label(value: str) -> bool:
    if not value:
        return False
    if value in {"the", "and", "or", "other", "misc", "miscellaneous", "none", "null"}:
        return False
    return bool(re.match(r"^[a-z0-9][a-z0-9._/-]{1,80}$", value))

def unique(items: Iterable[str]) -> List[str]:
    out = []
    seen = set()
    for item in items:
        label = clean_label(item)
        if valid_label(label) and label not in seen:
            seen.add(label)
            out.append(label)
    return out

def read_local_categories() -> List[str]:
    if not LOCAL_FILE.exists():
        return []
    return unique(LOCAL_FILE.read_text(encoding="utf-8", errors="replace").splitlines())

def download_text(url: str, cache_path: Path) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "local-doc-classifier-taxonomy-sync/1.0"})
    with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT) as response:
        raw = response.read()
    text = raw.decode("utf-8", errors="replace")
    cache_path.write_text(text, encoding="utf-8")
    return text

def parse_csv_last_column(text: str) -> List[str]:
    labels = []
    for row in csv.reader(text.splitlines()):
        if not row:
            continue
        labels.append(row[-1])
    return unique(labels)

def parse_google_product_taxonomy(text: str) -> List[str]:
    labels = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split(">")]
        if parts:
            labels.append(parts[-1])
            if len(parts) >= 2:
                labels.append(" / ".join(parts[-2:]))
    return unique(labels)

def parse_iab_tsv(text: str) -> List[str]:
    labels = []
    lines = text.splitlines()

    for line in lines:
        if not line.strip():
            continue

        fields = [x.strip() for x in line.split("\t")] if "\t" in line else re.split(r"\s{2,}", line.strip())

        for field in fields:
            f = field.strip()
            if not f:
                continue
            if f.lower() in {
                "unique id", "parent", "name", "tier 1", "tier 2", "tier 3", "tier 4",
                "relational id system content taxonomy v3.1 tiered categories extension"
            }:
                continue
            if re.fullmatch(r"[0-9]+", f):
                continue
            labels.append(f)

    return unique(labels)

def parse_source(source: dict, text: str) -> List[str]:
    parser = source.get("parser")
    if parser == "csv_last_column":
        return parse_csv_last_column(text)
    if parser == "google_product_taxonomy":
        return parse_google_product_taxonomy(text)
    if parser == "iab_tsv":
        return parse_iab_tsv(text)
    if parser == "static":
        return unique(source.get("labels", []))
    return []

def load_sources() -> list[dict]:
    return json.loads(SOURCES_FILE.read_text(encoding="utf-8"))

def main() -> int:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    local_categories = read_local_categories()
    sources = load_sources()

    public_all = []
    source_reports = []

    for source in sources:
        name = source.get("name", "unknown")
        enabled = bool(source.get("enabled", True))
        max_labels = int(source.get("max_labels", 500))

        if not enabled:
            source_reports.append({"name": name, "enabled": False, "count": 0})
            continue

        started = time.time()
        labels = []
        error = None

        try:
            if source.get("parser") == "static":
                labels = parse_source(source, "")
            else:
                url = source["url"]
                cache_path = CACHE_DIR / f"{name}.raw"
                text = download_text(url, cache_path)
                labels = parse_source(source, text)

            if max_labels > 0:
                labels = labels[:max_labels]

            (CACHE_DIR / f"{name}.labels.txt").write_text("\n".join(labels) + "\n", encoding="utf-8")
            public_all.extend(labels)

        except Exception as exc:
            error = str(exc)
            cached_labels = CACHE_DIR / f"{name}.labels.txt"
            if cached_labels.exists():
                labels = unique(cached_labels.read_text(encoding="utf-8", errors="replace").splitlines())
                public_all.extend(labels)
            else:
                labels = []

        source_reports.append({
            "name": name,
            "enabled": enabled,
            "count": len(labels),
            "error": error,
            "seconds": round(time.time() - started, 2),
        })

    public_clean = unique(public_all)
    full = unique(local_categories + public_clean)
    FULL_FILE.write_text("\n".join(full) + "\n", encoding="utf-8")
    PUBLIC_CLEAN_FILE.write_text("\n".join(public_clean) + "\n", encoding="utf-8")

    active_seed = unique(local_categories + PRIORITY_ALWAYS)

    active = []
    seen = set()

    for label in active_seed:
        if label not in seen:
            seen.add(label)
            active.append(label)

    for label in public_clean:
        if len(active) >= len(active_seed) + PUBLIC_PROMPT_CAP:
            break
        if label not in seen:
            seen.add(label)
            active.append(label)

    if not active:
        print("[ERROR] Active category list is empty; refusing to overwrite.", file=sys.stderr)
        return 1

    ACTIVE_FILE.write_text("\n".join(active) + "\n", encoding="utf-8")

    report = {
        "ok": True,
        "synced_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "active_count": len(active),
        "full_count": len(full),
        "public_count": len(public_clean),
        "active_file": str(ACTIVE_FILE),
        "full_file": str(FULL_FILE),
        "public_clean_file": str(PUBLIC_CLEAN_FILE),
        "sources": source_reports,
    }
    REPORT_FILE.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(json.dumps(report, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
