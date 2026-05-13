param(
  [string]$Server = "192.168.50.196",
  [string]$TestDir = "C:\Code\TestAI",
  [string]$Token = "",
  [switch]$FetchTokenOverSsh
)

$ErrorActionPreference = "Stop"
$ApiBase = "http://${Server}:4319"
$OutDir = Join-Path $TestDir "_classifier-test-results"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

if ([string]::IsNullOrWhiteSpace($Token) -and $FetchTokenOverSsh) {
  $Token = (ssh kay@${Server} "grep '^CLASSIFIER_API_TOKEN=' /opt/local-doc-classifier/.env | cut -d= -f2-").Trim()
}

if ([string]::IsNullOrWhiteSpace($Token)) {
  $Token = Read-Host "Paste CLASSIFIER_API_TOKEN"
}

Write-Host "Testing classifier API at ${ApiBase}" -ForegroundColor Cyan

$healthRaw = curl.exe -sS -H "X-API-Key: $Token" "${ApiBase}/health"
$healthPath = Join-Path $OutDir "health.json"
$healthRaw | Set-Content -Encoding UTF8 $healthPath
$health = $healthRaw | ConvertFrom-Json

if (-not $health.ok) {
  throw "Classifier health check failed. See ${healthPath}"
}

Write-Host "Health OK. Ollama OK: $($health.ollama_ok)" -ForegroundColor Green

$ImageExts = @("*.png", "*.jpg", "*.jpeg", "*.webp", "*.bmp", "*.tif", "*.tiff")
$PdfExts = @("*.pdf")
$WordExts = @("*.docx", "*.doc")

function Get-FirstMatchingFile {
  param([string]$Root, [string[]]$Patterns)
  foreach ($Pattern in $Patterns) {
    $Found = Get-ChildItem -Path $Root -Filter $Pattern -File -Recurse |
      Where-Object { $_.FullName -notlike "*_classifier-test-results*" } |
      Sort-Object LastWriteTime -Descending |
      Select-Object -First 1
    if ($Found) { return $Found }
  }
  return $null
}

function Get-MimeType {
  param([string]$Path)
  $Ext = [System.IO.Path]::GetExtension($Path).ToLowerInvariant()
  switch ($Ext) {
    ".pdf"  { return "application/pdf" }
    ".docx" { return "application/vnd.openxmlformats-officedocument.wordprocessingml.document" }
    ".doc"  { return "application/msword" }
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

function Test-Upload {
  param([string]$Kind, [System.IO.FileInfo]$File)

  if (-not $File) {
    Write-Host "SKIP ${Kind}: no matching file found under ${TestDir}" -ForegroundColor Yellow
    return $null
  }

  $Mime = Get-MimeType -Path $File.FullName
  $SafeName = $Kind.ToLowerInvariant()
  $ResponsePath = Join-Path $OutDir "${SafeName}-upload-response.json"

  Write-Host "Uploading ${Kind}: $($File.FullName)" -ForegroundColor Cyan

  $ResponseRaw = curl.exe -sS `
    -H "X-API-Key: $Token" `
    -F "file=@$($File.FullName);filename=$($File.Name);type=${Mime}" `
    "${ApiBase}/classify/upload"

  $ResponseRaw | Set-Content -Encoding UTF8 $ResponsePath

  try {
    $Response = $ResponseRaw | ConvertFrom-Json
  } catch {
    Write-Host "FAIL ${Kind}: response was not JSON. See ${ResponsePath}" -ForegroundColor Red
    return $null
  }

  if ($Response.ok -eq $true) {
    Write-Host "PASS ${Kind}: classified successfully" -ForegroundColor Green
    if ($Response.record.note_path) {
      Write-Host "Note: $($Response.record.note_path)" -ForegroundColor Green
    }
    if ($Response.record.classification.primary_label) {
      Write-Host "Label: $($Response.record.classification.primary_label) Confidence: $($Response.record.classification.confidence)" -ForegroundColor Green
    }
  } else {
    Write-Host "FAIL ${Kind}: classifier returned ok=false. See ${ResponsePath}" -ForegroundColor Red
    if ($Response.record.error) {
      Write-Host "Error: $($Response.record.error)" -ForegroundColor Red
    }
    if ($Response.stderr_tail) {
      Write-Host "stderr_tail: $($Response.stderr_tail)" -ForegroundColor DarkYellow
    }
  }

  return $Response
}

$ImageFile = Get-FirstMatchingFile -Root $TestDir -Patterns $ImageExts
$PdfFile = Get-FirstMatchingFile -Root $TestDir -Patterns $PdfExts
$WordFile = Get-FirstMatchingFile -Root $TestDir -Patterns $WordExts

$Results = @()
$Results += Test-Upload -Kind "Image" -File $ImageFile
$Results += Test-Upload -Kind "PDF" -File $PdfFile
$Results += Test-Upload -Kind "Word" -File $WordFile

$RecentPath = Join-Path $OutDir "recent.json"
curl.exe -sS -H "X-API-Key: $Token" "${ApiBase}/recent?limit=10" | Set-Content -Encoding UTF8 $RecentPath

$IndexPath = Join-Path $OutDir "classification-index.md"
curl.exe -sS -H "X-API-Key: $Token" "${ApiBase}/index?max_chars=30000" | Set-Content -Encoding UTF8 $IndexPath

Write-Host ""
Write-Host "Done. Results saved to: ${OutDir}" -ForegroundColor Cyan
Write-Host "Health: ${healthPath}"
Write-Host "Recent: ${RecentPath}"
Write-Host "Index: ${IndexPath}"
