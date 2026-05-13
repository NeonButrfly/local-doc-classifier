# Current State Snapshot

Generated package time: 2026-05-13T20:41:35

## Known working from session

- FastAPI health endpoint works.
- Ollama health works.
- PDF upload/classification works.
- Word upload/classification works.
- Obsidian Markdown notes are written.
- Classification index is written.
- Public taxonomy sync installed.
- Taxonomy router exists.
- Image classification works technically, but label policy may need continued correction tuning.

## Known caution

- Do not commit live API tokens.
- Do not commit generated vault content.
- Do not commit source documents.
- API token should be rotated after testing.
- If Docker images are pruned, rebuild local images before starting API.
- If `/categories` or `/corrections` returns 404, rebuild the API image from current source.
