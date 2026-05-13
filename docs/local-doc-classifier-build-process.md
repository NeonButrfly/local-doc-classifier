# Local Document Classifier Build Process

Generated: 2026-05-13T20:47:08

## Purpose

This document captures the full build process and final operating model for the local LLM-powered document/image classifier built during the working session.

The final system is intended to run on the Linux host:

```text
tichuml1 / 192.168.50.196
```

Primary live path:

```text
/opt/local-doc-classifier
```

Windows repo path target:

```text
C:\Code\local-doc-classifier
```

Windows test-data path:

```text
C:\Code\TestAI
```

The system classifies PDFs, Word documents, text/Markdown/CSV/Office files, and images locally, then writes Markdown classification notes into an Obsidian vault.

---

# 1. Final Architecture

## 1.1 High-level flow

```text
Windows/macOS/client/plugin
        ↓ HTTP multipart upload
Classifier FastAPI service on 192.168.50.196:4319
        ↓
/opt/local-doc-classifier/input/api
        ↓
Docling / OCR / file parsing
        ↓
Ollama text or vision model
        ↓
classification JSON
        ↓
Obsidian Markdown note
        ↓
/opt/local-doc-classifier/vault/Classification Index.md
```

## 1.2 Main components

| Component | Purpose |
|---|---|
| Ollama | Local model runtime |
| qwen2.5:3b | Text/document classification |
| qwen2.5vl:3b | Image/vision classification |
| Docling | PDF/Office/document extraction |
| FastAPI | Non-SSH upload and classification API |
| Obsidian vault | Markdown storage and human review layer |
| Taxonomy sync | Pulls public category lists occasionally |
| Taxonomy router | Learns category semantics without injecting thousands of labels into every LLM prompt |
| Correction memory | Stores human corrections for better future routing/classification |

## 1.3 Key paths

```text
/opt/local-doc-classifier/
├── docker-compose.yml
├── .env
├── docclass
├── taxcat
├── classifier/
├── taxonomy-router/
├── config/
├── input/
├── output/
├── vault/
├── ollama/
├── cache/
├── logs/
└── tmp/
```

Important generated paths:

```text
/opt/local-doc-classifier/output/manifest.jsonl
/opt/local-doc-classifier/vault/Classification Index.md
/opt/local-doc-classifier/vault/01 Classified/
/opt/local-doc-classifier/vault/02 Needs Review/
/opt/local-doc-classifier/vault/90 Attachments/
/opt/local-doc-classifier/config/categories.txt
/opt/local-doc-classifier/config/categories.full.txt
/opt/local-doc-classifier/config/corrections.jsonl
/opt/local-doc-classifier/config/taxonomy-router.joblib
```

---

# 2. Initial Docker/Ollama/Classifier Setup

## 2.1 Core install target

The classifier stack lives under:

```bash
/opt/local-doc-classifier
```

The repo/package is designed to deploy there.

## 2.2 Main `.env` shape

```env
APP_DIR=/opt/local-doc-classifier
CLASSIFY_MODEL=qwen2.5:3b
VISION_MODEL=qwen2.5vl:3b
PULL_VISION_MODEL=1
TZ=America/Anchorage
OLLAMA_PORT=11434
CLASSIFIER_API_PORT=4319
CLASSIFIER_API_BIND=0.0.0.0
CLASSIFIER_API_TOKEN=CHANGE_ME_GENERATE_WITH_OPENSSL
```

Do not commit the real `.env`.

## 2.3 Confirm Ollama models

Inside the Ollama container:

```bash
docker exec -it local-doc-classifier-ollama ollama list
```

Expected models:

```text
qwen2.5vl:3b
qwen2.5:3b
```

## 2.4 Test text model directly

```bash
docker exec -it local-doc-classifier-ollama ollama run qwen2.5:3b "Classify this document: Amazon receipt for Broad Spectrum Sunscreen SPF 30, total 18.99. Return one label and one sentence."
```

---

# 3. HTTP API

## 3.1 Why the HTTP API was added

