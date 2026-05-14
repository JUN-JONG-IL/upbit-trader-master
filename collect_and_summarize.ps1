param(
    [int] $Count = 6,
    [int] $IntervalSeconds = 300
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$DebugDir = Join-Path $ScriptDir "debug_logs"
if (-not (Test-Path $DebugDir)) { New-Item -Path $DebugDir -ItemType Directory | Out-Null }

Write-Output "Collecting $Count pool dumps every $IntervalSeconds seconds -> $DebugDir"

$collected = @()
for ($i=1; $i -le $Count; $i++) {
    $ts = Get-Date -Format "yyyyMMdd_HHmmss"
    $outFile = Join-Path $DebugDir ("pool_dump_$ts.txt")
    try {
        Write-Output ("[{0}] ({1}/{2}) Running debug_pool_dump -> {3}" -f (Get-Date -Format HH:mm:ss), $i, $Count, $outFile)
        & python .\debug_pool_dump.py --verbose 2>&1 | Out-File -FilePath $outFile -Encoding utf8
        Copy-Item -Path $outFile -Destination (Join-Path $DebugDir "latest_pool_dump.txt") -Force
        $collected += $outFile
    } catch {
        Write-Output ("Collector run failed for attempt {0}: {1}" -f $i, $_)
    }

    if ($i -lt $Count) {
        Start-Sleep -Seconds $IntervalSeconds
    }
}

# 요약 파일 생성
$summary = Join-Path $DebugDir ("pool_dump_summary_{0}.txt" -f (Get-Date -Format "yyyyMMdd_HHmmss"))
Write-Output ("Creating summary: {0}" -f $summary)
"`n== Pool dump summary generated at $(Get-Date) ==`n" | Out-File -FilePath $summary -Encoding utf8
"Collected files:`n" | Out-File -FilePath $summary -Append -Encoding utf8
$collected | ForEach-Object { $_ + "  (" + ((Get-Item $_).Length) + " bytes)" } | Out-File -FilePath $summary -Append -Encoding utf8
"`n--- Concatenated dump contents below ---`n" | Out-File -FilePath $summary -Append -Encoding utf8

foreach ($f in $collected) {
    ("`n>>> FILE: {0} `n" -f $f) | Out-File -FilePath $summary -Append -Encoding utf8
    Get-Content $f | Out-File -FilePath $summary -Append -Encoding utf8
}

# 압축 생성 (zip)
$zip = Join-Path $DebugDir ("pool_dumps_{0}.zip" -f (Get-Date -Format "yyyyMMdd_HHmmss"))
try {
    if (Test-Path $zip) { Remove-Item $zip -Force }
    Compress-Archive -Path ($collected + $summary) -DestinationPath $zip -Force
    Write-Output ("Created ZIP: {0}" -f $zip)
} catch {
    Write-Output ("ZIP creation failed: {0}" -f $_)
}

Write-Output ("Collection complete. Summary at: {0}" -f $summary)
