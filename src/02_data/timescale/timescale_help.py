# src/data/timescale/timescale_help.py
# Detailed help texts for Timescale UI buttons and overall overview.
# Single source of truth for user-facing help content (Korean).

HELP_OVERVIEW = """
TimescaleDB 관리 도구 도움말 (요약)

이 창은 TimescaleDB에 저장된 캔들(candles) 데이터를 조회·관리하기 위한 도구입니다.
상단의 입력 필드로 DB 접속 정보를 입력한 뒤, 기능 버튼들을 사용하여 데이터베이스와 상호작용할 수 있습니다.

주요 기능
- 연결 테스트: DB 연결 및 기본 질의 확인
- 메타 갱신: public 스키마의 테이블 목록 조회
- CAGG 생성/리프레시: Continuous Aggregate 생성 및 리프레시
- 자동갱신: 선택된 심볼/타임프레임에 대해 주기적 증분 갱신
- 로드/CSV/DB 저장: 화면에 표시된 데이터를 불러오고, CSV로 저장하거나 DB에 영구 저장

도움말 접근 방법
- 창 우측 상단의 '?' 버튼을 누르면 이 전체 도움말이 표시됩니다.
- 각 버튼 위에 마우스를 올리면 간단한 툴팁이 나오며, Qt의 'What's This?' 모드에서는 상세 설명을 확인할 수 있습니다.
"""

