# Synthetic Fixture Testing

This repo includes committed synthetic fixtures under:

```text
tests/fixtures
```

These files contain no real personal, medical, financial, legal, infrastructure, or identity data. They are intentionally made-up artifacts designed to exercise the classifier across several domains.

## Fixtures

| File | Type | Expected behavior |
|---|---|---|
| `synthetic_vendor_service_agreement.pdf` | Legal PDF | `legal`, `contract`, `policy`, or `work`; should prefer the fast document path when text extraction is clean |
| `synthetic_network_incident_report.docx` | Technical Word doc | `technical`, `work`, `report`, or `policy`; should prefer the fast document path when the incident-report structure is clear |
| `synthetic_quarterly_budget_forecast.xlsx` | Spreadsheet | `financial`, `spreadsheet`, `work`, or `report`; should use the fast spreadsheet path rather than slow OCR/LLM classification |
| `synthetic_snowy_industrial_waystation_reference.jpg` | Image | `reference-image`, `concept-art`, `environment-art`, or `image-only` |

Expected labels are defined in:

```text
tests/fixtures/expected-labels.json
```

Issue tracking:

- [#1](https://github.com/NeonButrfly/local-doc-classifier/issues/1) finalizes the visual-reference label policy for the snowy industrial waystation fixture and requires the live API to normalize document-style image misclassifications back to `reference-image`.

## Run tests from Windows

```powershell
cd C:\Code\local-doc-classifier
Set-ExecutionPolicy -Scope Process Bypass -Force
.\tests\windows\Test-LocalClassifier.ps1 -FetchTokenOverSsh
```

Or with a pasted token:

```powershell
.\tests\windows\Test-LocalClassifier.ps1 -Token "PASTE_TOKEN_HERE"
```

## Run tests from Linux or Raspberry Pi

```bash
cd /path/to/local-doc-classifier
chmod +x ./tests/linux/test-local-classifier.sh
./tests/linux/test-local-classifier.sh --server 192.168.50.196 --token "PASTE_TOKEN_HERE"
```

Or fetch the token over SSH if your Pi can read the deployment host:

```bash
./tests/linux/test-local-classifier.sh --server 192.168.50.196 --fetch-token-over-ssh
```

## Benchmark upload speed separately from classification

From a Raspberry Pi or another Linux client:

```bash
cd /path/to/local-doc-classifier
chmod +x ./tests/linux/benchmark-upload-vs-classify.sh
./tests/linux/benchmark-upload-vs-classify.sh \
  --server 192.168.50.196 \
  --file tests/fixtures/synthetic_quarterly_budget_forecast.xlsx \
  --token "PASTE_TOKEN_HERE" \
  --repeats 3
```

That script hits both:

- `/benchmark/upload-only` to measure transfer and staging time without decision-making
- `/classify/upload` to compare the full end-to-end cost, including worker-side `parse_ms`, `model_ms`, `note_write_ms`, and `total_ms`

Results are written to:

```text
tests\_classifier-test-results
```

That directory is ignored by Git.

## Why committed fixtures are allowed

The repo intentionally ignores most real document/image formats by default, but explicitly allows files under `tests/fixtures`.

Do not commit real user files. Only synthetic fixture data belongs here.
