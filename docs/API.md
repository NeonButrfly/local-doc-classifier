# API

Base URL:

```text
http://192.168.50.196:4319
```

Required header:

```text
X-API-Key: <CLASSIFIER_API_TOKEN>
```

## GET /health

Checks Ollama/API/vault health.

## POST /classify/upload

Multipart file upload.

```bash
curl -sS \
  -H "X-API-Key: ${TOKEN}" \
  -F "file=@/path/to/file.pdf;filename=file.pdf;type=application/pdf" \
  http://127.0.0.1:4319/classify/upload
```

Important: include `filename=...` or image extension handling may fail.

The response also includes:

- `upload_ms`: server-side time spent receiving and staging the multipart upload
- `classify_ms`: server-side time spent after upload on parsing/classification/note writing
- `total_ms`: full server-side request time
- `worker_timing`: deeper worker-side timing details from inside the classifier process

Hybrid text paths also record decision metadata in the manifest, including:

- taxonomy candidate labels used for the live decision
- LightGBM top-label and gate probabilities
- whether the live answer came from the fast heuristic path or the inline LLM path

Typical `worker_timing` fields:

- `mode`: `document` or `image`
- `parser`: parser path used for document files such as `docling`, `docling-converted`, `plain-text`, or `html-plain`
- `classifier`: optional classifier path used for special fast lanes such as `heuristic-spreadsheet-fast-path` or `heuristic-document-fast-path`
- `parse_ms`: time spent extracting text or Markdown before the model call
- `model_ms`: time spent waiting on the Ollama model response; this may be `0` for deterministic fast paths
- `note_write_ms`: time spent writing the Obsidian note and extracted Markdown
- `manifest_write_ms`: time spent appending the manifest record
- `total_ms`: total worker-side time for the file

Autonomous runtime behavior:

- fast-path text documents may be validated by LightGBM before deciding whether to call the LLM inline
- background shadow-mode review runs through a queue on the server
- disagreement evidence can retrain the LightGBM artifact and update heuristic config thresholds without editing source code

## POST /benchmark/upload-only

Multipart upload benchmark that stages the file without invoking classification.

```bash
curl -sS \
  -H "X-API-Key: ${TOKEN}" \
  -F "cleanup=true" \
  -F "file=@/path/to/file.pdf;filename=file.pdf;type=application/pdf" \
  http://127.0.0.1:4319/benchmark/upload-only
```

Useful for separating LAN upload/staging time from decision-making time.

## GET /recent

Returns recent manifest records.

## GET /index

Returns the Obsidian classification index.

## GET /note

Reads a vault-relative Markdown note.

## GET /categories

Returns active category list and groups.

## GET /corrections

Returns correction memory.

## POST /corrections

Adds correction memory.
