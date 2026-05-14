# Current State Snapshot

Updated from the 2026-05-13 takeover and validation pass.

## Repo state

- Source includes `normalize_image_classification_result()` in `classifier/app/category_manager.py` as the final image label-policy gate.
- The image execution path in `classifier/app/classify-to-obsidian.py` normalizes image classifications before writing Obsidian notes.
- Regression coverage for the snowy industrial waystation policy lives in `tests/test_image_label_policy.py`.
- GitHub tracking for this fix is in issue `#1`.

## Deployment status before rebuild

- The live API at `http://192.168.50.196:4319` returned healthy Ollama status during takeover.
- The live API was still serving an older application build because `/categories` returned `404 Not Found` even though the current repo source exposes that endpoint.
- A Linux home clone at `~/local-doc-classifier` was missing, so the desired GitHub -> Linux clone -> `/opt/local-doc-classifier` deployment flow needed to be restored.

## Known caution

- Do not commit live API tokens.
- Do not commit generated vault content.
- Do not commit source documents.
- API token should be rotated after testing.
- If Docker images are pruned, rebuild local images before starting API.
- If `/categories` returns `404`, the deployed API image is stale relative to repo source and must be rebuilt from the current checkout.