Originally, the classifier could be invoked through SSH or direct Docker commands. A non-SSH path was requested so Windows/macOS/iCloudPlugin could submit documents directly.

The FastAPI wrapper exposes the classifier over LAN:

```text
http://192.168.50.196:4319
```

## 3.2 API endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `/health` | GET | Verify Ollama/API/vault/classifier availability |
| `/classify/upload` | POST | Upload and classify a file |
| `/recent` | GET | Return recent manifest records |
| `/index` | GET | Return Obsidian Classification Index |
| `/note` | GET | Return a vault-relative Markdown note |
| `/categories` | GET | Return active categories and groups |
| `/corrections` | GET | Return correction memory |
| `/corrections` | POST | Add a correction |

All API calls require:

```text
X-API-Key: <CLASSIFIER_API_TOKEN>
```

## 3.3 Health test from Linux

```bash
TOKEN="$(grep '^CLASSIFIER_API_TOKEN=' /opt/local-doc-classifier/.env | cut -d= -f2-)"
curl -sS -H "X-API-Key: ${TOKEN}" http://127.0.0.1:4319/health | jq
```

Expected shape:

```json
{
  "ok": true,
  "ollama_ok": true,
  "ollama_error": null,
  "ollama_url": "http://ollama:11434",
  "input_root": "/input/api",
  "output_root": "/output",
  "vault_root": "/vault",
  "classification_index": "/vault/Classification Index.md",
  "manifest": "/output/manifest.jsonl",
  "classifier_script_exists": true
}
```

## 3.4 Health test from Windows PowerShell

```powershell
$server = "192.168.50.196"
$token = "PASTE_TOKEN_HERE"

curl.exe -sS -H "X-API-Key: $token" "http://${server}:4319/health"
```

---

# 4. Windows Upload Tests

## 4.1 PDF upload

```powershell
$server = "192.168.50.196"
$token = "PASTE_TOKEN_HERE"
$pdfPath = "$env:USERPROFILE\Downloads\FSA_SPF_Reimbursement_Packet_with_Receipts_Updated.pdf"

Test-Path $pdfPath

curl.exe -sS `
  -H "X-API-Key: $token" `
  -F "file=@$pdfPath;filename=FSA_SPF_Reimbursement_Packet_with_Receipts_Updated.pdf;type=application/pdf" `
  "http://${server}:4319/classify/upload"
```

## 4.2 Word upload

```powershell
$docxPath = "C:\Code\TestAI\FSA_SPF_Reimbursement_Packet.docx"

curl.exe -sS `
  -H "X-API-Key: $token" `
  -F "file=@$docxPath;filename=FSA_SPF_Reimbursement_Packet.docx;type=application/vnd.openxmlformats-officedocument.wordprocessingml.document" `
  "http://${server}:4319/classify/upload"
```

## 4.3 Image upload

Important: always force the multipart filename, or the API may see an empty extension.

```powershell
$imagePath = "C:\Code\TestAI\snowy-industrial-waystation-reference.jpg"

curl.exe -sS `
  -H "X-API-Key: $token" `
  -F "file=@$imagePath;filename=snowy-industrial-waystation-reference.jpg;type=image/jpeg" `
  "http://${server}:4319/classify/upload"
