# Reproduce Final Environment

## Target

```text
/opt/local-doc-classifier
```

## Requirements

- Ubuntu/Debian Linux
- Docker + Docker Compose
- LAN access
- Optional NVIDIA GPU
- Sufficient disk space
- Ollama model storage under `/opt/local-doc-classifier/ollama`

## Install

```bash
sudo ./scripts/install-or-update.sh
```

## Start

```bash
cd /opt/local-doc-classifier
docker compose up -d ollama api
```

## Pull models

```bash
cd /opt/local-doc-classifier
docker compose --profile init run --rm model-init
```

## Sync categories

```bash
/opt/local-doc-classifier/taxcat sync
```

## Train router

```bash
cd /opt/local-doc-classifier
docker compose --profile tools run --rm --entrypoint python taxonomy-router /router/train_taxonomy_router.py
```

## Test

Linux:

```bash
/opt/local-doc-classifier/scripts/health-check.sh
```

Windows:

```powershell
C:\Code\TestAI\Test-LocalClassifier.ps1
```
