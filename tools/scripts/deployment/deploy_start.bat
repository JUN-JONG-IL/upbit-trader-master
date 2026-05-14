@echo off
chcp 65001 >nul
echo ========================================
echo 🚀 Upbit Trader 시작
echo ========================================
echo.

echo [1/4] Docker 확인 중...
docker --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Docker Desktop이 설치되지 않았습니다.
    echo 👉 https://www.docker.com/products/docker-desktop 에서 설치하세요.
    echo.
    pause
    exit /b 1
)
echo ✅ Docker 설치 확인됨
echo.

echo [2/4] 인프라 시작 중 (MongoDB, Redis, Kafka, Zookeeper)...
docker-compose up -d
if %errorlevel% neq 0 (
    echo ❌ Docker Compose 실행 실패
    echo 👉 Docker Desktop이 실행 중인지 확인하세요.
    echo.
    pause
    exit /b 1
)
echo ✅ 인프라 시작 완료
echo.

echo [3/4] 인프라 상태 확인 중...
timeout /t 5 /nobreak >nul
docker ps --filter "name=upbit-" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
echo.

echo [4/4] Python 앱 시작 중...
cd src
python -m app.main
if %errorlevel% neq 0 (
    echo ❌ Python 앱 실행 실패
    echo 👉 requirements.txt 패키지가 설치되었는지 확인하세요.
    echo 👉 pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)