```

---

# 5. Windows Test Script

A Windows test script was created for:

```text
C:\Code\TestAI\Test-LocalClassifier.ps1
```

Final repo copy lives under:

```text
tests/windows/Test-LocalClassifier.ps1
```

## 5.1 Run with SSH token retrieval

```powershell
Set-ExecutionPolicy -Scope Process Bypass -Force
C:\Code\local-doc-classifier\tests\windows\Test-LocalClassifier.ps1 -FetchTokenOverSsh
```

## 5.2 Run with token manually

```powershell
Set-ExecutionPolicy -Scope Process Bypass -Force
C:\Code\local-doc-classifier\tests\windows\Test-LocalClassifier.ps1 -Token "PASTE_TOKEN_HERE"
```

## 5.3 What the script does

It uploads one file of each type from `C:\Code\TestAI`:

- image
- PDF
- Word document

It saves result files under:

```text
C:\Code\TestAI\_classifier-test-results
```

Files include:

```text
health.json
image-upload-response.json
pdf-upload-response.json
word-upload-response.json
recent.json
classification-index.md
```

---

# 6. Confirmed Working Test Results

## 6.1 Health

The health response showed:

```json
{
  "ok": true,
  "ollama_ok": true
}
```

## 6.2 PDF

The FSA SPF reimbursement PDF classified successfully.

Representative result:

```text
primary_label: receipt
secondary_labels: financial
confidence: 1.0
```

Representative generated note:

```text
/vault/01 Classified/receipt/98fb645093264ad983c2b830969484ce-FSA_SPF_Reimbursement_Packet_with_Receipts_Updated - receipt - f806ce37aebb.md
```

## 6.3 Word

The FSA SPF reimbursement Word document classified successfully.

Representative result:

```text
primary_label: receipt
secondary_labels: invoice, financial
confidence: 0.9
```

Representative generated note:

```text
/vault/01 Classified/receipt/a55e2492b6474e2387bde01fe8868854-FSA_SPF_Reimbursement_Packet - receipt - 3b395d7c3ba8.md
```

## 6.4 Image

The image classifier successfully interpreted the visible content:

```text
snowy industrial facility / waystation with pipes and machinery
```

But it initially mislabeled it as:

```text
technical
```

This was treated as a label policy problem, not a vision failure. Fixes added:

- image-safe category filtering
- visual-reference-first image candidate list
- correction memory
- post-classification image normalizer

Desired image result:

```text
primary_label: reference-image
secondary_labels: concept-art, environment-art, industrial, sci-fi, snow-ice, facility, waystation, architecture
```

---

# 7. Major Troubleshooting Notes

## 7.1 API port refused

Symptom:

```text
curl: (7) Failed to connect to 192.168.50.196 port 4319
```

Cause:

- API container stopped
- local image was pruned
- Docker tried to pull `local-doc-classifier-worker:latest` from Docker Hub

Fix:

```bash
cd /opt/local-doc-classifier
docker compose build classifier
docker compose up -d ollama api
docker compose ps
```

If Compose tries to pull the local image:

```bash
cd /opt/local-doc-classifier
docker compose up -d --build ollama api
```

## 7.2 Local image missing after prune

Symptom:

```text
pull access denied for local-doc-classifier-worker
```

Fix:

```bash
cd /opt/local-doc-classifier
docker compose build classifier
docker compose up -d api
```

## 7.3 Docker container name conflict

Symptom:

```text
Conflict. The container name "...local-doc-classifier-api" is already in use
```

Fix:

```bash
cd /opt/local-doc-classifier
docker compose rm -sf api || true
docker ps -aq --filter "name=local-doc-classifier-api" | xargs -r docker rm -f
docker compose up -d --build api
```

## 7.4 PDF parsing failed: missing libGL

Symptom:

```text
libGL.so.1: cannot open shared object file: No such file or directory
```

Fix in `classifier/Dockerfile`:

```text
libgl1
libglib2.0-0
```

Then rebuild:

```bash
cd /opt/local-doc-classifier
docker compose build classifier
docker compose up -d --force-recreate api
```

## 7.5 Disk full during Docker build

Symptom:

```text
no space left on device
/var/lib/containerd/...
```

Check disk:

```bash
df -h
```

Clean safely:

```bash
docker compose -f /opt/local-doc-classifier/docker-compose.yml down
docker container prune -f
docker image prune -af
docker builder prune -af
docker system prune -af
apt-get clean
apt-get autoremove -y
journalctl --vacuum-size=500M
df -h
```

Do not use `docker system prune --volumes` unless you are intentionally deleting volumes.

## 7.6 Multipart upload had blank extension

Symptom:

```json
{"detail":"Unsupported extension: "}
```

Cause:

`curl` sent upload without a usable filename.

Fix:

```powershell
-F "file=@$imagePath;filename=test-image.jpg;type=image/jpeg"
```

## 7.7 `/corrections` returned 404

Symptom:

```json
{"detail":"Not Found"}
```

Cause:

API source or rebuilt image did not include the correction route.

Fix:

- ensure `api_server.py` includes `/corrections`
- rebuild classifier
- remove stale API container
- restart API

```bash
cd /opt/local-doc-classifier
docker compose build classifier
docker compose rm -sf api || true
docker ps -aq --filter "name=local-doc-classifier-api" | xargs -r docker rm -f
docker compose up -d api
```

---

# 8. NVIDIA / GPU Notes

The host had an NVIDIA GPU detected by PCI:

```text
NVIDIA Corporation AD107M [GeForce RTX 4050 Max-Q / Mobile]
```

But initially:

```text
nvidia-smi: command not found
```

This meant no NVIDIA driver/user utilities were installed.

## 8.1 Enable Ubuntu restricted repo if needed

NVIDIA packages require the restricted repository.

Check components:

```bash
grep -R "Components:" /etc/apt/sources.list /etc/apt/sources.list.d/*.sources 2>/dev/null
```

If needed, ensure components include:

```text
main restricted universe multiverse
```

## 8.2 Install driver

```bash
apt-get update
apt-get install -y ubuntu-drivers-common linux-headers-$(uname -r)
ubuntu-drivers devices
ubuntu-drivers list --gpgpu
```

Observed recommendation included:

```text
nvidia-driver-595-open
```

Install:

```bash
apt-get install -y nvidia-driver-595-open nvidia-utils-595
reboot
```

Then:

```bash
nvidia-smi
```

## 8.3 Docker GPU support

After `nvidia-smi` works:

```bash
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
apt-get update
apt-get install -y nvidia-container-toolkit
nvidia-ctk runtime configure --runtime=docker
systemctl restart docker
```

Test:

```bash
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
```

## 8.4 Recommendation

Use GPU for Ollama inference if available.

Keep the classifier/API container mostly CPU/simple unless intentionally adding GPU OCR.

---

# 9. Obsidian Vault and SMB Access

## 9.1 Vault path

```text
/opt/local-doc-classifier/vault
```

## 9.2 SMB share for vault

Suggested Samba share:

```bash
apt-get update
apt-get install -y samba

chown -R kay:kay /opt/local-doc-classifier/vault
find /opt/local-doc-classifier/vault -type d -exec chmod 2775 {} \;
find /opt/local-doc-classifier/vault -type f -exec chmod 664 {} \;

tee -a /etc/samba/smb.conf >/dev/null <<'EOF'

[obsidian-vault]
   path = /opt/local-doc-classifier/vault
   browseable = yes
   read only = no
   guest ok = no
   valid users = kay
   force user = kay
   force group = kay
   create mask = 0664
   directory mask = 2775
EOF

smbpasswd -a kay
systemctl enable --now smbd
systemctl restart smbd
```

Windows path:

```text
\\192.168.50.196\obsidian-vault
```

macOS Finder path:

```text
smb://192.168.50.196/obsidian-vault
```

Open that folder as an Obsidian vault.

---

# 10. Public Taxonomy Sync

## 10.1 Goal

The classifier should occasionally pull updated classification/category lists from public sources, cache them locally, and train a taxonomy router.

It should not dump thousands of categories into every LLM prompt.

## 10.2 Sources configured

- Open Images boxable classes
- Open Images all descriptions
- Google Product Taxonomy
- IAB Content Taxonomy
- DocLayNet static document/layout categories

## 10.3 Sync files

```text
/opt/local-doc-classifier/config/taxonomy-sources.json
/opt/local-doc-classifier/config/categories.local.txt
/opt/local-doc-classifier/config/categories.txt
/opt/local-doc-classifier/config/categories.full.txt
/opt/local-doc-classifier/config/categories.public.clean.txt
/opt/local-doc-classifier/config/taxonomy-sync-report.json
```

## 10.4 Manual sync

```bash
cd /opt/local-doc-classifier
./taxcat sync
./taxcat status
./taxcat count
```

## 10.5 Timer

A systemd timer was configured:

```text
local-doc-classifier-taxonomy-sync.timer
```

Check:

```bash
systemctl list-timers | grep local-doc-classifier
```

The timer was configured for weekly Sunday around 03:23 server time with randomized delay.

If Alaska time is desired:

```bash
timedatectl set-timezone America/Anchorage
timedatectl
```

---

# 11. Taxonomy Router

## 11.1 Why it exists

The user wanted the LLM to “absorb” public category lists without sending the full list in every prompt.

Instead of fine-tuning the LLM immediately, the implemented solution is a lightweight local taxonomy router:

```text
public taxonomy lists
        ↓
categories.full.txt
        ↓
TF-IDF label index
        ↓
taxonomy-router.joblib
        ↓
shortlist likely labels
        ↓
LLM prompt sees only likely labels
```

## 11.2 Train router

```bash
cd /opt/local-doc-classifier
docker compose --profile tools run --rm --entrypoint python taxonomy-router /router/train_taxonomy_router.py
```

## 11.3 Test router

```bash
cd /opt/local-doc-classifier
docker compose --profile tools run --rm taxonomy-router --text "snowy industrial sci fi waystation exterior environment concept art reference image" --top 20
```

Expected likely labels:

```text
reference-image
concept-art
environment-art
industrial
sci-fi
snow-ice
waystation
facility
architecture
```

## 11.4 Why TF-IDF index was chosen

The first attempt used `SGDClassifier`, but failed with a large dense matrix allocation:

```text
numpy._core._exceptions._ArrayMemoryError
```

The TF-IDF label index avoids that by keeping a sparse similarity model.

---

# 12. Correction Memory

## 12.1 Correction JSONL path

```text
/opt/local-doc-classifier/config/corrections.jsonl
```

## 12.2 Add correction manually

```bash
cat >> /opt/local-doc-classifier/config/corrections.jsonl <<'EOF'
{"filename":"snowy-industrial-waystation-reference.jpg","extension":".jpg","kind":"image","old_label":"technical","correct_label":"reference-image","secondary_labels":["concept-art","environment-art","industrial","sci-fi","snow-ice","facility","waystation"],"note":"Snowy futuristic industrial facility / waystation image. This is visual reference or concept/environment art, not a technical document.","summary":"Futuristic snowy industrial facility with pipes and machinery."}
EOF
```

## 12.3 Add correction through API

```powershell
$server = "192.168.50.196"
$token = "PASTE_TOKEN_HERE"

$body = @{
  filename = "snowy-industrial-waystation-reference.jpg"
  extension = ".jpg"
  kind = "image"
  old_label = "technical"
  correct_label = "reference-image"
  secondary_labels = @("concept-art","environment-art","industrial","sci-fi","snow-ice","architecture","waystation","facility")
  note = "Snowy industrial sci-fi environment reference image, not a technical document, receipt, or screenshot."
  summary = "Frozen industrial waystation / facility concept-art reference."
} | ConvertTo-Json -Depth 5

curl.exe -sS `
  -H "X-API-Key: $token" `
  -H "Content-Type: application/json" `
  -d $body `
  "http://${server}:4319/corrections"
```

Then retrain router and rebuild API.

---

# 13. Reset Index and Clear Obsidian Vault

## 13.1 Goal

Reset generated outputs while preserving implementation, config, categories, corrections, router, Ollama models, and scripts.

The reset should clear:

- generated classified notes
- generated attachments
- extracted Markdown
- classification manifest
- API staging input
- Classification Index content

It should preserve:

- `.env`
- Docker Compose
- classifier code
- taxonomy router code
- config/category files
- corrections
- Ollama model data

## 13.2 Reset command

```bash
sudo /opt/local-doc-classifier/scripts/reset-vault-and-index.sh
```

## 13.3 What the reset script does

1. Creates a timestamped backup under:

```text
/opt/local-doc-classifier-backups
```

2. Stops API temporarily.
3. Clears:

```text
vault/01 Classified
vault/02 Needs Review
vault/90 Attachments
vault/_system/classifications
vault/_system/extracted-markdown
vault/Classification Index.md
output/manifest.jsonl
input/api
```

4. Recreates empty folders.
5. Writes a fresh `Classification Index.md`.
6. Restarts API.

---

# 14. Windows Repo Package

A Windows-friendly repo zip was generated:

```text
local-doc-classifier-repo-v1.0.0.zip
```

Unzip to:

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

Deploy to Linux:

```powershell
scp -r C:\Code\local-doc-classifier kay@192.168.50.196:/home/kay/local-doc-classifier-repo
ssh kay@192.168.50.196 "cd /home/kay/local-doc-classifier-repo && sudo ./scripts/install-or-update.sh"
```

Reset live generated vault/index after deployment:

```powershell
ssh kay@192.168.50.196 "sudo /opt/local-doc-classifier/scripts/reset-vault-and-index.sh"
```

---

# 15. Reproduction Checklist

## 15.1 On Windows

```powershell
cd C:\Code
Expand-Archive .\local-doc-classifier-repo-v1.0.0.zip -DestinationPath C:\Code
cd C:\Code\local-doc-classifier
git init
git add .
git commit -m "Initial local document classifier repo"
```

Copy to Linux:

```powershell
scp -r C:\Code\local-doc-classifier kay@192.168.50.196:/home/kay/local-doc-classifier-repo
```

## 15.2 On Linux

```bash
cd /home/kay/local-doc-classifier-repo
sudo ./scripts/install-or-update.sh
```

Sync categories:

```bash
cd /opt/local-doc-classifier
sudo ./taxcat sync
```

Train router:

```bash
cd /opt/local-doc-classifier
sudo docker compose --profile tools run --rm --entrypoint python taxonomy-router /router/train_taxonomy_router.py
```

Start API:

```bash
cd /opt/local-doc-classifier
sudo docker compose up -d ollama api
```

Health:

```bash
TOKEN="$(grep '^CLASSIFIER_API_TOKEN=' /opt/local-doc-classifier/.env | cut -d= -f2-)"
curl -sS -H "X-API-Key: ${TOKEN}" http://127.0.0.1:4319/health | jq
```

## 15.3 On Windows test machine

```powershell
Set-ExecutionPolicy -Scope Process Bypass -Force
C:\Code\local-doc-classifier\tests\windows\Test-LocalClassifier.ps1 -FetchTokenOverSsh
```

---

# 16. Final Desired Behavior

## 16.1 Document classification

PDF/Word/text documents should produce Markdown notes like:

```text
/vault/01 Classified/receipt/<filename> - receipt - <hash>.md
```

## 16.2 Image classification

Reference/concept art images should classify as:

```text
primary_label: reference-image
secondary_labels:
  - concept-art
  - environment-art
  - industrial
  - sci-fi
  - snow-ice
  - facility
  - waystation
  - architecture
```

## 16.3 Obsidian output

Every successful classification should write:

- one Markdown note
- optional attachment copy
- optional extracted Markdown
- updated `Classification Index.md`
- manifest record in `output/manifest.jsonl`

## 16.4 iCloudPlugin integration direction

The iCloud plugin should call the HTTP classifier API instead of SSH:

```text
POST http://192.168.50.196:4319/classify/upload
GET  http://192.168.50.196:4319/index
GET  http://192.168.50.196:4319/note?path=...
GET  http://192.168.50.196:4319/recent
```

Plugin results should reference:

```text
/vault/Classification Index.md
/vault/01 Classified/...
```

---

# 17. Open Items

These are not blockers but are worth tracking:

1. Rotate the API token after testing.
2. Confirm `/categories` and `/corrections` routes after every rebuild.
3. Confirm image classification now normalizes snowy industrial waystation images to `reference-image`.
4. Decide whether to enable NVIDIA GPU for Ollama after `nvidia-smi` works.
5. Add CI-style tests for API health, sample PDF, sample Word, and sample image.
6. Keep Obsidian vault generated content out of Git.
7. Decide whether to push the Windows repo to GitHub or keep it local/private.
