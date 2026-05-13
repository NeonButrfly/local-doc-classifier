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
