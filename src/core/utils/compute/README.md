# CHANGELOG
# 2026-01-31 | Copilot | 생성/재작성: src/compute/README.md. 영향: src/compute 폴더의 모든 주요 파일(캔들 집계, 지표 엔진, 스캐너 실행기, ComputeProcess 등) 문서화. 테스트: 로컬 ComputeProcess 실행 예제, lint/test 권장 명령 포함.

Version: v1.0
Last Modified: 2026-01-31 | Copilot

# README: src/compute
Purpose: GUI와 분리된 계산 전용 프로세스(Compute Process)를 포함하는 모듈입니다. 캔들 집계(Candle Aggregator), 지표의 증분 계산(Indicator Engine, O(1)), 스캐너 실행기(조건식 평가 및 델타 전송), ComputeProcess 메인(멀티프로세스·Redis Pub/Sub 연동) 등을 통해 실시간 트레이딩 데이터의 집계·지표·스캐닝·퍼블리시를 담당합니다. 이 문서는 src/compute 폴더에 직접 포함된 파일만을 대상으로 하며(하위 폴더/다른 경로 파일 제외), 각 파일별로 목적, 사용법(복사·붙여넣기 가능한 예제), 주의사항을 자세히 서술합니다.

Note (검색 한계): 코드 검색 결과는 도구 제한으로 인해 완전하지 않을 수 있습니다. 폴더의 전체 파일 목록을 직접 확인하려면 GitHub에서 src/compute 디렉터리를 확인하세요:
https://github.com/JUN-JONG-IL/upbit-trader-master/tree/main/src/compute

FILES (각 항목: 파일명 / Purpose / Usage / Cautions — 하나의 문단으로 상세 기술)

- README.md
  - Purpose: 이 파일은 src/compute 폴더의 목적, 각 모듈 설명, 실행·개발 지침, 테스트 체크리스트, 주의사항을 통합 제공합니다.
  - Usage: Compute 프로세스(로컬/개발 환경) 또는 모듈 단위 테스트를 수행하기 전에 본 README를 반드시 확인하십시오.
  - Cautions: 문서 수정 시 변경 사유와 영향 범위(어떤 UI/서비스가 의존하는지)를 명확히 기록하세요.

- __init__.py
  - Purpose: compute 패키지의 공개 진입점으로 ComputeProcess를 외부에 노출합니다.
  - Usage (예):
    - from src.compute import ComputeProcess
  - Cautions: 패키지 임포트 시 무거운 초기화(예: Redis 접속, Mongo 연결)를 하지 마십시오. 임포트 시 사이드 이펙트가 발생하면 테스트/모듈 로딩에 문제를 초래합니다.

- compute_main.py
  - Purpose: Compute 프로세스의 엔트리이자 메인 구현체(ComputeProcess). multiprocessing.Process 기반으로 Redis Pub/Sub을 구독하여 trade 이벤트를 캔들로 집계하고(문서화된 파이프라인), IndicatorEngine으로 지표를 증분 계산한 뒤 결과를 Redis/MongoDB에 저장하고 UI용 WebSocket 패치(또는 Redis 토픽)를 발행합니다.
  - Usage (개발 예):
    - from src.compute.compute_main import ComputeProcess
    - proc = ComputeProcess(redis_host='localhost', redis_port=6379, mongodb_enabled=True)
    - proc.start()
    - # 실행 중지
    - proc.terminate() or proc.stop()  # 구현된 안전 종료 API 사용
  - Cautions: 이 모듈은 외부 의존성(redis, motor/mongodb 등)에 따라 동작이 달라집니다. REDIS_AVAILABLE, MONGODB_AVAILABLE 등의 플래그를 확인하세요. 프로세스 시작/종료 라이프사이클을 엄격히 관리하지 않으면 데몬 프로세스가 잔존하거나 자원 누수가 발생할 수 있습니다. 운영 환경에서는 환경변수/시크릿 관리를 통해 민감정보를 안전히 주입하세요.

