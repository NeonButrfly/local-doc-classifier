# Fixtures Update v1.0.2

This update removes the old FSA/SPF-focused fixture set and replaces it with diverse synthetic artifacts:

- fake legal PDF
- fake technical Word incident report
- fake financial spreadsheet
- fake sci-fi/industrial reference image

## Apply on Windows

From `C:\Code\local-doc-classifier`:

```powershell
Remove-Item .\tests\fixtures -Recurse -Force
Remove-Item .\tests\_classifier-test-results -Recurse -Force -ErrorAction SilentlyContinue
```

Then extract this zip over `C:\Code`.

```powershell
Expand-Archive .\local-doc-classifier-fixtures-update-v1.0.2.zip -DestinationPath C:\Code -Force
cd C:\Code\local-doc-classifier
git status
```

Commit:

```powershell
git add .gitignore tests\fixtures tests\windows\Test-LocalClassifier.ps1 docs\FIXTURE_TESTING.md scripts\windows\Replace-SyntheticFixtures.ps1 README-fixtures-update.md
git commit -m "replace classifier fixtures with diverse synthetic artifacts"
```

Run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass -Force
.\tests\windows\Test-LocalClassifier.ps1 -FetchTokenOverSsh
```
