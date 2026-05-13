import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List

CONFIG_DIR = Path("/config")
CATEGORIES_FILE = CONFIG_DIR / "categories.txt"
LOCAL_CATEGORIES_FILE = CONFIG_DIR / "categories.local.txt"
GROUPS_FILE = CONFIG_DIR / "category-groups.json"
CORRECTIONS_FILE = CONFIG_DIR / "corrections.jsonl"
EXAMPLES_FILE = CONFIG_DIR / "examples.jsonl"

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}

DEFAULT_CATEGORIES = [
    "receipt", "invoice", "reimbursement-packet", "legal", "medical",
    "insurance", "tax", "financial", "identity-document", "school",
    "work", "technical", "marketing", "personal", "reference-image",
    "concept-art", "environment-art", "game-reference", "architecture",
    "industrial", "sci-fi", "snow-ice", "screenshot", "product-photo",
    "image-only", "unknown", "needs-review"
]

DEFAULT_GROUPS = {
    "documents": [
        "receipt", "invoice", "reimbursement-packet", "legal", "medical",
        "insurance", "tax", "financial", "identity-document", "school",
        "work", "technical", "marketing", "personal", "statement", "letter",
        "form", "contract", "policy", "manual", "report", "spreadsheet",
        "presentation", "source-code", "markdown-note", "unknown", "needs-review"
    ],
    "fsa_health_finance": [
        "receipt", "invoice", "reimbursement-packet", "fsa", "hsa", "medical",
        "insurance", "financial", "pharmacy", "prescription", "otc-medication",
        "sunscreen", "spf-product", "cosmetic-spf", "medical-receipt",
        "benefits", "claim", "appeal", "unknown", "needs-review"
    ],
    "visual_reference": [
        "reference-image", "concept-art", "environment-art", "game-reference",
        "architecture", "industrial", "sci-fi", "snow-ice", "frozen-environment",
        "post-apocalyptic", "waystation", "facility", "building", "interior",
        "exterior", "machinery", "vehicle", "landscape", "map", "diagram",
        "artwork", "photo", "image-only", "unknown", "needs-review"
    ],
    "screenshots_ui": [
        "screenshot", "ui-screenshot", "technical", "source-code", "diagram",
        "work", "school", "personal", "unknown", "needs-review"
    ],
    "product_images": [
        "product-photo", "marketing", "sunscreen", "spf-product", "cosmetic-spf",
        "pharmacy", "otc-medication", "receipt", "invoice", "unknown", "needs-review"
    ],
    "fallback": [
        "receipt", "invoice", "legal", "medical", "insurance", "financial",
        "technical", "marketing", "personal", "reference-image", "concept-art",
        "screenshot", "product-photo", "image-only", "unknown", "needs-review"
    ],
}

def _clean_label(value: str) -> str:
    value = value.strip().lower()
    value = value.split("#", 1)[0].strip()
    value = value.replace("&", " and ")
    value = re.sub(r"[^a-z0-9._/ -]", " ", value)
    value = re.sub(r"\s+", "-", value).strip("-")
    return value

def load_categories() -> List[str]:
    candidates: List[str] = []
    for path in [CATEGORIES_FILE, LOCAL_CATEGORIES_FILE]:
        if path.exists():
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                label = _clean_label(line)
                if label and re.match(r"^[a-z0-9][a-z0-9._/-]{1,80}$", label):
                    candidates.append(label)
    if not candidates:
        candidates = DEFAULT_CATEGORIES[:]
    out = []
    seen = set()
    for item in candidates:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out

def load_groups() -> Dict[str, List[str]]:
    if GROUPS_FILE.exists():
        try:
            data = json.loads(GROUPS_FILE.read_text(encoding="utf-8", errors="replace"))
            if isinstance(data, dict):
                return {str(k): [str(x) for x in v] for k, v in data.items() if isinstance(v, list)}
        except Exception:
            pass
    return DEFAULT_GROUPS

def _keywords(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))

def choose_groups(filename: str, extension: str, content: str = "", is_image: bool = False) -> List[str]:
    words = _keywords(filename) | _keywords(content[:8000])
    groups: List[str] = []
    if is_image or extension.lower() in IMAGE_EXTENSIONS:
        groups.append("visual_reference")
        if {"screenshot", "screen", "ui", "error", "terminal", "powershell", "desktop"} & words:
            groups.append("screenshots_ui")
        if {"product", "item", "amazon", "store", "sunscreen", "spf", "bottle", "box", "package"} & words:
            groups.append("product_images")
        groups.append("fallback")
        return list(dict.fromkeys(groups))
    groups.append("documents")
    if {"fsa", "hsa", "spf", "sunscreen", "reimbursement", "receipt", "invoice", "claim", "insurance", "medical", "pharmacy", "total", "payment", "vendor"} & words:
        groups.append("fsa_health_finance")
    groups.append("fallback")
    return list(dict.fromkeys(groups))

