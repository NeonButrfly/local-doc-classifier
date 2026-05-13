param(
  [string]$Server = "192.168.50.196",
  [string]$RepoRoot = "",
  [string]$Token = "",
  [switch]$FetchTokenOverSsh,
  [switch]$SkipAssertions
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
  $RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
}

$ApiBase = "http://${Server}:4319"
$FixtureDir = Join-Path $RepoRoot "tests\fixtures"
$OutDir = Join-Path $RepoRoot "tests\_classifier-test-results"
$ExpectedPath = Join-Path $FixtureDir "expected-labels.json"

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

if ([string]::IsNullOrWhiteSpace($Token) -and $FetchTokenOverSsh) {
  $Token = (ssh kay@${Server} "grep '^CLASSIFIER_API_TOKEN=' /opt/local-doc-classifier/.env | cut -d= -f2-").Trim()
}

if ([string]::IsNullOrWhiteSpace($Token)) {
  $Token = Read-Host "Paste CLASSIFIER_API_TOKEN"
}

function Get-MimeType {
  param([string]$Path)
  $Ext = [System.IO.Path]::GetExtension($Path).ToLowerInvariant()
  switch ($Ext) {
    ".pdf"  { return "application/pdf" }
    ".docx" { return "application/vnd.openxmlformats-officedocument.wordprocessingml.document" }
    ".doc"  { return "application/msword" }
    ".xlsx" { return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" }
    ".xls"  { return "application/vnd.ms-excel" }
    ".png"  { return "image/png" }
    ".jpg"  { return "image/jpeg" }
    ".jpeg" { return "image/jpeg" }
    ".webp" { return "image/webp" }
    ".bmp"  { return "image/bmp" }
    ".tif"  { return "image/tiff" }
    ".tiff" { return "image/tiff" }
    default { return "application/octet-stream" }
  }
}

function Assert-Classification {
  param(
    [string]$FixtureName,
    [object]$Response,
    [object]$Expected
  )

  if ($SkipAssertions) { return }

  if ($Response.ok -ne $true) {
    throw "Fixture ${FixtureName} failed classification API call."
  }

  if (-not $Response.record.classification.primary_label) {
    throw "Fixture ${FixtureName} produced no primary_label."
  }

  $primary = [string]$Response.record.classification.primary_label
  $secondary = @($Response.record.classification.secondary_labels)

  if ($Expected.acceptable_primary_labels -and ($Expected.acceptable_primary_labels -notcontains $primary)) {
    throw "Fixture ${FixtureName} primary_label '$primary' not in acceptable list: $($Expected.acceptable_primary_labels -join ', ')"
  }

  if ($Expected.forbidden_primary_labels -and ($Expected.forbidden_primary_labels -contains $primary)) {
    throw "Fixture ${FixtureName} primary_label '$primary' is forbidden."
  }

  if ($Expected.expected_secondary_any) {
    $hit = $false
    foreach ($label in $Expected.expected_secondary_any) {
      if ($secondary -contains $label -or $primary -eq $label) {
        $hit = $true
        break
      }
    }
    if (-not $hit) {
      throw "Fixture ${FixtureName} did not include any expected secondary label. Expected one of: $($Expected.expected_secondary_any -join ', '). Got primary='$primary', secondary='$($secondary -join ', ')'"
    }
  }
}

Write-Host "Testing classifier API at ${ApiBase}" -ForegroundColor Cyan
Write-Host "Repo root: ${RepoRoot}" -ForegroundColor Cyan
Write-Host "Fixture dir: ${FixtureDir}" -ForegroundColor Cyan

if (-not (Test-Path $FixtureDir)) {
  throw "Fixture directory not found: ${FixtureDir}"
}

$healthRaw = curl.exe -sS -H "X-API-Key: $Token" "${ApiBase}/health"
$healthPath = Join-Path $OutDir "health.json"
$healthRaw | Set-Content -Encoding UTF8 $healthPath
$health = $healthRaw | ConvertFrom-Json

if (-not $health.ok) {
  throw "Classifier health check failed. See ${healthPath}"
}

Write-Host "Health OK. Ollama OK: $($health.ollama_ok)" -ForegroundColor Green

$expectedDoc = Get-Content $ExpectedPath -Raw | ConvertFrom-Json
$results = @()

foreach ($fixture in $expectedDoc.fixtures) {
  $filePath = Join-Path $FixtureDir $fixture.file
  if (-not (Test-Path $filePath)) {
    throw "Missing fixture: $filePath"
  }

  $mime = Get-MimeType -Path $filePath
  $responsePath = Join-Path $OutDir "$($fixture.kind)-upload-response.json"

  Write-Host "Uploading $($fixture.kind): $filePath" -ForegroundColor Cyan

  $responseRaw = curl.exe -sS `
    -H "X-API-Key: $Token" `
    -F "file=@$filePath;filename=$($fixture.file);type=${mime}" `
    "${ApiBase}/classify/upload"

  $responseRaw | Set-Content -Encoding UTF8 $responsePath
  $response = $responseRaw | ConvertFrom-Json

  if ($response.ok -eq $true) {
    $label = $response.record.classification.primary_label
    $confidence = $response.record.classification.confidence
    $note = $response.record.note_path
    Write-Host "PASS upload: $($fixture.file) => $label confidence=$confidence" -ForegroundColor Green
    Write-Host "Note: $note" -ForegroundColor Green
  } else {
    Write-Host "FAIL upload: $($fixture.file)" -ForegroundColor Red
    if ($response.record.error) { Write-Host "Error: $($response.record.error)" -ForegroundColor Red }
    if ($response.stderr_tail) { Write-Host "stderr_tail: $($response.stderr_tail)" -ForegroundColor DarkYellow }
  }

  Assert-Classification -FixtureName $fixture.file -Response $response -Expected $fixture
  $results += $response
}

$recentPath = Join-Path $OutDir "recent.json"
curl.exe -sS -H "X-API-Key: $Token" "${ApiBase}/recent?limit=10" | Set-Content -Encoding UTF8 $recentPath

$indexPath = Join-Path $OutDir "classification-index.md"
curl.exe -sS -H "X-API-Key: $Token" "${ApiBase}/index?max_chars=30000" | Set-Content -Encoding UTF8 $indexPath

Write-Host ""
Write-Host "Done. Results saved to: ${OutDir}" -ForegroundColor Cyan
Write-Host "Health: ${healthPath}"
Write-Host "Recent: ${recentPath}"
Write-Host "Index: ${indexPath}"
