# Synthetic Fixture Testing

This repo includes committed synthetic fixtures under:

```text
tests/fixtures
```

These files contain no real personal, medical, financial, legal, infrastructure, or identity data. They are intentionally made-up artifacts designed to exercise the classifier across several domains.

## Fixtures

| File | Type | Expected behavior |
|---|---|---|
| `synthetic_vendor_service_agreement.pdf` | Legal PDF | `legal`, `contract`, `policy`, or `work` |
| `synthetic_network_incident_report.docx` | Technical Word doc | `technical`, `work`, `report`, or `policy` |
| `synthetic_quarterly_budget_forecast.xlsx` | Spreadsheet | `financial`, `spreadsheet`, `work`, or `report` |
| `synthetic_snowy_industrial_waystation_reference.jpg` | Image | `reference-image`, `concept-art`, `environment-art`, or `image-only` |

Expected labels are defined in:

```text
tests/fixtures/expected-labels.json
```

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

Results are written to:

```text
tests\_classifier-test-results
```

That directory is ignored by Git.

## Why committed fixtures are allowed

The repo intentionally ignores most real document/image formats by default, but explicitly allows files under `tests/fixtures`.

Do not commit real user files. Only synthetic fixture data belongs here.
