import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import joblib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import LabelEncoder


CONFIG_DIR = Path("/config")
OUTPUT_ROOT = Path("/output")

HYBRID_GATING_PATH = CONFIG_DIR / "hybrid-gating.json"
HEURISTIC_RULES_PATH = CONFIG_DIR / "heuristic-rules.json"
LIGHTGBM_MODEL_PATH = CONFIG_DIR / "lightgbm-classifier.joblib"
LIGHTGBM_REPORT_PATH = CONFIG_DIR / "lightgbm-training-report.json"
SHADOW_QUEUE_DIR = OUTPUT_ROOT / "shadow-queue"
SHADOW_COMPARISONS_PATH = OUTPUT_ROOT / "shadow-comparisons.jsonl"
READINESS_REPORT_PATH = OUTPUT_ROOT / "readiness-report.json"
RETRAIN_DIR = OUTPUT_ROOT / "retrain"
MANIFEST_PATH = OUTPUT_ROOT / "manifest.jsonl"
CORRECTIONS_PATH = CONFIG_DIR / "corrections.jsonl"
EXAMPLES_PATH = CONFIG_DIR / "examples.jsonl"

DEFAULT_HYBRID_GATING = {
    "mode": "hybrid",
    "heuristic_fast_confidence": 0.92,
    "lightgbm_fast_confidence": 0.80,
    "aligned_soft_confidence": 0.60,
    "needs_llm_threshold": 0.45,
    "disagreement_risk_threshold": 0.35,
    "teacher_confidence_threshold": 0.85,
    "shadow_mode": "all",
    "shadow_sample_rate": 1.0,
    "auto_retrain_enabled": True,
    "auto_threshold_update_enabled": True,
    "auto_inline_disagreement_threshold": 3,
    "readiness_min_teacher_samples": 10,
    "readiness_min_unique_teacher_files": 10,
    "readiness_min_teacher_extensions": 6,
    "readiness_min_teacher_labels": 5,
    "readiness_min_teacher_agreement_rate": 0.80,
    "readiness_min_teacher_approval_rate": 0.70,
    "readiness_max_queue_depth": 25,
    "allow_real_ingestion": False,
}

DEFAULT_HEURISTIC_RULES = {
    "document_fast_path": {
        "legal_agreement_min_score": 6,
        "technical_incident_min_score": 6,
        "technical_report_min_score": 4,
    },
    "spreadsheet_fast_path": {
        "enabled": True,
    },
    "force_inline_llm_for": [],
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_hybrid_gating_config(path: Optional[Path] = None) -> Dict[str, Any]:
    merged = dict(DEFAULT_HYBRID_GATING)
    merged.update(load_json(path or HYBRID_GATING_PATH, default={}) or {})
    return merged


def load_heuristic_rules(path: Optional[Path] = None) -> Dict[str, Any]:
    merged = json.loads(json.dumps(DEFAULT_HEURISTIC_RULES))
    loaded = load_json(path or HEURISTIC_RULES_PATH, default={}) or {}
    for key, value in loaded.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key].update(value)
        else:
            merged[key] = value
    return merged


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def choose_live_decision(
    heuristic_result: Optional[Dict[str, Any]],
    lightgbm_result: Optional[Dict[str, Any]],
    gating_config: Dict[str, Any],
    candidate_categories: Optional[list[str]] = None,
) -> Dict[str, Any]:
    heuristic_result = heuristic_result or {}
    lightgbm_result = lightgbm_result or {}
    candidate_categories = candidate_categories or []

    heuristic_primary = str(heuristic_result.get("primary_label", "unknown") or "unknown")
    heuristic_confidence = float(heuristic_result.get("confidence", 0.0) or 0.0)
    model_primary = str(lightgbm_result.get("top_label", heuristic_primary) or heuristic_primary)
    model_confidence = float(lightgbm_result.get("top_probability", 0.0) or 0.0)
    needs_llm_probability = float(lightgbm_result.get("needs_llm_probability", 1.0) or 0.0)
    disagreement_risk = float(lightgbm_result.get("disagreement_risk", 1.0) or 0.0)

    aligned = heuristic_primary == model_primary
    heuristic_ready = heuristic_confidence >= float(gating_config["heuristic_fast_confidence"])
    model_ready = model_confidence >= float(gating_config["lightgbm_fast_confidence"])
    aligned_soft_ready = aligned and model_confidence >= float(gating_config.get("aligned_soft_confidence", 0.60))
    low_llm_need = needs_llm_probability < float(gating_config["needs_llm_threshold"])
    low_disagreement = disagreement_risk < float(gating_config["disagreement_risk_threshold"])
    strong_alignment = aligned and heuristic_ready and model_ready and low_disagreement
    soft_alignment = aligned and heuristic_ready and aligned_soft_ready and low_llm_need and low_disagreement

    if strong_alignment or soft_alignment:
        return {
            "use_inline_llm": False,
            "live_source": "heuristic-fast-path",
            "selected_primary_hint": heuristic_primary,
            "decision_reason": "fast-path-aligned",
            "candidate_count": len(candidate_categories),
            "heuristic_confidence": heuristic_confidence,
            "lightgbm_confidence": model_confidence,
            "needs_llm_probability": needs_llm_probability,
            "disagreement_risk": disagreement_risk,
        }

    return {
        "use_inline_llm": True,
        "live_source": "inline-llm",
        "selected_primary_hint": model_primary,
        "decision_reason": "model-required",
        "candidate_count": len(candidate_categories),
        "heuristic_confidence": heuristic_confidence,
        "lightgbm_confidence": model_confidence,
        "needs_llm_probability": needs_llm_probability,
        "disagreement_risk": disagreement_risk,
    }