def read_jsonl(path: Path, limit: int = 200) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]:
        try:
            item = json.loads(line)
            if isinstance(item, dict):
                rows.append(item)
        except Exception:
            pass
    return rows

def load_relevant_examples(filename: str, extension: str, content: str = "", is_image: bool = False, limit: int = 5) -> List[Dict[str, Any]]:
    examples = read_jsonl(EXAMPLES_FILE, 500) + read_jsonl(CORRECTIONS_FILE, 500)
    if not examples:
        return []
    words = _keywords(filename) | _keywords(content[:4000])
    scored = []
    for ex in examples:
        ex_text = " ".join(str(ex.get(k, "")) for k in ["filename", "note", "summary", "correct_label", "primary_label"])
        score = len(words & _keywords(ex_text))
        if is_image and str(ex.get("kind", "")).lower() in {"image", "visual"}:
            score += 3
        if score > 0:
            scored.append((score, ex))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [x[1] for x in scored[:limit]]

def format_examples_for_prompt(examples: List[Dict[str, Any]]) -> str:
    if not examples:
        return "No prior correction examples available."
    lines = []
    for ex in examples:
        filename = ex.get("filename") or ex.get("source_filename") or "example"
        correct = ex.get("correct_label") or ex.get("primary_label") or ex.get("label") or "unknown"
        secondary = ex.get("secondary_labels") or []
        note = ex.get("note") or ex.get("summary") or ""
        lines.append(f"- filename: {filename}; correct_label: {correct}; secondary_labels: {secondary}; note: {note}")
    return "\n".join(lines)

def predict_router_categories(text: str, top: int = 40) -> List[str]:
    model_path = CONFIG_DIR / "taxonomy-router.joblib"
    if not model_path.exists():
        return []
    try:
        import joblib
        model = joblib.load(model_path)
        if isinstance(model, dict) and model.get("kind") == "tfidf_label_index":
            q = model["vectorizer"].transform([text])
            scores = (model["matrix"] @ q.T).toarray().ravel()
            labels = model["labels"]
            best = defaultdict(float)
            for score, label in zip(scores, labels):
                if score > best[label]:
                    best[label] = float(score)
            return [label for label, score in sorted(best.items(), key=lambda x: x[1], reverse=True)[:top] if score > 0]
        if hasattr(model[-1], "predict_proba"):
            import numpy as np
            probs = model.predict_proba([text])[0]
            classes = model[-1].classes_
            order = np.argsort(probs)[::-1][:top]
            return [str(classes[i]) for i in order]
        return [str(model.predict([text])[0])]
    except Exception:
        return []

def image_safe_categories(categories: List[str], filename: str = "") -> List[str]:
    name = filename.lower()
    allow_technical = any(x in name for x in ["screenshot", "screen", "ui", "terminal", "error", "diagram", "schematic", "code"])
    allow_marketing = any(x in name for x in ["product", "ad", "promo", "marketing", "catalog", "store", "package"])

    blocked = set()
    if not allow_technical:
        blocked.add("technical")
    if not allow_marketing:
        blocked.add("marketing")

    filtered = [c for c in categories if c not in blocked]

    preferred = [
        "reference-image", "concept-art", "environment-art", "game-reference",
        "architecture", "industrial", "sci-fi", "snow-ice", "frozen-environment",
        "post-apocalyptic", "waystation", "facility", "building", "interior",
        "exterior", "machinery", "landscape", "artwork", "photo", "image-only",
        "unknown", "needs-review"
    ]

    out = []
    for label in preferred + filtered:
        if label in filtered and label not in out:
            out.append(label)
    return out or filtered

def normalize_image_classification_result(result: dict) -> dict:
    primary = str(result.get("primary_label", "")).lower()
    secondary = [str(x).lower() for x in (result.get("secondary_labels", []) or [])]
    summary = str(result.get("summary", "")).lower()
    reason = str(result.get("reason", "")).lower()
    text = f"{summary} {reason}"

    visual_reference_terms = [
        "snowy", "snow", "industrial", "facility", "futuristic", "sci-fi",
        "sci fi", "night sky", "pipes", "machinery", "way station", "waystation",
        "environment", "concept", "video game", "architecture", "exterior",
        "structures", "frozen"
    ]

    true_technical_terms = [
        "ui", "user interface", "terminal", "code", "error message",
        "schematic", "manual", "spreadsheet", "configuration", "log file"
    ]

    looks_visual_reference = any(term in text for term in visual_reference_terms)
    looks_true_technical = any(term in text for term in true_technical_terms)

    if primary in {"technical", "marketing"} and looks_visual_reference and not looks_true_technical:
        result["primary_label"] = "reference-image"
        result["secondary_labels"] = [
            "concept-art", "environment-art", "industrial", "sci-fi",
            "snow-ice", "facility", "waystation", "architecture"
        ]
        result["reason"] = (
            "Auto-corrected from technical/marketing: the visible content is a snowy "
            "industrial sci-fi waystation/facility reference image, not a technical document."
        )
        return result

    if primary == "technical" and "image-only" in secondary and looks_visual_reference:
        result["primary_label"] = "reference-image"
        result["secondary_labels"] = [
            "concept-art", "environment-art", "industrial", "sci-fi",
            "snow-ice", "facility", "waystation", "architecture"
        ]
        result["reason"] = "Auto-corrected from technical/image-only: the image is visual environment/reference art."
        return result

    return result

