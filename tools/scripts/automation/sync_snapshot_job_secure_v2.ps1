# sync_snapshot_job_secure_v2.ps1
# 위치: <project-root>\scheduler\sync_snapshot_job_secure_v2.ps1
# 설명: 스크립트 위치를 기준으로 프로젝트 루트와 snapshot 폴더를 자동 계산합니다.
# 권장: 이 파일은 UTF-8 (BOM 없음)으로 저장하세요.

# --- 경로 설정 (동적, 안전한 폴백 포함) ---
$scriptDir = $PSScriptRoot
if (-not $scriptDir) {
  if ($MyInvocation.MyCommand.Path) { $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path }
  else { $scriptDir = (Get-Location).Path }
}
# project root = parent of scheduler folder
$work = Split-Path -Parent $scriptDir
# snapshot 파일 경로(루트/snapshot/)
$snapshotFile = Join-Path $work 'snapshot\snapshot_rows_clean.jsonl'
# 로그 파일(루트)
$log = Join-Path $work 'sync_snapshot_job.log'

# 타임스탬프 로깅 함수
function Write-Log {
  param($Message)
  $ts = (Get-Date).ToString("s")
  "$ts `t $Message" | Out-File -FilePath $log -Append -Encoding utf8
}

Write-Log "----- START -----"

try {
  Set-Location $work

  $mongoPass = $env:MONGO_PASS
  if (-not $mongoPass) {
    Write-Log "ERROR: MONGO_PASS environment variable is not set. Aborting."
    exit 1
  }

  # 안전하게 외부 프로세스 실행 결과(표준출력/표준오류)를 로그에 기록하는 함수
  function Invoke-Log {
    param(
      [Parameter(Mandatory=$true)][string]$ExePath,
      [Parameter(Mandatory=$true)][string]$ExeArgs
    )
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $ExePath
    $psi.Arguments = $ExeArgs
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true

    $p = [System.Diagnostics.Process]::Start($psi)
    $out = $p.StandardOutput.ReadToEnd()
    $err = $p.StandardError.ReadToEnd()
    $p.WaitForExit()

    if ($out -and $out.Trim().Length -gt 0) {
      $out -split "`r?`n" | ForEach-Object { Write-Log "OUT: $_" }
    }
    if ($err -and $err.Trim().Length -gt 0) {
      $err -split "`r?`n" | ForEach-Object { Write-Log "ERR: $_" }
    }
    return $p.ExitCode
  }

  # 1) TimescaleDB -> JSONL (직접 snapshotFile로 씀)
  # 사용되는 커맨드 라인에서 리디렉션(>)을 포함하므로 Invoke-Expression 사용
  $psqlSql = "COPY (SELECT row_to_json(t)::text FROM (SELECT symbol, timeframe, extract(epoch from last_time AT TIME ZONE 'UTC') AS last_time_epoch, extract(epoch from updated_at AT TIME ZONE 'UTC') AS updated_at_epoch FROM latest_snapshot) t) TO STDOUT;"
  $psqlCmd = "docker exec -i upbit-timescaledb psql -U app_user -d upbit_trader -t -A -c `"${psqlSql}`" > `"$snapshotFile`""
  Write-Log "Running psql -> snapshot: $psqlCmd"
  Invoke-Expression $psqlCmd 2>&1 | ForEach-Object { Write-Log "PSQL: $_" }

  # 확인: snapshot 파일이 만들어졌는지
  if (-not (Test-Path $snapshotFile)) {
    Write-Log "ERROR: snapshot file not created: $snapshotFile"
    throw "SnapshotNotCreated"
  }
  $fi = Get-Item $snapshotFile
  if ($fi.Length -eq 0) {
    Write-Log "WARNING: snapshot file is empty: $snapshotFile"
  } else {
    Write-Log "Snapshot file created: $snapshotFile (bytes: $($fi.Length))"
  }

  # 2) snapshot 파일을 Mongo 컨테이너로 복사
  $cpArgs = "cp `"$snapshotFile`" upbit-mongodb:/tmp/snapshot_rows.jsonl"
  Write-Log "docker $cpArgs"
  $rc = Invoke-Log -ExePath "docker" -ExeArgs $cpArgs
  if ($rc -ne 0) { Write-Log "ERROR: docker cp snapshot returned exit code $rc"; throw "DockerCpSnapshotFailed" }

  # 3) sync JS를 컨테이너로 복사 (scheduler 폴더의 js를 사용)
  $jsPath = Join-Path $scriptDir 'sync_snapshot_upsert_robust.js'
  if (-not (Test-Path $jsPath)) {
    # fallback: try project root
    $jsPathRoot = Join-Path $work 'sync_snapshot_upsert_robust.js'
    if (Test-Path $jsPathRoot) {
      $jsPath = $jsPathRoot
      Write-Log "Info: sync JS not found in scheduler; using $jsPathRoot"
    } else {
      Write-Log "ERROR: sync_snapshot_upsert_robust.js not found in scheduler or project root."
      throw "SyncJsNotFound"
    }
  }
  $cpJsArgs = "cp `"$jsPath`" upbit-mongodb:/tmp/sync_snapshot_upsert_robust.js"
  Write-Log "docker $cpJsArgs"
  $rc = Invoke-Log -ExePath "docker" -ExeArgs $cpJsArgs
  if ($rc -ne 0) { Write-Log "ERROR: docker cp js returned exit code $rc"; throw "DockerCpJsFailed" }

  # 4) mongosh 실행 (환경변수로 비밀번호 사용)
  $execArgs = "exec upbit-mongodb mongosh --username admin --password `"$mongoPass`" --authenticationDatabase admin /tmp/sync_snapshot_upsert_robust.js"
  Write-Log "docker $execArgs"
  $rc = Invoke-Log -ExePath "docker" -ExeArgs $execArgs
  if ($rc -ne 0) { Write-Log "ERROR: mongosh script returned exit code $rc"; throw "MongoShellFailed" }

  # 5) 임시파일(로컬 snapshot) 정리(원하면 주석 처리)
  try {
    Remove-Item $snapshotFile -ErrorAction SilentlyContinue
    Write-Log "Removed local snapshot file: $snapshotFile"
  } catch {
    Write-Log "WARN: failed to remove local snapshot file: $($_.Exception.Message)"
  }

} catch {
  Write-Log "EXCEPTION: $($_.Exception.Message)"
  if ($_.InvocationInfo) { Write-Log "AT: $($_.InvocationInfo.PositionMessage)" }
}

Write-Log "----- END -----`n"