def build_shadow_record(
    filename: str,
    extension: str,
    parser: Optional[str],
    heuristic_result: Optional[Dict[str, Any]],
    lightgbm_result: Optional[Dict[str, Any]],
    live_result: Optional[Dict[str, Any]],
    llm_result: Optional[Dict[str, Any]],
    taxonomy_candidates: list[str],
    text_preview: str,
    live_source: str = "",
) -> Dict[str, Any]:
    heuristic_result = heuristic_result or {}
    lightgbm_result = lightgbm_result or {}
    live_result = live_result or {}
    llm_result = llm_result or {}

    heuristic_primary = str(heuristic_result.get("primary_label", "unknown") or "unknown")
    lightgbm_primary = str(lightgbm_result.get("top_label", "unknown") or "unknown")
    live_primary = str(live_result.get("primary_label", "unknown") or "unknown")
    shadow_primary = str(llm_result.get("primary_label", "unknown") or "unknown")
    teacher_review = evaluate_teacher_result(
        llm_result=llm_result,
        taxonomy_candidates=taxonomy_candidates,
        live_result=live_result,
        gating_config=load_hybrid_gating_config(),
    )

    return {
        "recorded_at": utc_now(),
        "filename": filename,
        "extension": extension,
        "parser": parser,
        "heuristic_primary": heuristic_primary,
        "heuristic_confidence": heuristic_result.get("confidence"),
        "lightgbm_primary": lightgbm_primary,
        "lightgbm_confidence": lightgbm_result.get("top_probability"),
        "needs_llm_probability": lightgbm_result.get("needs_llm_probability"),
        "disagreement_risk": lightgbm_result.get("disagreement_risk"),
        "live_primary": live_primary,
        "live_source": live_source,
        "shadow_primary": shadow_primary,
        "shadow_confidence": llm_result.get("confidence"),
        "taxonomy_candidates": taxonomy_candidates,
        "disagreement": live_primary != shadow_primary,
        "teacher_review_status": teacher_review["review_status"],
        "teacher_reason": teacher_review["reason"],
        "teacher_approved_for_training": teacher_review["teacher_approved_for_training"],
        "teacher_supports_live_result": teacher_review["teacher_supports_live_result"],
        "teacher_suggests_correction": teacher_review["teacher_suggests_correction"],
        "text_preview": text_preview[:4000],
    }