- candle_aggregator.py
  - Purpose: Trade 이벤트(틱/거래)를 실시간으로 캔들(틱/초/분/시간/일/주/월 등)로 집계하는 핵심 모듈. O(1) 증분 업데이트 방식으로 각 트레이드에 대해 상·저·종·거래량만 갱신하며, 캔들 마감 시점에 close 이벤트를 발생시킵니다.
  - Usage (예):
    - from src.compute.candle_aggregator import CandleAggregator
    - agg = CandleAggregator(exchange='upbit')
    - agg.on_trade(symbol='KRW-BTC', price=50000000, volume=0.001, timestamp=...)
    - closed = agg.check_and_emit_closed_candles()
  - Cautions: 시간대(KST) 기준 계산이 포함되어 있으므로 타임스탬프 표준(UTC vs KST)을 일관되게 사용해야 합니다. O(1) 성능을 보장하려면 내부 상태 관리(고정 크 버퍼 등)를 깨뜨리지 말고, 대량 종목 처리 시 메모리 사용량이 증가하므로 모니터링/샤딩 전략을 준비하세요. 캔들 스키마(필드명)가 외부 저장(Mongo/Redis) 및 UI가 기대하는 스키마와 항상 일치하는지 검증하세요.

- indicator_engine.py
  - Purpose: 기술 지표(EMA, SMA, RSI, MACD, Bollinger, ATR, Stochastic 등)를 O(1) 증분 방식으로 계산하는 엔진. 각 심볼+타임프레임별로 상태를 유지하며 Welford 온라인 알고리즘 등으로 분산/표준편차를 효율적으로 계산합니다.
  - Usage (예):
    - from src.compute.indicator_engine import IndicatorEngine
    - ie = IndicatorEngine()
    - ie.update_with_closed_candle(symbol, timeframe, candle)  # 구현된 통합 API 사용
    - value = ie.get('RSI', symbol, timeframe)
  - Cautions: 지표 계산은 상태 기반(stateful)이므로 프로세스 재시작/복구 시 상태 복원이 필요합니다(체크포인트/스냅샷 또는 과거 캔들 Prefetch). 입력 데이터의 순서가 바뀌면 잘못된 결과가 발생할 수 있으므로 시간 순서를 보장하세요. 고유한 파라미터(예: RSI period)를 변경하면 결과가 크게 달라지므로 버전화 및 호환성 전략을 세우십시오.

- scanner_executor.py
  - Purpose: 스캐너 실행기 — 조건식(사용자 정의 표현식)을 AST 기반으로 안전하게 평가하여 종목 필터링을 수행하고, 변경된 종목(add/remove)만 델타로 전송합니다. 200ms 마이크로배치 실행 모델로 설계되어 있으며 전체 종목 재평가를 피합니다.
  - Usage (예):
    - from src.compute.scanner_executor import ScanCondition, ExpressionEvaluator
    - eval = ExpressionEvaluator()
    - cond = ScanCondition(id='s1', name='Low RSI', expression='RSI < 30 AND Volume > 1000000')
    - result = eval.evaluate(cond.expression, context={'RSI':25, 'Volume':1500000})
  - Cautions: ExpressionEvaluator는 AST 기반으로 일부 안전한 연산만 허용합니다(허용된 함수/연산자 목록 참조). 외부 입력을 그대로 평가하면 보안 이슈가 발생할 수 있으니 반드시 검증된 표현식만 허용하세요. 또한 스캐너는 delta 전송 빈도 및 배치 크기에 따라 성능에 영향을 받으므로 백프레셔 및 스로틀 정책을 마련하세요.

USAGE — 로컬 개발 및 실행 (복사·붙여넣기 가능한 명령)

1) 개발 환경 준비
- python -m venv .venv
- source .venv/bin/activate    # Windows: .\.venv\Scripts\Activate.ps1
- pip install -r requirements.txt

2) ComputeProcess 실행(개발용 예)
- python -c "from src.compute.compute_main import ComputeProcess; p=ComputeProcess(redis_host='localhost', redis_port=6379); p.start(); print('ComputeProcess started')"
  (실제 운영에서는 systemd/docker/kubernetes 등으로 관리)

3) 모듈 단위 테스트(예)
- python -c "from src.compute.candle_aggregator import CandleAggregator; a=CandleAggregator(); print('ok')"

4) 지표 엔진/스캐너 테스트(예)
- python -c "from src.compute.indicator_engine import IndicatorEngine; ie=IndicatorEngine(); print(ie.metrics)"

DEVELOPMENT · LINT · TEST
- pip install -r requirements-dev.txt
- black --check .
- flake8 src/compute
- mypy src/compute
- bandit -r src/compute
- pytest tests/compute -q  # 존재 시

