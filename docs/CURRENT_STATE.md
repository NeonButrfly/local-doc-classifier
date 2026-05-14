# Current State Snapshot

Updated from the 2026-05-13 takeover, deployment repair, and live validation pass.

## Repo state

- Source includes `normalize_image_classification_result()` in `classifier/app/category_manager.py` as the final image label-policy gate.
- The image execution path in `classifier/app/classify-to-obsidian.py` normalizes image classifications before writing Obsidian notes.
- Regression coverage for the snowy industrial waystation policy lives in `tests/test_image_label_policy.py`.
- GitHub tracking for this fix is in issue `#1`.

## Deployment status

- The Linux home clone at `~/local-doc-classifier` has been restored from GitHub and is now the deployment source for `/opt/local-doc-classifier`.
- `scripts/install-or-update.sh` now handles the available Docker Compose packaging on the Ubuntu Questing host.
- Repeated installs now replace deployed source directories cleanly instead of nesting stale code under `/opt/local-doc-classifier`.
- The classifier image now preloads the RapidOCR runtime weights needed for Docling-based document parsing.
- The live API at `http://192.168.50.196:4319` now returns healthy `/health`, working `/categories`, and working `/corrections`.
- The committed synthetic PDF, DOCX, XLSX, and JPG fixtures all uploaded successfully through the live API after the rebuild.
- GitHub issues `#1`, `#2`, `#3`, and `#4` were updated with validation evidence and closed after verification.

## Known caution

- Do not commit live API tokens.
- Do not commit generated vault content.
- Do not commit source documents.
- API token should be rotated after testing.
- If Docker images are pruned, rebuild local images before starting API.
- If `/categories` returns `404`, the deployed API image is stale relative to repo source and must be rebuilt from the current checkout.
- If a future deploy regresses document uploads, verify that the classifier image still includes the RapidOCR preloaded weights before debugging the API layer.
