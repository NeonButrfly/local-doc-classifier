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
