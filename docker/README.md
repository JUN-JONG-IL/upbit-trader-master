# docker — Docker 초기화 파일

## 목적

Docker 컨테이너 초기화에 사용되는 SQL 및 스크립트 파일을 제공합니다.

## 구조

```
docker/
└── init/
    ├── init_clickhouse.sql     # ClickHouse 초기화 (구 init/)
    ├── init_postgres.sql       # PostgreSQL 초기화 (구 init/)
    ├── init_timescaledb.sql    # TimescaleDB 초기화 (구 init/)
    ├── mongo_init.js           # MongoDB 초기화 스크립트 (구 init/)
    └── sql/
        ├── 00_schema.sql           # 기본 스키마 (구 sql/)
        ├── 01_hypertables.sql      # TimescaleDB 하이퍼테이블 (구 sql/)
        ├── 02_cagg.sql             # Continuous Aggregate (구 sql/)
        ├── 03_policies.sql         # 보존 정책 (구 sql/)
        └── 04_hash_partitioning.sql # 해시 파티셔닝 (구 sql/)
```

## 사용법

Docker Compose에서 초기화 파일을 마운트하여 사용합니다.
자세한 내용은 프로젝트 루트의 `docker-compose.yml` 파일을 참조하세요.
