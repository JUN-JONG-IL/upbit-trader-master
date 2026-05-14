# rename-02data-to-data_01-auto.ps1
# 위치: 레포 루트에서 실행
# 목적: src 내부 "02_data" -> "data_01" 치환 (인코딩 보존), .bak 백업, git mv 시도, 자동 커밋(선택적)

chcp 65001 > $null
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"

$OLD = "02_data"
$NEW = "data_01"
$BRANCH = "rename-02data-to-data_01"

Write-Host "`nSTART: rename $OLD -> $NEW (branch: $BRANCH)"
Write-Host "Working dir: $(Get-Location)`n"

function Get-FileEncodingName([string]$path) {
  if (-not (Test-Path $path)) { return $null }
  $fs = [System.IO.File]::OpenRead($path)
  try {
    $bytes = New-Object byte[] 4
    $read = $fs.Read($bytes, 0, 4)
  } finally {
    $fs.Close()
  }
  if ($read -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) { return "UTF8" }
  if ($read -ge 2 -and $bytes[0] -eq 0xFF -and $bytes[1] -eq 0xFE) { return "Unicode" }
  if ($read -ge 2 -and $bytes[0] -eq 0xFE -and $bytes[1] -eq 0xFF) { return "BigEndianUnicode" }
  if ($read -ge 4 -and $bytes[0] -eq 0x00 -and $bytes[1] -eq 0x00 -and $bytes[2] -eq 0xFE -and $bytes[3] -eq 0xFF) { return "UTF32" }
  return "Default"
}

function Read-FilePreserve([string]$path) {
  $encName = Get-FileEncodingName $path
  try {
    if ($encName -eq "Default") { $text = Get-Content -Raw -Encoding Default -ErrorAction Stop $path }
    else { $text = Get-Content -Raw -Encoding $encName -ErrorAction Stop $path }
    return @{ Text = $text; Encoding = $encName }
  } catch {
    Write-Warning "읽기 실패($path): $_"
    return @{ Text = ""; Encoding = $encName }
  }
}

function Write-FilePreserve([string]$path, [string]$text, [string]$encName) {
  try {
    if ($encName -eq "Default") { Set-Content -Path $path -Value $text -Encoding Default -Force }
    else { Set-Content -Path $path -Value $text -Encoding $encName -Force }
    return $true
  } catch {
    Write-Warning "쓰기 실패($path): $_"
    return $false
  }
}

if (-not (Test-Path ".git")) { Write-Error ".git not found in current directory. cd to repo root."; exit 1 }

# auto stash if dirty
$status = (git status --porcelain) -join "`n"
$stashed = $false
$stashRef = $null
if (-not [string]::IsNullOrWhiteSpace($status)) {
  Write-Host "Working tree dirty: creating stash..."
  $stashOutput = git stash push -u -m "auto: pre-rename stash $(Get-Date -Format s)" 2>&1
  $stashExit = $LASTEXITCODE
  Write-Host $stashOutput
  if ($stashExit -ne 0) { Write-Warning "git stash failed (exit code $stashExit). Aborting."; exit 1 }
  if ($stashOutput -match "stash@\{\d+\}") { $stashRef = $matches[0] } else { $stashRef = "stash@{0}" }
  $stashed = $true
  Write-Host "Created stash: $stashRef"
} else { Write-Host "Working tree clean." }

# branch create/checkout (기본 브랜치에서 새 브랜치 만들려면 사용자가 default branch로 체크아웃하세요)
git rev-parse --verify $BRANCH > $null 2>&1
if ($LASTEXITCODE -eq 0) { git checkout $BRANCH } else { git checkout -b $BRANCH }
if ($LASTEXITCODE -ne 0) { Write-Error "git checkout failed"; exit 1 }

# git mv folder if exists
if (Test-Path "src\$OLD") {
  Write-Host "Renaming folder src\$OLD -> src\$NEW via git mv"
  git mv "src\$OLD" "src\$NEW" 2>&1
  if ($LASTEXITCODE -ne 0) { Write-Warning "git mv failed; continuing with textual replacements." }
} else {
  Write-Host "Folder src\$OLD not found; performing textual replacements only."
}

# search files and preserve encoding
$exts = @("*.py","*.pyw","*.md","*.rst","*.json","*.yml","*.yaml","*.ini","*.cfg","*.sh","*.ps1","*.txt","*.xml","*.html","Dockerfile")
$files = @()
foreach ($e in $exts) { try { $files += Get-ChildItem -Recurse -File -Include $e -ErrorAction SilentlyContinue } catch {} }
$files = $files | Sort-Object -Unique
$matchFiles = @()
foreach ($f in $files) {
  try {
    $r = Read-FilePreserve $f.FullName
    if ($null -ne $r.Text -and $r.Text -match [regex]::Escape($OLD)) { $matchFiles += @{ Path = $f.FullName; Encoding = $r.Encoding } }
  } catch {}
}

if ($matchFiles.Count -eq 0) { Write-Host "No files found that contain '$OLD'." }
else {
  Write-Host "Files to be updated: $($matchFiles.Count)"
  foreach ($m in $matchFiles) { Write-Host " - $($m.Path) (encoding: $($m.Encoding))" }
}

# replacements with .bak
foreach ($m in $matchFiles) {
  $path = $m.Path; $enc = $m.Encoding
  try {
    $bak = $path + ".bak"
    if (-not (Test-Path $bak)) { Copy-Item -Path $path -Destination $bak -ErrorAction Stop; Write-Host "백업: $bak" }
    $r = Read-FilePreserve $path; $content = $r.Text
    $newcontent = $content -replace [regex]::Escape($OLD), $NEW
    if ($newcontent -ne $content) { $ok = Write-FilePreserve $path $newcontent $enc; if ($ok) { Write-Host "Replaced in: $path (encoding preserved: $enc)" } else { Write-Warning "Failed to write: $path" } } else { Write-Host "No replacement needed: $path" }
  } catch { Write-Warning "Error processing $path : $_" }
}

# stage & commit
git add -A
$staged = git --no-pager diff --staged --name-only 2>&1; Write-Host $staged
git commit -m "chore: rename src/$OLD -> src/$NEW and update imports (automated)" 2>&1
if ($LASTEXITCODE -ne 0) { Write-Warning "git commit failed or nothing to commit (exit code $LASTEXITCODE). Continuing." } else { Write-Host "Commit created." }

# python compile check
python -m compileall -q .
if ($LASTEXITCODE -ne 0) { Write-Warning "compileall reported issues; check Python files." } else { Write-Host "Python compile check passed." }

# stash restore
if ($stashed -and $stashRef) {
  Write-Host "Attempting to pop stash $stashRef ..."
  git stash pop $stashRef --index 2>&1
  if ($LASTEXITCODE -ne 0) { Write-Warning "git stash pop failed or conflicts occurred. Run 'git stash list' and resolve manually." } else { Write-Host "Stash popped." }
} elseif ($stashed) {
  Write-Host "Attempting to pop latest stash ..."
  git stash pop --index 2>&1
  if ($LASTEXITCODE -ne 0) { Write-Warning "git stash pop failed or conflicts occurred. Please resolve manually." } else { Write-Host "Stash popped." }
}

Write-Host "`nDONE: rename operation finished. Verify app runs and fix any remaining import/syntax issues manually."
