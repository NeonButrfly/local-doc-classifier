param(
  [string]$RepoRoot = "C:\Code\local-doc-classifier"
)

$ErrorActionPreference = "Stop"

$FixtureDir = Join-Path $RepoRoot "tests\fixtures"
$ResultsDir = Join-Path $RepoRoot "tests\_classifier-test-results"

Write-Host "Replacing synthetic fixtures under: $FixtureDir" -ForegroundColor Cyan

if (Test-Path $FixtureDir) {
  Remove-Item $FixtureDir -Recurse -Force
}

New-Item -ItemType Directory -Force -Path $FixtureDir | Out-Null

Write-Host "After extracting this overlay, the FSA/SPF fixtures should be gone." -ForegroundColor Green

if (Test-Path $ResultsDir) {
  Write-Host "Removing old fixture test results: $ResultsDir" -ForegroundColor Yellow
  Remove-Item $ResultsDir -Recurse -Force
}