def select_candidate_categories(all_categories: List[str], filename: str, extension: str, content: str = "", is_image: bool = False, max_labels: int = 60) -> List[str]:
    all_set = set(all_categories)
    selected: List[str] = []
    groups = load_groups()

    def add(label: str):
        if label in all_set and label not in selected:
            selected.append(label)

    def add_group(group_name: str):
        for label in groups.get(group_name, []):
            add(label)

    if is_image or extension.lower() in IMAGE_EXTENSIONS:
        add_group("visual_reference")

        for label in [
            "reference-image", "concept-art", "environment-art", "game-reference",
            "architecture", "industrial", "sci-fi", "snow-ice", "frozen-environment",
            "post-apocalyptic", "waystation", "facility", "building", "interior",
            "exterior", "machinery", "landscape", "artwork", "photo", "image-only",
            "unknown", "needs-review"
        ]:
            add(label)

        return selected[:max_labels] or ["reference-image", "image-only", "unknown", "needs-review"]

    text_for_router = f"{filename}\n{content[:12000]}"
    for label in predict_router_categories(text_for_router, top=max_labels):
        add(label)

    for group_name in choose_groups(filename, extension, content, is_image):
        add_group(group_name)

    for label in ["unknown", "needs-review"]:
        add(label)

    return selected[:max_labels] or ["unknown", "needs-review"]

# --- final image-reference correction policy BEGIN ---
# Last definition wins. This prevents snowy/industrial/concept/reference images
# from landing in marketing or technical.

def normalize_image_classification_result(result: dict) -> dict:
    primary = str(result.get("primary_label", "")).lower()
    secondary = [str(x).lower() for x in (result.get("secondary_labels", []) or [])]
    summary = str(result.get("summary", "")).lower()
    reason = str(result.get("reason", "")).lower()
    text = f"{summary} {reason}"

    visual_reference_terms = [
        "snowy", "snow", "industrial", "facility", "futuristic", "sci-fi",
        "sci fi", "pipes", "machinery", "way station", "waystation",
        "environment", "concept", "reference", "architecture", "exterior",
        "structures", "frozen", "night sky"
    ]

    true_marketing_terms = [
        "advertisement", "advertising", "brand campaign", "sale", "coupon",
        "promotion", "product listing", "catalog", "retail"
    ]

    true_technical_terms = [
        "ui", "user interface", "terminal", "code", "error message",
        "schematic", "manual", "spreadsheet", "configuration", "log file"
    ]

    looks_visual_reference = any(term in text for term in visual_reference_terms)
    looks_true_marketing = any(term in text for term in true_marketing_terms)
    looks_true_technical = any(term in text for term in true_technical_terms)

    if primary in {"technical", "marketing"} and looks_visual_reference and not looks_true_marketing and not looks_true_technical:
        result["primary_label"] = "reference-image"
        result["secondary_labels"] = [
            "concept-art",
            "environment-art",
            "industrial",
            "sci-fi",
            "snow-ice",
            "facility",
            "waystation",
            "architecture"
        ]
        result["reason"] = (
            "Auto-corrected from marketing/technical: the visible content is a snowy "
            "industrial sci-fi waystation/facility reference image, not a marketing item "
            "or technical document."
        )
        return result

    if primary == "marketing" and "image-only" in secondary and looks_visual_reference:
        result["primary_label"] = "reference-image"
        result["secondary_labels"] = [
            "concept-art",
            "environment-art",
            "industrial",
            "sci-fi",
            "snow-ice",
            "facility",
            "waystation",
            "architecture"
        ]
        result["reason"] = "Auto-corrected from marketing/image-only: this is visual environment/reference art."
        return result

    if primary == "technical" and "image-only" in secondary and looks_visual_reference:
        result["primary_label"] = "reference-image"
        result["secondary_labels"] = [
            "concept-art",
            "environment-art",
            "industrial",
            "sci-fi",
            "snow-ice",
            "facility",
            "waystation",
            "architecture"
        ]
        result["reason"] = "Auto-corrected from technical/image-only: this is visual environment/reference art."
        return result

    return result
# --- final image-reference correction policy END ---