# Per-button detailed help. Keys are UI objectNames (btn_test_conn, btn_refresh_meta, ...)
# Each value is a dict with:
#  - title: short title
#  - summary: one-line summary
#  - detail: very detailed explanation (shown in full help dialog)
BUTTON_HELP = {
    "btn_test_conn": {
        "title": "연결 테스트",
        "summary": "입력한 접속 정보로 간단한 쿼리(SELECT now())를 실행하여 DB 연결을 확인합니다.",
        "detail": """연결 테스트 버튼(실행 시)
무엇이 뜨나:
- 상태 라벨(lbl_status)이 '연결 테스트 중...'으로 바뀝니다.
- 성공하면 상태 라벨에 연결 시각을 표시하고 로그 창(pe_log)에 '연결 OK' 메시지를 남깁니다.
- 실패하면 상태 라벨이 '상태: 오류'로 바뀌고 에러 툴팁을 설정합니다.

왜 필요한가:
- DB 접속 정보(호스트, DB 이름, 사용자, 패스워드)가 정확한지 즉시 확인하기 위해 필요합니다.
- 네트워크 또는 권한 문제를 사전 점검하기 위한 용도입니다.

내부 동작:
1) ConnectorWorker.run_query("SELECT now() as now;") 호출.
2) TimescaleConnector가 psycopg2로 DB 연결을 시도하고 쿼리 실행.
3) 결과를 UI 스레드로 전달하여 상태 업데이트 및 심볼 목록 갱신(populate)을 트리거합니다.

권장/주의사항:
- 방화벽, pg_hba 설정 등으로 접속이 거부될 수 있습니다.
- 비밀번호 등 민감정보는 운영환경에서 시크릿 매니저 사용을 권장합니다.
"""
    },
    "btn_refresh_meta": {
        "title": "메타 갱신",
        "summary": "public 스키마의 테이블 목록을 조회하여 현재 DB 상태를 확인합니다.",
        "detail": """메타 갱신 버튼(실행 시)
무엇이 뜨나:
- 조회된 테이블 목록을 표시하는 팝업창이 나타납니다.
- pe_log에 '메타 조회: N' 로그가 남습니다.

왜 필요한가:
- candles, staging_candles, latest_snapshot, cagg_* 등의 테이블/뷰 존재 여부를 확인하기 위함입니다.
- 마이그레이션이나 스키마 변경 후 상태 검증용입니다.

내부 동작:
1) ConnectorWorker.run_query("SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name;") 호출.
2) 결과를 받아 팝업으로 표시합니다.

권장/주의사항:
- 권한이 제한된 DB 계정은 일부 테이블을 보지 못할 수 있습니다.
- 대규모 DB에서 시간이 걸릴 수 있으니 기다려 주세요.
"""
    },
    "btn_create_cagg": {
        "title": "CAGG 생성",
        "summary": "Continuous Aggregate(집계 뷰)를 생성합니다 (WITH NO DATA 권장).",
        "detail": """CAGG 생성(실행 시)
무엇이 뜨나:
- 타임프레임 입력창(예: '5 minutes' 또는 '1 hour')이 표시됩니다.
- 확인하면 백그라운드로 CAGG 생성 요청이 실행되며, pe_log에 로그가 남습니다.

왜 필요한가:
- 상위 타임프레임(예: 5분, 15분, 1시간) 집계를 통해 조회 성능을 개선합니다.
- 원시 데이터를 기반으로 CAGG를 생성하면 차트/지표 성능이 좋아집니다.

내부 동작:
1) view_name 생성(e.g. cagg_candles_5minutes).
2) Connector.run_action("create_cagg", view_name, bucket_interval, where=None) 호출.
3) TimescaleConnector.create_continuous_aggregate()에서 CREATE MATERIALIZED VIEW ... WITH NO DATA 실행.

권장/주의사항:
- WITH NO DATA로 생성한 뒤 REFRESH를 실행해야 데이터가 채워집니다.
- 대��� 범위 REFRESH는 부하가 크므로 배치 시간과 CONCURRENTLY 사용을 권장합니다.
- 생성 권한(슈퍼유저 또는 적절한 권한)이 필요할 수 있습니다.

예시 SQL:
  CREATE MATERIALIZED VIEW IF NOT EXISTS cagg_candles_5m
  WITH (timescaledb.continuous) AS
  SELECT time_bucket('5 minutes', time) AS bucket, symbol,
         first(open, time) AS open, max(high) AS high, min(low) AS low,
         last(close, time) AS close, sum(volume) AS volume
  FROM public.candles
  WHERE timeframe = '1m'
  GROUP BY bucket, symbol
  WITH NO DATA;
"""
    },
    "btn_refresh_cagg": {
        "title": "CAGG 리프레시",
        "summary": "지정한 CAGG(materialized view)를 리프레시합니다 (CONCURRENTLY 권장).",
        "detail": """CAGG 리프레시(실행 시)
무엇이 뜨나:
- 리프레시할 뷰 이름 입력창이 표시됩니다.
- 확인하면 백그라운드에서 REFRESH MATERIALIZED VIEW가 실행되고 완료 로그가 남습니다.

왜 필요한가:
- CAGG를 생성한 후 또는 정책 변경 후 최신화하려면 REFRESH가 필요합니다.

내부 동작:
1) Connector.run_action("refresh_cagg", view_name, concurrent=True) 호출.
2) TimescaleConnector.refresh_materialized_view()에서 REFRESH MATERIALIZED VIEW CONCURRENTLY <view> 실행.

권장/주의사항:
- CONCURRENTLY가 항상 가능하지 않습니다(뷰·인덱스 구성에 의존).
- 대형 뷰는 오래 걸리므로 비업무 시간대 실행 권장.
"""
    },
    "btn_auto_refresh": {
        "title": "자동갱신 토글",
        "summary": "선택한 심볼+타임프레임에 대해 주기적(증분) 갱신을 켜거나 끕니다.",
        "detail": """자동갱신 토글(ON/OFF)
무엇이 뜨나:
- 버튼 텍스트로 '자동갱신: ON' 또는 '자동갱신: OFF'를 표시합니다.
- ON이면 주기적으로(DB 증분 조회) 데이터를 갱신합니다.

왜 필요한가:
- 실시간 모니터링 또는 개발 중 최신 데이터를 자동 반영하려고 사용합니다.
- 전체 재조회보다 증분 조회로 DB 부하를 줄입니다.

내부 동작:
1) ON 상태에서 QTimer가 주기적으로 _on_auto_tick을 호출합니다.
2) _on_auto_tick은 last_timestamp[(symbol,tf)]가 있으면 select_since(symbol,tf,last_ts)를 호출하여 신규 데이터만 수신하고,
   없으면 select_recent(symbol,tf,limit)를 호출합니다.
3) 수신한 rows로 마지막 timestamp를 갱신하고 화면을 리로드합니다.

권장/주의사항:
- 기본 간격은 30초이며 필요에 따라 조정하세요.
- 서버/클라이언트의 시간대(tz)를 일치시키는 것이 중요합니다(권장: UTC).
- 많은 심볼/탭에서 동시에 켜면 DB 부하가 커집니다.
"""
    },
    "btn_load": {
        "title": "데이터 로드",
        "summary": "선택된 심볼+현재 탭 타임프레임의 최신 데이터를 DB에서 불러와 테이블에 표시합니다.",
        "detail": """데이터 로드(실행 시)
무엇이 뜨나:
- 심볼이 비어있으면 입력창이 표시됩니다.
- 심볼을 입력하거나 콤보에서 선택하면 최신 N개 행이 로드되어 현재 탭에 표시됩니다.

왜 필요한가:
- 특정 심볼/타임프레임 데이터를 수동으로 확인하거나 문제 재현 시 사용합니다.

내부 동작:
1) SELECT time, open, high, low, close, volume
   FROM public.candles
   WHERE symbol=%s AND timeframe=%s
   ORDER BY time DESC LIMIT %s;
2) ConnectorWorker로 쿼리 실행 후 결과를 QTableView 모델에 반영합니다.

권장/주의사항:
- limit 기본값은 1000이며 UI/설정에서 조정 가능합니다.
- 큰 limit는 메모리/성능에 영향을 줄 수 있습니다.
"""
    },
    "btn_export_csv": {
        "title": "CSV 내보내기",
        "summary": "현재 탭에 표시된 데이터를 CSV 파일로 저장합니다.",
        "detail": """CSV 내보내기
무엇이 뜨나:
- 파일 저장 다이얼로그가 표시됩니다. 파일을 선택하면 모델의 모든 행을 CSV로 기록합니다.

왜 필요한가:
- 데이터를 엑셀, pandas 등 외부 도구로 옮겨 추가 분석 또는 디버깅할 때 사용합니다.

내부 동작:
1) 현재 QTableView.model()을 순회하며 헤더와 각 행을 CSV writer로 저장.
2) 저장 성공/실패를 pe_log에 기록합니다.

권장/주의사항:
- 디스크 공간 및 파일 쓰기 권한을 확인하세요.
"""
    },
    "btn_save_db": {
        "title": "DB 저장",
        "summary": "현재 탭에 표시된 데이터를 검증(validate)한 뒤 TimescaleDB의 candles 테이블에 bulk upsert 합니다.",
        "detail": """DB 저장 (validate -> bulk upsert)
무엇이 뜨나:
- 저장 전 확인 팝업(행 수 확인)이 표시됩니다.
- 저장 진행 중 상태가 pe_log에 출력되며, 완료 후 성공/실패 로그가 표시됩니다.

왜 필요한가:
- UI에서 편집/검토한 데이터를 DB에 영구 저장하기 위해 사용합니다.
- 대량 업로드는 execute_values 또는 COPY 기반으로 효율적으로 처리됩니다.

내부 동작:
1) 화면 모델에서 (exchange, symbol, timeframe, time, open, high, low, close, volume, trade_count, is_closed, ts) 튜플 리스트를 생성합니다.
2) validate_candle_advanced(rows)를 호출하여 무결성(시간, OHLC 논리, volume 등)을 검사합니다.
3) ConnectorWorker.run_action("bulk_insert", rows)를 호출하면 TimescaleConnector.insert_candles_bulk가 execute_values 우선, 없으면 TEMP TABLE + COPY -> INSERT ... ON CONFLICT 방식으로 업서트합니다.
4) 업서트 성공 시 TimescaleConnector.update_latest_snapshot를 통해 latest_snapshot를 갱신합니다.

권장/주의사항:
- 앱 부트스트랩(로그인 전) 단계에서 DB 연결 및 hypertable 보장(ensure) 로직을 수행하세요.
- 네트워크 장애 시 로컬 큐(파일 또는 Redis)에 임시 보관 후 재전송하는 로직을 권장합니다.
- 권한: INSERT/UPDATE 권한이 필요합니다.
"""
    }
}  # end BUTTON_HELP