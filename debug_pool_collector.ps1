param(
    [int] $IntervalSeconds = 300,
    [int] $MaxFiles = 288  # 보관할 최대 파일 수 (기본: 288 -> 24시간@5분 간격)
)

# 루트 기준 debug_logs 디렉터리
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$DebugDir = Join-Path $ScriptDir "debug_logs"
if (-not (Test-Path $DebugDir)) { New-Item -Path $DebugDir -ItemType Directory | Out-Null }

Write-Output "debug_pool_collector starting. IntervalSeconds=$IntervalSeconds, debug dir=$DebugDir"

while ($true) {
    try {
        $ts = Get-Date -Format "yyyyMMdd_HHmmss"
        $outFile = Join-Path $DebugDir ("pool_dump_$ts.txt")
        $latest = Join-Path $DebugDir "latest_pool_dump.txt"
        Write-Output "[$(Get-Date -Format HH:mm:ss)] Running debug_pool_dump -> $outFile"

        # 파이썬 스크립트 실행: stdout/stderr 모두 캡처
        # PowerShell: 2>&1 로 stderr를 합쳐 파일에 쓴다
        & python .\debug_pool_dump.py --verbose 2>&1 | Out-File -FilePath $outFile -Encoding utf8

        # 최신 복사(항상 덮어쓰기)
        Copy-Item -Path $outFile -Destination $latest -Force

        # 파일 회전: 오래된 파일 삭제
        try {
            $files = Get-ChildItem -Path $DebugDir -Filter "pool_dump_*.txt" | Sort-Object LastWriteTime -Descending
            if ($files.Count -gt $MaxFiles) {
                $toDelete = $files | Select-Object -Skip $MaxFiles
                foreach ($f in $toDelete) {
                    Remove-Item -Path $f.FullName -Force -ErrorAction SilentlyContinue
                }
            }
        } catch {
            Write-Output "File rotation failed: $_"
        }
    } catch {
        Write-Output "Collector run failed: $_"
    }

    Start-Sleep -Seconds $IntervalSeconds
}
