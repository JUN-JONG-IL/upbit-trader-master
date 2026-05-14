# ==============================================================================
# Kafka Topic 생성 스크립트 (v9.0)
# 실행 환경: Windows PowerShell (Docker Desktop)
#
# 사용법:
#   cd <프로젝트 루트>
#   docker compose --profile cluster up -d
#   .\tools\scripts\init-kafka-topics.ps1
# ==============================================================================

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host "=== Kafka Topic 초기화 시작 ===" -ForegroundColor Cyan

$broker    = "kafka-broker-1:9092"
$container = "upbit-kafka"   # 기존 단일 Kafka 컨테이너 이름

# 컨테이너가 준비될 때까지 대기
$maxWait = 60
$waited  = 0
do {
    Start-Sleep -Seconds 3
    $waited += 3
    $check = docker exec $container kafka-broker-api-versions `
        --bootstrap-server localhost:9092 2>&1 | Select-String "broker" | Select-Object -First 1
    Write-Host "  Kafka 준비 확인: (${waited}s)"
} while (-not $check -and $waited -lt $maxWait)

if (-not $check) {
    Write-Error "Kafka 가 응답하지 않습니다. 컨테이너를 확인하세요."
    exit 1
}

# Topic 목록 정의 (이름, 파티션 수, 복제 인수)
$topics = @(
    @{ name = "trade_events";    partitions = 30; replication = 3 },
    @{ name = "candle_events";   partitions = 10; replication = 3 },
    @{ name = "gap_events";      partitions = 5;  replication = 3 },
    @{ name = "order_events";    partitions = 10; replication = 3 },
    @{ name = "alert_events";    partitions = 5;  replication = 1 }
)

foreach ($topic in $topics) {
    $name   = $topic.name
    $parts  = $topic.partitions
    $replic = $topic.replication

    Write-Host "`n  생성: $name (partitions=$parts, replication=$replic)" -ForegroundColor Yellow

    docker exec $container kafka-topics `
        --create `
        --if-not-exists `
        --topic $name `
        --bootstrap-server "localhost:9092" `
        --partitions $parts `
        --replication-factor $replic

    if ($LASTEXITCODE -ne 0) {
        Write-Warning "  '$name' Topic 생성 실패 (exit: $LASTEXITCODE) — 이미 존재할 수 있습니다."
    } else {
        Write-Host "  '$name' 생성 완료" -ForegroundColor Green
    }
}

# Topic 목록 확인
Write-Host "`n=== 생성된 Topic 목록 ===" -ForegroundColor Green
docker exec $container kafka-topics `
    --list `
    --bootstrap-server "localhost:9092"

Write-Host "`n=== Kafka Topic 초기화 완료 ===" -ForegroundColor Green
