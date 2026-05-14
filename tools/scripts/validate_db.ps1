#!/usr/bin/env pwsh
# validate_db.ps1 — DB 연결 검증 스크립트
# 실행: .\tools\scripts\validate_db.ps1

param(
    [string]$EnvFile = ".env"
)

# .env 파일 로드 (KEY=VALUE 형식 파싱)
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith('#')) {
            $idx = $line.IndexOf('=')
            if ($idx -gt 0) {
                $key   = $line.Substring(0, $idx).Trim()
                $value = $line.Substring($idx + 1).Trim()
                [System.Environment]::SetEnvironmentVariable($key, $value, 'Process')
            }
        }
    }
    Write-Host ".env 파일 로드 완료: $EnvFile" -ForegroundColor DarkGray
}

$overallOk = $true

# ─────────────────────────────────── TimescaleDB ──────────────────────────────
Write-Host "`n=== TimescaleDB 연결 테스트 ===" -ForegroundColor Cyan
$pgResult = python - << 'EOF'
import sys, os
try:
    import asyncpg, asyncio
    dsn = os.getenv("DATABASE_URL", "")
    if not dsn:
        host = os.getenv("PGHOST", "127.0.0.1")
        port = os.getenv("PGPORT", "5432")
        user = os.getenv("PGUSER", "admin")
        pw   = os.getenv("PGPASSWORD", "")
        db   = os.getenv("PGDATABASE", "upbit_trader")
        dsn  = f"postgresql://{user}:{pw}@{host}:{port}/{db}"
    async def _check():
        conn = await asyncpg.connect(dsn)
        try:
            return await conn.fetchval('SELECT 1')
        finally:
            await conn.close()
    val = asyncio.run(_check())
    print(f"OK (result={val})")
    sys.exit(0)
except ImportError as e:
    print(f"SKIP (asyncpg 미설치: {e})", file=sys.stderr)
    sys.exit(2)
except Exception as e:
    print(f"FAIL: {e}", file=sys.stderr)
    sys.exit(1)
EOF
$exitCode = $LASTEXITCODE
if ($exitCode -eq 0) {
    Write-Host "✅ TimescaleDB OK — $pgResult" -ForegroundColor Green
} elseif ($exitCode -eq 2) {
    Write-Host "⚠️  TimescaleDB SKIP — $pgResult" -ForegroundColor Yellow
} else {
    Write-Host "❌ TimescaleDB FAIL — $pgResult" -ForegroundColor Red
    $overallOk = $false
}

# ─────────────────────────────────────── Redis ────────────────────────────────
Write-Host "`n=== Redis 연결 테스트 ===" -ForegroundColor Cyan
$redisResult = python - << 'EOF'
import sys, os
try:
    import redis as _redis
    host = os.getenv("REDIS_HOST", "127.0.0.1")
    port = int(os.getenv("REDIS_PORT", "6379"))
    pw   = os.getenv("REDIS_PASSWORD") or None
    db   = int(os.getenv("REDIS_DB", "0"))
    r = _redis.Redis(host=host, port=port, password=pw, db=db, socket_timeout=5)
    r.ping()
    info = r.info("server")
    ver  = info.get("redis_version", "?")
    print(f"OK (version={ver})")
    sys.exit(0)
except ImportError as e:
    print(f"SKIP (redis 미설치: {e})", file=sys.stderr)
    sys.exit(2)
except Exception as e:
    print(f"FAIL: {e}", file=sys.stderr)
    sys.exit(1)
EOF
$exitCode = $LASTEXITCODE
if ($exitCode -eq 0) {
    Write-Host "✅ Redis OK — $redisResult" -ForegroundColor Green
} elseif ($exitCode -eq 2) {
    Write-Host "⚠️  Redis SKIP — $redisResult" -ForegroundColor Yellow
} else {
    Write-Host "❌ Redis FAIL — $redisResult" -ForegroundColor Red
    $overallOk = $false
}

# ─────────────────────────────────────── MongoDB ──────────────────────────────
Write-Host "`n=== MongoDB 연결 테스트 ===" -ForegroundColor Cyan
$mongoResult = python - << 'EOF'
import sys, os
from urllib.parse import quote_plus
try:
    from pymongo import MongoClient
    # 개별 자격증명 우선 (이중 인코딩 방지)
    user = (
        os.getenv("MONGO_INITDB_ROOT_USERNAME")
        or os.getenv("MONGO_INITDB_ROOT_USERNAME_CONTAINER")
        or os.getenv("MONGO_USER")
    )
    pw = (
        os.getenv("MONGO_INITDB_ROOT_PASSWORD")
        or os.getenv("MONGO_INITDB_ROOT_PASSWORD_CONTAINER")
        or os.getenv("MONGO_PASSWORD")
    )
    host = os.getenv("MONGO_HOST", "localhost")
    port = int(os.getenv("MONGO_PORT", "27017"))
    db   = os.getenv("MONGO_DB", "upbit_trader")

    if user and pw:
        uri = f"mongodb://{quote_plus(user)}:{quote_plus(pw)}@{host}:{port}/{db}?authSource=admin"
    else:
        uri = os.getenv("MONGO_URI") or f"mongodb://{host}:{port}/{db}"

    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    info = client.server_info()
    ver  = info.get("version", "?")
    print(f"OK (version={ver})")
    sys.exit(0)
except ImportError as e:
    print(f"SKIP (pymongo 미설치: {e})", file=sys.stderr)
    sys.exit(2)
except Exception as e:
    print(f"FAIL: {e}", file=sys.stderr)
    sys.exit(1)
EOF
$exitCode = $LASTEXITCODE
if ($exitCode -eq 0) {
    Write-Host "✅ MongoDB OK — $mongoResult" -ForegroundColor Green
} elseif ($exitCode -eq 2) {
    Write-Host "⚠️  MongoDB SKIP — $mongoResult" -ForegroundColor Yellow
} else {
    Write-Host "❌ MongoDB FAIL — $mongoResult" -ForegroundColor Red
    $overallOk = $false
}

# ─────────────────────────────────────── 요약 ─────────────────────────────────
Write-Host ""
if ($overallOk) {
    Write-Host "✅ 모든 DB 연결 성공" -ForegroundColor Green
} else {
    Write-Host "❌ 일부 DB 연결 실패 — 위 오류 메시지를 확인하세요." -ForegroundColor Red
    exit 1
}
