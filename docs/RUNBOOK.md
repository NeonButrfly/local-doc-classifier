# Runbook

## Start stack

```bash
cd /opt/local-doc-classifier
docker compose up -d ollama api
```

If the vault is stored on a separate path, the active location is whatever
`VAULT_DIR` is set to in `/opt/local-doc-classifier/.env`. For an NFS-backed
vault, the installer can mount a remote export first and then point `VAULT_DIR`
at a subdirectory under that mount.

## Rebuild API

```bash
cd /opt/local-doc-classifier
docker compose build classifier
docker compose rm -sf api || true
docker ps -aq --filter "name=local-doc-classifier-api" | xargs -r docker rm -f
docker compose up -d api
```

## Health check

```bash
TOKEN="$(grep '^CLASSIFIER_API_TOKEN=' /opt/local-doc-classifier/.env | cut -d= -f2-)"
curl -sS -H "X-API-Key: ${TOKEN}" http://127.0.0.1:4319/health | jq
```

Expected:

```json
{
  "ok": true,
  "ollama_ok": true
}
```

## Test API upload from Linux

```bash
TOKEN="$(grep '^CLASSIFIER_API_TOKEN=' /opt/local-doc-classifier/.env | cut -d= -f2-)"

cat > /tmp/test-receipt.txt <<'EOF'
Amazon receipt
Item: Broad Spectrum Sunscreen SPF 30
Total: $18.99
Date: 2026-05-13
EOF

curl -sS \
  -H "X-API-Key: ${TOKEN}" \
  -F "file=@/tmp/test-receipt.txt;filename=test-receipt.txt;type=text/plain" \
  http://127.0.0.1:4319/classify/upload | jq
```

## Sync public categories

```bash
cd /opt/local-doc-classifier
./taxcat sync
./taxcat status
./taxcat count
```

## Train taxonomy router

```bash
cd /opt/local-doc-classifier
docker compose --profile tools run --rm --entrypoint python taxonomy-router /router/train_taxonomy_router.py
```

## Test taxonomy router

```bash
cd /opt/local-doc-classifier
docker compose --profile tools run --rm taxonomy-router --text "snowy industrial sci fi waystation exterior environment concept art reference image" --top 20
```

## Add a correction manually

```bash
mkdir -p /opt/local-doc-classifier/config

cat >> /opt/local-doc-classifier/config/corrections.jsonl <<'EOF'
{"filename":"snowy-industrial-waystation-reference.jpg","extension":".jpg","kind":"image","old_label":"technical","correct_label":"reference-image","secondary_labels":["concept-art","environment-art","industrial","sci-fi","snow-ice","facility","waystation"],"note":"Snowy futuristic industrial facility / waystation image. This is visual reference or concept/environment art, not a technical document.","summary":"Futuristic snowy industrial facility with pipes and machinery."}
EOF
```

Then retrain router and rebuild API.

## Reset generated index and vault

```bash
/opt/local-doc-classifier/scripts/reset-vault-and-index.sh
```

## Example NFS-backed vault settings

```dotenv
APP_DIR=/opt/local-doc-classifier
VAULT_NFS_REMOTE=192.168.50.86:/srv/cloud-vault
VAULT_NFS_MOUNT_DIR=/mnt/cloud-vault
VAULT_DIR=/mnt/cloud-vault/local-doc-classifier-vault
```
