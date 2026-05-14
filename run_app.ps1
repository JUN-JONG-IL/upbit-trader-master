# run_app.ps1 — 앱 실행용 (현재 세션에만 적용되는 env로 실행)
$env:PGHOST = "127.0.0.1"
$env:PGPORT = "58529"
$env:PGUSER = "postgres"
$env:PGPASSWORD = "postgres"
$env:PGDATABASE = "upbit_trader"

$env:TIMESCALE_LOCAL_MINCONN = "1"
$env:TIMESCALE_LOCAL_MAXCONN = "5"
$env:TIMESCALE_GLOBAL_FAIL_COOLDOWN_SEC = "60"
$env:POOL_MONITOR = "1"

python .\src\app\main.py

# 안전설정: DB 동시성/청크 제어
$env:TIMESCALE_MAX_CONCURRENT_OPS = "10"
$env:STAGER_MAX_CONCURRENT_WRITES = "5"
$env:TIMESCALE_EXECUTE_CHUNK_SIZE = "200"
# end of safety env
