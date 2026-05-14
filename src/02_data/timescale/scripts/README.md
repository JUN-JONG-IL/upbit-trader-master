# data/scripts

이 폴더에는 Timescale 관련 스크립트(성능 테스트 등)를 배치합니다.

test_bulk_insert.py
- 설명: Timescale에 대량 행을 업서트해서 성능/동작을 검증합니다.
- 사용법:
  1. 환경변수 설정(POSTGRES_HOST, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD)
  2. python -m src.data.scripts.test_bulk_insert --rows 5000
- 주의: 실제 DB에 데이터를 삽입하므로 테스트용 심볼을 사용하세요.