#!/usr/bin/env python3
import json
import re
from pathlib import Path

import joblib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

APP_DIR = Path("/opt/local-doc-classifier")
CONFIG_DIR = APP_DIR / "config"
FULL_CATEGORIES = CONFIG_DIR / "categories.full.txt"
LOCAL_CATEGORIES = CONFIG_DIR / "categories.local.txt"
GROUPS_FILE = CONFIG_DIR / "category-groups.json"
CORRECTIONS_FILE = CONFIG_DIR / "corrections.jsonl"
MODEL_PATH = CONFIG_DIR / "taxonomy-router.joblib"
REPORT_PATH = CONFIG_DIR / "taxonomy-router-report.json"

def clean_label(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9._/ -]", " ", value)
    value = re.sub(r"\s+", "-", value)
    return value.strip("-")

def load_lines(path: Path):
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        label = clean_label(line)
        if label:
            out.append(label)
    return list(dict.fromkeys(out))

def load_groups():
    if GROUPS_FILE.exists():
        try:
            return json.loads(GROUPS_FILE.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            pass
    return {}

def load_corrections():
    if not CORRECTIONS_FILE.exists():
        return []
    rows = []
    for line in CORRECTIONS_FILE.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            item = json.loads(line)
            if isinstance(item, dict):
                rows.append(item)
        except Exception:
            pass
    return rows

def label_words(label: str) -> str:
    return label.replace("-", " ").replace("/", " ").replace("_", " ")

def examples_for_label(label: str):
    words = label_words(label)
    examples = [
        label,
        words,
        f"classification category {words}",
        f"file label {words}",
    ]

    if any(k in label for k in ["receipt", "invoice", "reimbursement", "financial", "tax", "claim", "fsa", "hsa"]):
        examples += [
            f"receipt invoice vendor total payment order reimbursement claim {words}",
            f"financial fsa hsa benefits claim receipt sunscreen spf medical expense {words}",
        ]

    if any(k in label for k in ["legal", "contract", "policy", "law", "regulation"]):
        examples += [
            f"legal contract policy regulation agreement terms clause {words}",
        ]

    if any(k in label for k in ["medical", "pharmacy", "prescription", "health"]):
        examples += [
            f"medical healthcare pharmacy prescription insurance patient clinic medication {words}",
        ]

    if any(k in label for k in ["reference", "concept", "environment", "game", "architecture", "industrial", "sci-fi", "snow", "facility", "waystation", "post-apocalyptic"]):
        examples += [
            f"image reference concept art environment game architecture industrial sci fi snow facility waystation {words}",
            f"visual reference frozen industrial exterior machinery facility not document not receipt {words}",
        ]

    if any(k in label for k in ["screenshot", "ui", "terminal", "source-code", "diagram"]):
        examples += [
            f"screenshot user interface terminal error code console technical diagram {words}",
        ]

    if any(k in label for k in ["product", "photo", "shopping"]):
        examples += [
            f"product photo retail item packaging object shopping catalog {words}",
        ]

    return examples

def main():
    categories = load_lines(FULL_CATEGORIES) or load_lines(LOCAL_CATEGORIES)
    groups = load_groups()
    corrections = load_corrections()

    if not categories:
        raise SystemExit("No categories found. Run taxonomy sync first.")

    texts = []
    labels = []

    for label in categories:
        for text in examples_for_label(label):
            texts.append(text)
            labels.append(label)

    for group_name, group_labels in groups.items():
        for label in group_labels:
            label = clean_label(str(label))
            if not label:
                continue
            texts.append(f"{group_name} {label_words(label)}")
            labels.append(label)

    for c in corrections:
        correct = clean_label(str(c.get("correct_label", "")))
        if not correct:
            continue
        filename = str(c.get("filename", ""))
        note = str(c.get("note", ""))
        summary = str(c.get("summary", ""))
        secondary = " ".join(map(str, c.get("secondary_labels", [])))
        old_label = str(c.get("old_label", ""))
        sample = f"{filename} {note} {summary} secondary {secondary} old {old_label}"
        texts.append(sample)
        labels.append(correct)

    vectorizer = TfidfVectorizer(
        lowercase=True,
        analyzer="word",
        ngram_range=(1, 2),
        max_features=60000,
        min_df=1,
        sublinear_tf=True,
        norm="l2",
        dtype=np.float32,
    )

    matrix = vectorizer.fit_transform(texts)

    model = {
        "kind": "tfidf_label_index",
        "vectorizer": vectorizer,
        "matrix": matrix,
        "labels": labels,
    }

    joblib.dump(model, MODEL_PATH, compress=3)

    report = {
        "ok": True,
        "kind": "tfidf_label_index",
        "category_count": len(set(labels)),
        "training_rows": len(texts),
        "features": len(vectorizer.vocabulary_),
        "corrections_used": len(corrections),
        "model_path": str(MODEL_PATH),
    }

    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    main()
