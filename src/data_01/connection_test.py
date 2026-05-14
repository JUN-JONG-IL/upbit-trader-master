"""
?곗씠?곕쿋?댁뒪 ?곌껐 寃利??ㅽ겕由쏀듃
DB?ㅺ퀎.md v8.0 ?뱀뀡 21 "Docker ?섍꼍 ?ㅼ젙" 湲곗?

?ъ슜踰?
    python src/data_01/connection_test.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# src/ ?붾젆?좊━瑜?Python 寃쎈줈??異붽?
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def test_timescaledb() -> bool:
    """TimescaleDB ?곌껐 ?뚯뒪??""
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
        print(f"??TimescaleDB ?곌껐 ?깃났: {version[0]}")
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        print(f"??TimescaleDB ?곌껐 ?ㅽ뙣: {e}")
        return False


def test_redis() -> bool:
    """Redis ?곌껐 ?뚯뒪??""
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
        print("??Redis ?곌껐 ?깃났: PING OK")
        return True
    except Exception as e:
        print(f"??Redis ?곌껐 ?ㅽ뙣: {e}")
        return False


def test_mongodb() -> bool:
    """MongoDB ?곌껐 ?뚯뒪??""
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
        print(f"??MongoDB ?곌껐 ?깃났: v{version}")
        return True
    except Exception as e:
        print(f"??MongoDB ?곌껐 ?ㅽ뙣: {e}")
        return False


if __name__ == "__main__":
    print("?뵇 Docker 而⑦뀒?대꼫 ?곌껐 ?뺤씤 ?쒖옉...\n")
    results = {
        "TimescaleDB": test_timescaledb(),
        "Redis": test_redis(),
        "MongoDB": test_mongodb(),
    }

    print("\n?뱤 寃곌낵 ?붿빟:")
    for db, success in results.items():
        status = "???뺤긽" if success else "???ㅽ뙣"
        print(f"  {db}: {status}")

    if all(results.values()):
        print("\n?럦 紐⑤뱺 ?곗씠?곕쿋?댁뒪 ?곌껐 ?깃났!")
    else:
        print("\n?좑툘  ?쇰? ?곗씠?곕쿋?댁뒪 ?곌껐 ?ㅽ뙣 - docker-compose.yml ?뺤씤 ?꾩슂")
        sys.exit(1)

