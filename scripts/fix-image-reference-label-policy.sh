#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_DIR}"

python3 - <<'PY'
from pathlib import Path
import re

p = Path("classifier/app/category_manager.py")
s = p.read_text(encoding="utf-8")

start = "# --- final image-reference correction policy BEGIN ---"
end = "# --- final image-reference correction policy END ---"

block = r'''
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
'''

pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.DOTALL)

if pattern.search(s):
    s = pattern.sub(block.strip(), s)
else:
    s = s.rstrip() + "\n\n" + block.strip() + "\n"

p.write_text(s, encoding="utf-8")
PY

python3 - <<'PY'
from pathlib import Path
import re

p = Path("classifier/app/classify-to-obsidian.py")
s = p.read_text(encoding="utf-8")

marker_start = "    # --- image-normalize-before-note BEGIN ---"
marker_end = "    # --- image-normalize-before-note END ---"

s = re.sub(
    re.escape(marker_start) + r".*?" + re.escape(marker_end) + r"\n",
    "",
    s,
    flags=re.DOTALL,
)

signature = """def write_obsidian_note(
    vault: Path,
    source_path: Path,
    file_hash: str,
    markdown: Optional[str],
    classification: Dict[str, Any],
    attach_originals: bool,
) -> Path:
"""

insert = signature + """    # --- image-normalize-before-note BEGIN ---
    try:
        if source_path.suffix.lower() in IMAGE_EXTENSIONS:
            from category_manager import normalize_image_classification_result
            classification = normalize_image_classification_result(classification)
    except Exception:
        pass
    # --- image-normalize-before-note END ---

"""

if signature not in s:
    raise SystemExit("Could not find write_obsidian_note signature.")

s = s.replace(signature, insert, 1)
p.write_text(s, encoding="utf-8")
PY

echo "[DONE] Applied image reference label policy fix."
