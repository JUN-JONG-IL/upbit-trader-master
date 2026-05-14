#!/bin/bash

echo "========================================"
echo "🚀 Upbit Trader 시작"
echo "========================================"
echo ""

echo "[1/4] Docker 확인 중..."
if ! command -v docker &> /dev/null; then
    echo "❌ Docker가 설치되지 않았습니다."
    echo "👉 https://www.docker.com/products/docker-desktop 에서 설치하세요."
    echo ""
    exit 1
fi
echo "✅ Docker 설치 확인됨"
echo ""

echo "[2/4] 인프라 시작 중 (MongoDB, Redis, Kafka, Zookeeper)..."
docker-compose up -d
if [ $? -ne 0 ]; then
    echo "❌ Docker Compose 실행 실패"
    echo "👉 Docker Desktop이 실행 중인지 확인하세요."
    echo ""
    exit 1
fi
echo "✅ 인프라 시작 완료"
echo ""

echo "[3/4] 인프라 상태 확인 중..."
sleep 5
docker ps --filter "name=upbit-" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
echo ""

echo "[4/4] Python 앱 시작 중..."
cd src
python -m app.main
if [ $? -ne 0 ]; then
    echo "❌ Python 앱 실행 실패"
    echo "👉 requirements.txt 패키지가 설치되었는지 확인하세요."
    echo "👉 pip install -r requirements.txt"
    echo ""
    exit 1
fi
