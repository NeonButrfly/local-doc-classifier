# Architecture

## Overview

```text
Windows/macOS/client/plugin
        ↓ HTTP multipart upload
Classifier FastAPI service
        ↓
/input/api
        ↓
Docling / OCR / file parsing
        ↓
Ollama text or vision model
        ↓
classification JSON
        ↓
Obsidian Markdown note
        ↓
/vault/Classification Index.md
```

## Services

### ollama

Runs local models:

```text
qwen2.5:3b
qwen2.5vl:3b
```

### api

FastAPI upload API.

Primary endpoints:

```text
GET  /health
POST /classify/upload
GET  /recent
GET  /index
GET  /note?path=...
GET  /categories
GET  /corrections
POST /corrections
```

### classifier

One-shot CLI container for direct classification jobs.

### taxonomy-router

Lightweight TF-IDF label router trained from public category lists and correction examples.

## Taxonomy strategy

Do not pass thousands of public categories into every LLM prompt.

Instead:

```text
public taxonomy sync
        ↓
categories.full.txt
        ↓
taxonomy-router.joblib
        ↓
shortlist likely labels
        ↓
LLM sees only likely labels
```

## Correction strategy

When the classifier is wrong:

1. Save a correction into `config/corrections.jsonl`.
2. Retrain the taxonomy router.
3. Rebuild/restart the API.
4. Reclassify.