def evaluate_teacher_result(
    llm_result: Optional[Dict[str, Any]],
    taxonomy_candidates: list[str],
    live_result: Optional[Dict[str, Any]],
    gating_config: Dict[str, Any],
) -> Dict[str, Any]:
    llm_result = llm_result or {}
    live_result = live_result or {}
    taxonomy_candidates = taxonomy_candidates or []

    teacher_primary = str(llm_result.get("primary_label", "unknown") or "unknown")
    live_primary = str(live_result.get("primary_label", "unknown") or "unknown")
    teacher_confidence = safe_float(llm_result.get("confidence"), 0.0)
    confidence_ok = teacher_confidence >= safe_float(gating_config.get("teacher_confidence_threshold"), 0.85)
    in_candidate_set = not taxonomy_candidates or teacher_primary in taxonomy_candidates
    supports_live = teacher_primary == live_primary
    suggests_correction = teacher_primary != live_primary and teacher_primary != "unknown"

    if not confidence_ok:
        return {
            "review_status": "teacher-low-confidence",
            "reason": "teacher-confidence-below-threshold",
            "teacher_approved_for_training": False,
            "teacher_supports_live_result": supports_live,
            "teacher_suggests_correction": False,
        }

    if not in_candidate_set:
        return {
            "review_status": "teacher-outside-candidates",
            "reason": "teacher-label-outside-taxonomy-candidates",
            "teacher_approved_for_training": False,
            "teacher_supports_live_result": False,
            "teacher_suggests_correction": False,
        }

    return {
        "review_status": "teacher-approved",
        "reason": "teacher-approved-for-training",
        "teacher_approved_for_training": True,
        "teacher_supports_live_result": supports_live,
        "teacher_suggests_correction": suggests_correction,
    }


def build_feature_text(payload: Dict[str, Any]) -> str:
    filename = str(payload.get("filename", ""))
    extension = str(payload.get("extension", ""))
    parser = str(payload.get("parser", ""))
    heuristic_primary = str(payload.get("heuristic_primary", ""))
    taxonomy_candidates = " ".join(map(str, payload.get("taxonomy_candidates", []) or []))
    text_preview = str(payload.get("text_preview", ""))[:12000]
    return " ".join(
        [
            filename,
            extension,
            parser,
            f"heuristic {heuristic_primary}",
            f"taxonomy {taxonomy_candidates}",
            text_preview,
        ]
    ).strip()


def _train_binary_model(matrix, values):
    unique = sorted(set(int(v) for v in values))
    if len(unique) <= 1:
        return {"kind": "constant", "value": float(unique[0] if unique else 0)}

    import lightgbm as lgb

    model = lgb.LGBMClassifier(
        objective="binary",
        n_estimators=40,
        num_leaves=15,
        min_data_in_leaf=1,
        random_state=7,
        verbose=-1,
    )
    model.fit(matrix, np.array(values, dtype=np.int32))
    return {"kind": "lightgbm", "model": model}


def _predict_binary_model(model_artifact, matrix) -> float:
    if model_artifact.get("kind") == "constant":
        return float(model_artifact.get("value", 0.0))
    model = model_artifact["model"]
    probabilities = model.predict_proba(matrix)[0]
    return float(probabilities[1] if len(probabilities) > 1 else probabilities[0])


