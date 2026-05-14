# ==============================================================================
# Redis Cluster 초기화 스크립트 (v9.0)
# 실행 환경: Windows PowerShell (Docker Desktop)
#
# 사용법:
#   cd <프로젝트 루트>
#   docker compose --profile cluster up -d
#   .\tools\scripts\init-redis-cluster.ps1
# ==============================================================================

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host "=== Redis Cluster 초기화 시작 ===" -ForegroundColor Cyan

# 컨테이너가 준비될 때까지 대기
$maxWait = 30
$waited  = 0
do {
    Start-Sleep -Seconds 2
    $waited += 2
    $ping = docker exec upbit-redis-master-1 redis-cli -p 7000 PING 2>&1
    Write-Host "  redis-master-1 PING: $ping (${waited}s)"
} while ($ping -ne "PONG" -and $waited -lt $maxWait)

if ($ping -ne "PONG") {
    Write-Error "redis-master-1 가 응답하지 않습니다. 컨테이너를 확인하세요."
    exit 1
}

# Cluster 생성
# Master 3대 + Replica 6대 (--cluster-replicas 2: 마스터당 2개 레플리카)
# 총 9노드: 7000(M) 7001(M) 7002(M) + 7003~7008(R × 6)
Write-Host "`n=== Cluster 생성 중 ===" -ForegroundColor Yellow

docker exec -it upbit-redis-master-1 redis-cli `
    --cluster create `
    "172.25.0.11:7000" "172.25.0.12:7001" "172.25.0.13:7002" `
    "172.25.0.14:7003" "172.25.0.15:7004" "172.25.0.16:7005" `
    "172.25.0.17:7006" "172.25.0.18:7007" "172.25.0.19:7008" `
    --cluster-replicas 2 `
    -a "RedisDev!2026" `
    --cluster-yes

if ($LASTEXITCODE -ne 0) {
    Write-Error "Cluster 생성 실패 (exit code: $LASTEXITCODE)"
    exit $LASTEXITCODE
}

# 클러스터 상태 확인
Write-Host "`n=== Cluster 상태 확인 ===" -ForegroundColor Green
docker exec upbit-redis-master-1 redis-cli `
    -p 7000 -a "RedisDev!2026" cluster info

Write-Host "`n=== Redis Cluster 초기화 완료 ===" -ForegroundColor Green
