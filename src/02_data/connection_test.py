"""
데이터베이스 연결 검증 스크립트
DB설계.md v8.0 섹션 21 "Docker 환경 설정" 기준

사용법:
    python src/02_data/connection_test.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# src/ 디렉토리를 Python 경로에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def test_timescaledb() -> bool:
    """TimescaleDB 연결 테스트"""
    try:
        import psycopg2  # type: ignore

        conn = psycopg2.connect(
            host=os.getenv("PGHOST", os.getenv("TIMESCALEDB_HOST", "localhost")),
            port=int(os.getenv("PGPORT", os.getenv("TIMESCALEDB_PORT", 5432))),
            database=os.getenv("PGDATABASE", os.getenv("TIMESCALEDB_DB", "upbit_trader")),
            user=os.getenv("PGUSER", os.getenv("TIMESCALEDB_USER", "postgres")),
            password=os.getenv("PGPASSWORD", os.getenv("TIMESCALEDB_PASSWORD", "")),
        )
        cursor = conn.cursor()
        cursor.execute("SELECT version();")
        version = cursor.fetchone()
        print(f"✅ TimescaleDB 연결 성공: {version[0]}")
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        print(f"❌ TimescaleDB 연결 실패: {e}")
        return False


def test_redis() -> bool:
    """Redis 연결 테스트"""
    try:
        import redis as redis_lib  # type: ignore

        r = redis_lib.Redis(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", 6379)),
            password=os.getenv("REDIS_PASSWORD") or None,
            db=int(os.getenv("REDIS_DB", 0)),
            decode_responses=True,
        )
        r.ping()
        print("✅ Redis 연결 성공: PING OK")
        return True
    except Exception as e:
        print(f"❌ Redis 연결 실패: {e}")
        return False


def test_mongodb() -> bool:
    """MongoDB 연결 테스트"""
    try:
        from pymongo import MongoClient  # type: ignore

        mongo_uri = os.getenv("MONGO_URI", "")
        if mongo_uri:
            client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
        else:
            client = MongoClient(
                host=os.getenv("MONGO_HOST", "localhost"),
                port=int(os.getenv("MONGO_PORT", 27017)),
                serverSelectionTimeoutMS=5000,
            )
        db_name = os.getenv("MONGO_DB", os.getenv("MONGO_INITDB_DATABASE_CONTAINER", "upbit_trader"))
        client[db_name].command("ping")
        version = client.server_info().get("version", "unknown")
        print(f"✅ MongoDB 연결 성공: v{version}")
        return True
    except Exception as e:
        print(f"❌ MongoDB 연결 실패: {e}")
        return False


if __name__ == "__main__":
    print("🔍 Docker 컨테이너 연결 확인 시작...\n")
    results = {
        "TimescaleDB": test_timescaledb(),
        "Redis": test_redis(),
        "MongoDB": test_mongodb(),
    }

    print("\n📊 결과 요약:")
    for db, success in results.items():
        status = "✅ 정상" if success else "❌ 실패"
        print(f"  {db}: {status}")

    if all(results.values()):
        print("\n🎉 모든 데이터베이스 연결 성공!")
    else:
        print("\n⚠️  일부 데이터베이스 연결 실패 - docker-compose.yml 확인 필요")
        sys.exit(1)