def train_lightgbm_model(
    training_rows: list[Dict[str, Any]],
    model_path: Path,
    report_path: Path,
) -> Dict[str, Any]:
    rows = [row for row in training_rows if row.get("accepted_primary")]
    if not rows:
        raise ValueError("No training rows with accepted_primary available.")

    texts = [build_feature_text(row) for row in rows]
    labels = [str(row["accepted_primary"]) for row in rows]
    needs_llm_targets = [1 if row.get("used_inline_llm") else 0 for row in rows]
    disagreement_targets = [1 if row.get("disagreement") else 0 for row in rows]

    vectorizer = TfidfVectorizer(
        lowercase=True,
        analyzer="word",
        ngram_range=(1, 2),
        max_features=12000,
        min_df=1,
        sublinear_tf=True,
        norm="l2",
        dtype=np.float32,
    )
    matrix = vectorizer.fit_transform(texts)

    label_encoder = LabelEncoder()
    y = label_encoder.fit_transform(labels)

    import lightgbm as lgb

    label_model = lgb.LGBMClassifier(
        objective="multiclass",
        n_estimators=60,
        num_leaves=15,
        min_data_in_leaf=1,
        random_state=7,
        verbose=-1,
    )
    label_model.fit(matrix, y)

    model_artifact = {
        "kind": "hybrid-lightgbm-v1",
        "vectorizer": vectorizer,
        "label_encoder": label_encoder,
        "label_model": label_model,
        "needs_llm_model": _train_binary_model(matrix, needs_llm_targets),
        "disagreement_model": _train_binary_model(matrix, disagreement_targets),
        "trained_at": utc_now(),
        "training_rows": len(rows),
    }
    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model_artifact, model_path, compress=3)

    report = {
        "ok": True,
        "kind": model_artifact["kind"],
        "trained_at": model_artifact["trained_at"],
        "training_rows": len(rows),
        "class_count": len(label_encoder.classes_),
        "features": len(vectorizer.vocabulary_),
        "model_path": str(model_path),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def predict_lightgbm_result(payload: Dict[str, Any], model_path: Path) -> Dict[str, Any]:
    model_artifact = joblib.load(model_path)
    matrix = model_artifact["vectorizer"].transform([build_feature_text(payload)])
    probabilities = model_artifact["label_model"].predict_proba(matrix)[0]
    classes = model_artifact["label_encoder"].classes_
    order = np.argsort(probabilities)[::-1]
    top_labels = [str(classes[idx]) for idx in order[:5]]
    top_label = top_labels[0] if top_labels else "unknown"
    top_probability = float(probabilities[order[0]]) if len(order) else 0.0

    return {
        "top_label": top_label,
        "top_probability": top_probability,
        "top_labels": top_labels,
        "label_probabilities": {
            str(classes[idx]): float(probabilities[idx])
            for idx in order[: min(10, len(order))]
        },
        "needs_llm_probability": _predict_binary_model(model_artifact["needs_llm_model"], matrix),
        "disagreement_risk": _predict_binary_model(model_artifact["disagreement_model"], matrix),
    }


def enqueue_shadow_job(payload: Dict[str, Any], queue_dir: Path = SHADOW_QUEUE_DIR) -> Path:
    queue_dir.mkdir(parents=True, exist_ok=True)
    job_path = queue_dir / f"{utc_now().replace(':', '-')}-{uuid.uuid4().hex}.json"
    save_json(job_path, payload)
    return job_path


def append_jsonl(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def read_jsonl(path: Path, limit: Optional[int] = None) -> list[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[Dict[str, Any]] = []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if limit is not None:
        lines = lines[-limit:]
    for line in lines:
        try:
            item = json.loads(line)
        except Exception:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def process_shadow_queue_once(
    queue_dir: Path = SHADOW_QUEUE_DIR,
    comparisons_path: Path = SHADOW_COMPARISONS_PATH,
    shadow_classifier=None,
) -> int:
    if shadow_classifier is None:
        return 0

    processed = 0
    for job_path in sorted(queue_dir.glob("*.json")):
        job = load_json(job_path, default={}) or {}
        llm_result = shadow_classifier(job)
        comparison = build_shadow_record(
            filename=str(job.get("filename", "")),
            extension=str(job.get("extension", "")),
            parser=job.get("parser"),
            heuristic_result=job.get("heuristic_result"),
            lightgbm_result=job.get("lightgbm_result"),
            live_result=job.get("live_result"),
            llm_result=llm_result,
            taxonomy_candidates=job.get("taxonomy_candidates", []) or [],
            text_preview=str(job.get("text_preview", "")),
            live_source=str(job.get("live_source", "")),
        )
        append_jsonl(comparisons_path, comparison)
        try:
            job_path.unlink()
        except Exception:
            pass
        processed += 1
    return processed


def apply_disagreement_updates(
    comparisons: list[Dict[str, Any]],
    gating_path: Path = HYBRID_GATING_PATH,
    rules_path: Path = HEURISTIC_RULES_PATH,
) -> Dict[str, Any]:
    gating = load_hybrid_gating_config(gating_path)
    rules = load_heuristic_rules(rules_path)
    threshold = int(gating.get("auto_inline_disagreement_threshold", 3))

    counts: Dict[str, int] = {}
    for item in comparisons:
        if not item.get("disagreement"):
            continue
        key = f"{item.get('parser', 'unknown')}|{item.get('heuristic_primary', 'unknown')}"
        counts[key] = counts.get(key, 0) + 1

    forced = set(rules.get("force_inline_llm_for", []) or [])
    updated = False

    for key, count in counts.items():
        if count >= threshold and key not in forced:
            forced.add(key)
            updated = True

    if updated:
        rules["force_inline_llm_for"] = sorted(forced)
        gating["heuristic_fast_confidence"] = max(
            0.75,
            round(float(gating["heuristic_fast_confidence"]) - 0.02, 4),
        )
        save_json(gating_path, gating)
        save_json(rules_path, rules)

    return {
        "updated": updated,
        "forced_rule_count": len(forced),
        "heuristic_fast_confidence": gating["heuristic_fast_confidence"],
    }


def maybe_retrain_from_shadow_data(
    comparisons_path: Path = SHADOW_COMPARISONS_PATH,
    model_path: Path = LIGHTGBM_MODEL_PATH,
    report_path: Path = LIGHTGBM_REPORT_PATH,
    min_rows: int = 25,
) -> Dict[str, Any]:
    comparisons = []
    if comparisons_path.exists():
        for line in comparisons_path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                item = json.loads(line)
            except Exception:
                continue
            if isinstance(item, dict):
                comparisons.append(item)

    approved = [row for row in comparisons if row.get("teacher_approved_for_training")]
    if len(approved) < min_rows:
        return {
            "retrained": False,
            "training_rows": len(approved),
            "teacher_approved_rows": len(approved),
        }

    training_rows = []
    for row in approved:
        training_rows.append(
            {
                "filename": row.get("filename", ""),
                "extension": row.get("extension", ""),
                "parser": row.get("parser", ""),
                "text_preview": row.get("text_preview", ""),
                "heuristic_primary": row.get("heuristic_primary", "unknown"),
                "taxonomy_candidates": row.get("taxonomy_candidates", []),
                "accepted_primary": row.get("shadow_primary") or row.get("live_primary") or row.get("heuristic_primary") or "unknown",
                "used_inline_llm": True,
                "disagreement": bool(row.get("disagreement")),
            }
        )

    report = train_lightgbm_model(
        training_rows=training_rows,
        model_path=model_path,
        report_path=report_path,
    )
    return {
        "retrained": True,
        "training_rows": len(training_rows),
        "teacher_approved_rows": len(approved),
        "report": report,
    }


def build_training_rows_from_runtime(
    manifest_path: Path = MANIFEST_PATH,
    corrections_path: Path = CORRECTIONS_PATH,
    examples_path: Path = EXAMPLES_PATH,
    comparisons_path: Path = SHADOW_COMPARISONS_PATH,
) -> list[Dict[str, Any]]:
    rows: list[Dict[str, Any]] = []

    for item in read_jsonl(manifest_path, limit=500):
        classification = item.get("classification") or {}
        if not item.get("ok") or not classification.get("primary_label"):
            continue
        rows.append(
            {
                "filename": Path(str(item.get("source_path", ""))).name,
                "extension": Path(str(item.get("source_path", ""))).suffix.lower(),
                "parser": (item.get("timing") or {}).get("parser", ""),
                "text_preview": " ".join(
                    filter(
                        None,
                        [
                            str(classification.get("summary", "")),
                            str(classification.get("reason", "")),
                            " ".join(map(str, classification.get("secondary_labels", []) or [])),
                        ],
                    )
                ),
                "heuristic_primary": ((item.get("hybrid") or {}).get("decision") or {}).get("selected_primary_hint", classification.get("primary_label", "unknown")),
                "taxonomy_candidates": (item.get("hybrid") or {}).get("taxonomy_candidates", []) or classification.get("candidate_categories_used", []),
                "accepted_primary": classification.get("primary_label"),
                "used_inline_llm": ((item.get("hybrid") or {}).get("decision") or {}).get("live_source") == "inline-llm",
                "disagreement": False,
            }
        )

    for item in read_jsonl(corrections_path, limit=500) + read_jsonl(examples_path, limit=500):
        accepted = item.get("correct_label") or item.get("primary_label") or item.get("label")
        if not accepted:
            continue
        rows.append(
            {
                "filename": str(item.get("filename") or item.get("source_filename") or "example"),
                "extension": Path(str(item.get("filename") or item.get("source_filename") or "example")).suffix.lower(),
                "parser": str(item.get("parser", "")),
                "text_preview": " ".join(
                    filter(
                        None,
                        [
                            str(item.get("summary", "")),
                            str(item.get("note", "")),
                            str(item.get("old_label", "")),
                        ],
                    )
                ),
                "heuristic_primary": str(item.get("old_label") or accepted),
                "taxonomy_candidates": item.get("secondary_labels", []) or [],
                "accepted_primary": str(accepted),
                "used_inline_llm": True,
                "disagreement": bool(item.get("old_label") and item.get("old_label") != accepted),
            }
        )

    for item in read_jsonl(comparisons_path, limit=1000):
        rows.append(
            {
                "filename": str(item.get("filename", "")),
                "extension": str(item.get("extension", "")),
                "parser": str(item.get("parser", "")),
                "text_preview": str(item.get("text_preview", "")),
                "heuristic_primary": str(item.get("heuristic_primary", "unknown")),
                "taxonomy_candidates": item.get("taxonomy_candidates", []) or [],
                "accepted_primary": str(item.get("shadow_primary") or item.get("live_primary") or item.get("heuristic_primary") or "unknown"),
                "used_inline_llm": True,
                "disagreement": bool(item.get("disagreement")),
            }
        )

    return rows


def ensure_lightgbm_model(
    model_path: Path = LIGHTGBM_MODEL_PATH,
    report_path: Path = LIGHTGBM_REPORT_PATH,
    min_rows: int = 3,
) -> Dict[str, Any]:
    if model_path.exists():
        return {"ok": True, "created": False, "model_path": str(model_path)}

    training_rows = build_training_rows_from_runtime()
    if len(training_rows) < min_rows:
        return {"ok": False, "created": False, "reason": "insufficient-training-rows", "training_rows": len(training_rows)}

    report = train_lightgbm_model(
        training_rows=training_rows,
        model_path=model_path,
        report_path=report_path,
    )
    return {"ok": True, "created": True, "report": report}


def build_readiness_report(
    gating_config: Optional[Dict[str, Any]] = None,
    comparisons_path: Path = SHADOW_COMPARISONS_PATH,
    queue_dir: Path = SHADOW_QUEUE_DIR,
    model_path: Path = LIGHTGBM_MODEL_PATH,
) -> Dict[str, Any]:
    gating = gating_config or load_hybrid_gating_config()
    comparisons = read_jsonl(comparisons_path, limit=500)
    queue_depth = len(list(queue_dir.glob("*.json"))) if queue_dir.exists() else 0
    model_exists = model_path.exists()

    reviewed = [row for row in comparisons if row.get("teacher_review_status")]
    approved = [row for row in comparisons if row.get("teacher_approved_for_training")]
    agreements = [row for row in approved if row.get("teacher_supports_live_result")]
    approved_unique_files = sorted(
        {
            str(row.get("filename", "")).strip()
            for row in approved
            if str(row.get("filename", "")).strip()
        }
    )
    approved_extensions = sorted(
        {
            str(row.get("extension", "")).strip().lower()
            for row in approved
            if str(row.get("extension", "")).strip()
        }
    )
    approved_labels = sorted(
        {
            str(row.get("shadow_primary") or row.get("live_primary") or row.get("heuristic_primary") or "unknown").strip()
            for row in approved
            if str(row.get("shadow_primary") or row.get("live_primary") or row.get("heuristic_primary") or "").strip()
        }
    )
    approved_parsers = sorted(
        {
            str(row.get("parser", "")).strip()
            for row in approved
            if str(row.get("parser", "")).strip()
        }
    )
    approval_rate = (len(approved) / len(reviewed)) if reviewed else 0.0
    agreement_rate = (len(agreements) / len(approved)) if approved else 0.0

    min_samples = int(gating.get("readiness_min_teacher_samples", 10))
    min_unique_files = int(gating.get("readiness_min_unique_teacher_files", min_samples))
    min_extensions = int(gating.get("readiness_min_teacher_extensions", 4))
    min_labels = int(gating.get("readiness_min_teacher_labels", 4))
    min_agreement = safe_float(gating.get("readiness_min_teacher_agreement_rate"), 0.80)
    min_approval = safe_float(gating.get("readiness_min_teacher_approval_rate"), 0.70)
    max_queue_depth = int(gating.get("readiness_max_queue_depth", 25))
    allow_real_ingestion = bool(gating.get("allow_real_ingestion", False))

    thresholds_pass = (
        model_exists
        and len(approved) >= min_samples
        and len(approved_unique_files) >= min_unique_files
        and len(approved_extensions) >= min_extensions
        and len(approved_labels) >= min_labels
        and approval_rate >= min_approval
        and agreement_rate >= min_agreement
        and queue_depth <= max_queue_depth
    )

    warnings: list[str] = []
    if not model_exists:
        warnings.append("lightgbm-model-missing")
    if len(approved) < min_samples:
        warnings.append("insufficient-teacher-approved-samples")
    if len(approved_unique_files) < min_unique_files:
        warnings.append("insufficient-unique-teacher-files")
    if len(approved_extensions) < min_extensions:
        warnings.append("insufficient-teacher-extension-coverage")
    if len(approved_labels) < min_labels:
        warnings.append("insufficient-teacher-label-coverage")
    if approval_rate < min_approval:
        warnings.append("teacher-approval-rate-below-threshold")
    if agreement_rate < min_agreement:
        warnings.append("teacher-agreement-rate-below-threshold")
    if queue_depth > max_queue_depth:
        warnings.append("shadow-queue-backlog-too-deep")
    if thresholds_pass and not allow_real_ingestion:
        warnings.append("manual-real-ingestion-enable-still-required")

    return {
        "generated_at": utc_now(),
        "ok": True,
        "model_exists": model_exists,
        "comparison_rows": len(comparisons),
        "teacher_reviewed_rows": len(reviewed),
        "teacher_approved_rows": len(approved),
        "teacher_live_agreement_rows": len(agreements),
        "teacher_approval_rate": round(approval_rate, 6),
        "teacher_agreement_rate": round(agreement_rate, 6),
        "teacher_unique_files": len(approved_unique_files),
        "teacher_extensions": approved_extensions,
        "teacher_labels": approved_labels,
        "teacher_parsers": approved_parsers,
        "queue_depth": queue_depth,
        "thresholds": {
            "readiness_min_teacher_samples": min_samples,
            "readiness_min_unique_teacher_files": min_unique_files,
            "readiness_min_teacher_extensions": min_extensions,
            "readiness_min_teacher_labels": min_labels,
            "readiness_min_teacher_agreement_rate": min_agreement,
            "readiness_min_teacher_approval_rate": min_approval,
            "readiness_max_queue_depth": max_queue_depth,
        },
        "thresholds_pass": thresholds_pass,
        "allow_real_ingestion": allow_real_ingestion,
        "real_ingestion_allowed": thresholds_pass and allow_real_ingestion,
        "warnings": warnings,
    }


def write_readiness_report(
    gating_config: Optional[Dict[str, Any]] = None,
    readiness_path: Path = READINESS_REPORT_PATH,
) -> Dict[str, Any]:
    report = build_readiness_report(gating_config=gating_config)
    save_json(readiness_path, report)
    return report
