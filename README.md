# Local Document Classifier

A local Docker-orchestrated document and image classifier using:

- Ollama for local LLM inference
- Qwen text and vision models
- Docling / OCR for document extraction
- FastAPI upload API
- Obsidian vault output for Markdown notes
- Public taxonomy sync
- Lightweight taxonomy router
- Correction memory

Default live deployment target:

```text
/opt/local-doc-classifier
```

Default LAN API:

```text
http://192.168.50.196:4319
```

Default Obsidian vault:

```text
/opt/local-doc-classifier/vault
```

The deployment can also override this with:

```text
VAULT_DIR=/some/other/path
```

For an NFS-backed vault, set for example:

```text
VAULT_NFS_REMOTE=192.168.50.86:/srv/cloud-vault
VAULT_NFS_MOUNT_DIR=/mnt/cloud-vault
VAULT_DIR=/mnt/cloud-vault/local-doc-classifier-vault
```

## What this repo contains

```text
classifier/          Dockerized FastAPI + Docling/Ollama classifier
taxonomy-router/     Lightweight TF-IDF taxonomy router
config/              Local categories, groups, public taxonomy source config
scripts/             Install, reset, health check, taxonomy sync helpers
docs/                Architecture, API docs, runbook, reproduction notes
tests/windows/       Windows PowerShell API test script
```

## Quick Windows repo setup

Unzip this repo to:

```powershell
C:\Code\local-doc-classifier
```

Initialize Git:

```powershell
cd C:\Code\local-doc-classifier
git init
git add .
git commit -m "Initial local document classifier repo"
```

Copy/deploy to Linux:

```powershell
scp -r C:\Code\local-doc-classifier kay@192.168.50.196:/home/kay/local-doc-classifier-repo
ssh kay@192.168.50.196 "cd /home/kay/local-doc-classifier-repo && sudo ./scripts/install-or-update.sh"
```

## Test from Windows

Put one image, one PDF, and one Word document under:

```text
C:\Code\TestAI
```

Then run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass -Force
C:\Code\local-doc-classifier\tests\windows\Test-LocalClassifier.ps1 -FetchTokenOverSsh
```

## Security note

Do not commit `.env`, API tokens, Obsidian vault contents, source documents, Ollama model data, or generated outputs.

Rotate the API token if it has been shared.