RUNTIME CONFIGURATION
- Redis: ComputeProcess는 Redis Pub/Sub을 통해 trade 이벤트를 수신/발행합니다. redis 패키지가 설치되어 있지 않으면 REDIS_AVAILABLE 플래그가 False가 되므로 동작 모드를 확인하세요.
- MongoDB: motor(motor_asyncio)가 설치되어 있으면 Mongo 저장 기능을 사용합니다. 설치 여부에 따라 MONGODB_AVAILABLE 플래그 동작이 달라집니다.
- 설정: ComputeProcess/RealtimeManager 등은 외부 config(예: src/config.yaml 또는 환경변수)를 통해 Redis/Mongo 엔드포인트, TTL, 퍼블리시 토픽명을 받도록 설계되어야 합니다.
- 모드 분리: PAPER/LIVE 모드 구분은 데이터 소스 및 저장/퍼블리시 정책에 영향을 줍니다. 실거래 관련 설정은 분리·암호화하십시오.

WARNINGS / CRITICAL NOTES
- 데이터 포맷 불변성(P1): 캔들/지표/델타 메시지의 스키마(필드명, 데이터 유형)는 UI 및 다른 프로세스(Chart, Scanner, ComputeConsumer 등)가 의존합니다. 스키마 변경은 엄격한 검토·문서화·승인 절차가 필요합니다.
- 상태 복원: IndicatorEngine과 CandleAggregator는 상태 기반이므로 프로세스 재시작 시 상태를 복원하는 방법(과거 캔들 prefetch 또는 체크포인트)이 마련되어 있지 않으면 지표가 초기화되어 잘못된 값을 낼 수 있습니다.
- 성능: 캔들 집계·지표 계산은 고빈도 트레이드(초당 수천/만 건)에 대해 설계되어야 합니다. CPU/메모리/네트워크 한계에 따른 샤딩·멀티프로세싱 설계를 고려하세요.
- 보안: scanner_executor에서 사용자 표현식을 허용할 때는 AST 기반 허용 연산자/함수만 사용하도록 제한하고, 임의 코드 실행을 허용하지 마세요.

TROUBLESHOOTING (일반 문제 및 해결 팁)
- Redis 구독 실패: Redis 접속 정보(host/port/auth)와 네트워크 연결을 확인. REDIS_AVAILABLE False인 경우 관련 기능이 비활성화됩니다.
- CandleAggregator가 잘못된 캔들 생성: 입력 트레이드 타임스탬프의 정렬/타임존 문제를 점검(KST/UTC 변환).
- Indicator 값이 초기화됨: 프로세스 재시작 또는 상태 복원 실패 여부 확인 — 과거 캔들 prefetch 기능을 통해 초기 상태 재구성 필요.
- ComputeProcess가 종료되지 않음: 멀티프로세스/스레드 종료 루틴(stop/terminate/join)을 올바르게 호출했는지 확인.

BACKUP · ROLLBACK
- 변경 전 커밋: 주요 알고리즘(aggregator/indicator/scanner) 변경 전 반드시 커밋 및 브랜치 생성.
- 상태 스냅샷: IndicatorEngine/CandleAggregator 상태를 주기적으로 스냅샷(파일 또는 DB)하여 재시작 시 복원 가능하도록 설계하세요.
- 롤백: 변경 사항이 문제를 야기하면 이전 커밋으로 체크아웃하고 상태 복원 및 smoke test 수행(예: 샘플 트레이드 → 캔들 생성/지표 계산 확인).

TESTING CHECKLIST (변경 시 수행)
- 단위 테스트: CandleAggregator의 O(1) 업데이트 동작(예: 단일 트레이드로 high/low/close/volume 갱신) 확인.
- 지표 정확성: IndicatorEngine 메소드별(EMA/RSI/MACD 등) 계산 결과를 표준 구현과 비교합니다.
- 스캐너 안전성: ExpressionEvaluator가 악의적 입력을 실행하지 않고 의도한 연산만 수행하는지 검사.
- 통합 플로우: Redis 로컬 환경에서 ComputeProcess를 실행 → 더미 트레이드 발행 → 캔들 close 이벤트 및 지표 계산/Redis·Mongo 저장 확인.
- lint/mypy/flake8 통과.

REFERENCES
- work_order/README_작성_가이드.md, work_order/규칙.md (문서·변경 정책)
- src/config.yaml (전역 설정 참조)
- scripts/doc_check.py, verify_phase2.py (레포 검증 도구)

AUTHOR / CONTACT
- 작성자: Copilot (자동 생성 규칙에 따름)
- Last Modified: 2026-01-31

--------------------------------------------------------------------------------
Next README proposal: src/chart/README.md (이미 작성) 또는 src/search/README.md 제안합니다. 원하시면 바로 진행하겠습니다.
