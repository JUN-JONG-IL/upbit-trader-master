# CHANGELOG
# 2026-01-31 | Copilot | 생성/재작성: src/component/README.md. 영향: src/component 폴더 문서화(파일별 목적/사용법/주의사항 추가). 테스트: 로컬 모듈 임포트/기능 검증 권장.

Version: v1.0
Last Modified: 2026-01-31 | Copilot

# README: src/component
Purpose: 실시간 트레이딩 플랫폼의 코어 런타임 계층(자산/티커 관리, WebSocket 수신·동기화, 계정 동기화, Redis/Kafka 퍼블리시 연동 등)을 모아 두는 패키지입니다. 이 폴더는 플랫폼 전반에서 재사용되는 실시간 데이터 매니저 및 관련 객체들을 포함하며, UI 및 상위 서비스 계층(예: ChartWidget, OrderBookWidget, Account UI)과 데이터를 안전하게 교환하는 역할을 합니다.

Important: 이 문서는 src/component 폴더의 "직접 포함된 파일"만 문서화합니다(하위 폴더/다른 경로의 파일은 포함하지 않음). README_작성_가이드.md 규칙을 준수하여 각 파일에 대해 Purpose / Usage(복사·붙여넣기 가능한 예제) / Cautions(주의사항)을 상세히 작성했습니다.

Note on repository listing: 코드 검색/디렉터리 조회 결과가 제한될 수 있으며, 이 문서에 포함된 파일 목록은 현재 검색 결과를 기반으로 작성되었습니다. 더 많은 파일을 직접 확인하려면 GitHub에서 src/component 디렉터리를 확인하세요:
https://github.com/JUN-JONG-IL/upbit-trader-master/tree/main/src/component

FILES (각 항목: 파일명 / Purpose / Usage / Cautions)

- README.md
  - Purpose: 이 파일은 src/component 폴더의 전체 개요, 각 파일의 역할, 실행·개발 지침 및 주의사항을 통합 제공합니다.
  - Usage: 개발자는 이 파일을 먼저 읽어 component의 책임 범위(실시간 데이터, 계정 동기화 등)를 이해한 뒤 변경 작업을 진행해야 합니다.
  - Cautions: 문서 변경 시 변경 이유, 영향 범위(관련 UI/서비스), 테스트(유닛·통합) 계획을 명확히 기록하세요.

- __init__.py
  - Purpose: 패키지의 공개 진입점으로 주요 심볼(RealtimeManager, Account, Coin 등)을 재노출하여 외부에서 간편하게 import할 수 있게 합니다.
  - Usage (예):
    - from src.component import RealtimeManager, Account, Coin
  - Cautions: __init__.py에 무거운 초기화 로직을 넣지 마세요(예: WebSocket 연결, Redis 접속 등). 패키지 임포트 시 사이드이펙트가 발생하면 테스트/임포트 루틴이 실패할 수 있습니다.

- component.py
  - Purpose: 이 모듈은 src/component의 핵심 구현 파일로, Coin 객체(종목 상태/티커/집계), RealtimeManager(티커/오더북/계정 동기화 및 WebSocket 관리), WebsocketManager(Upbit/외부 WebSocket 수신자), Account(계정/포지션 동기화) 등 플랫폼 런타임 로직을 포함합니다. 또한 Phase 2.1에서 Redis Pub/Sub 발행 기능을 통합하는 코드(옵션)를 포함합니다.
  - Usage (복사·붙여넣기 예제):
    - from src.component.component import RealtimeManager, Account, Coin
    - rm = RealtimeManager(config)
    - rm.start()                # 백그라운드 WebSocket 스레드/루프 시작
    - coin = Coin({'market':'KRW-BTC','korean_name':'비트코인','english_name':'Bitcoin'})
    - acct = Account(api_client); acct.sync()
    - rm.stop()                 # 안전 종료
  - Cautions:
    - 네트워크/스레드: RealtimeManager는 내부에서 스레드/비동기 루프(websockets/aiopyupbit 등)를 생성합니다. start/stop 라이프사이클을 엄격히 관리하지 않으면 데몬 스레드가 잔류하거나 프로세스가 종료되지 않을 수 있습니다.
    - 민감정보: API 키/시크릿은 Account나 외부 클라이언트로 전달할 때 절대 레포지토리에 하드코딩하지 마세요. 환경변수/시크릿 매니저 사용.
    - 데이터 포맷 호환성: Coin 객체의 공개 getter API와 orderbook unit 포맷은 기존 UI(예: OrderbookWidget)가 기대하는 스키마를 변경하지 않도록 유지해야 합니다. 필요 시 변환 어댑터를 명시적으로 구현하고 문서화하세요.
    - 외부 의존성: Redis가 optional로 import되어 동작 조건이 달라질 수 있습니다(REDIS_AVAILABLE 플래그). Redis 미설치 환경에서는 대체 경로가 동작하는지 확인하세요.
    - 안정성: WebSocket 재연결 로직, 에러 핸들링, 메시지 스로틀링(과도한 이벤트로 인한 큐 폭주 방지)을 반드시 포함해야 합니다.

USAGE — 개발 / 실행 (복사·붙여넣기 가능한 명령)
1) 개발 환경 준비
- python -m venv .venv
- source .venv/bin/activate   # Windows: .\.venv\Scripts\Activate.ps1
- pip install -r requirements.txt

2) 단순 모듈 테스트 (REPL)
- python -c "from src.component import RealtimeManager; print('import ok')"

3) 간단 런타임 예제 (개발용)
- 아래는 매우 단순화된 예제이며 실제 운영에서는 config/로그인/권한 처리가 필요합니다.
  - from src.component.component import RealtimeManager
  - rm = RealtimeManager({'some':'config'})  # 실제 생성자 인자 확인
  - rm.start()
  - # 작업 후
  - rm.stop()

4) Redis 사용(옵션)
- pip install redis
- 환경에서 Redis 사용 시 REDIS_AVAILABLE이 True가 되는지 확인하세요. Redis 미설치 시 관련 기능은 비활성화 됩니다.

RUNTIME CONFIGURATION
- 설정: RealtimeManager/Account 생성자에서 받는 설정(config) 형식을 확인하세요(예: WebSocket URL, Redis/Kafka 엔드포인트, 재연결 정책). 루트의 src/config.yaml이나 상위 설정을 참조하도록 설계되어 있을 가능성이 높습니다.
- 모드 분리: 모드(PAPER/LIVE 등)와 관련된 플래그는 Account/RealtimeManager가 외부 환경에 따라 실거래 엔드포인트나 시뮬레이션 모드로 전환하도록 구성하세요.
- 민감정보: API 키/시크릿은 환경변수나 CI/Secrets에 보관하고, 런타임은 이를 안전히 주입하세요.

WARNINGS / CRITICAL NOTES
- 실거래 위험: component 모듈은 계정·주문·잔고 동기화에 관여할 수 있습니다. 실거래 환경에서의 변경(특히 주문 관련 API 호출)은 반드시 이중 확인/로그/승인 절차를 도입하세요.
- 기능 변질 금지: 기존 UI/외부 인터페이스(특정 필드명, 시간 포맷 등)를 임의로 변경하지 마세요. 변경이 필요하면 영향 분석을 문서화하고 사용자 승인 절차를 따르세요.
- 성능/스케일: 티커/오더북의 빈번한 이벤트는 내부 큐와 처리 로직에 부담을 줍니다. 메시지 버퍼링, 배치 발행, Redis/Kafka 퍼블리시 사용을 고려하여 backpressure를 설계하세요.
- 외부 서비스 의존성: Redis/Kafka/WebSocket 라이브러리 미설치 시 graceful fallback이 필요합니다. REDIS_AVAILABLE과 같은 플래그로 분기 처리되어 있는지 확인하세요.

TROUBLESHOOTING (자주 발생 문제 & 해결 팁)
- 데몬 스레드/루프가 종료되지 않음: RealtimeManager.stop() 또는 관련 종료 훅을 호출했는지 확인. 스레드 join/async loop stop 절차가 정상적으로 실행되는지 로그로 확인하세요.
- 메시지 포맷 불일치(오더북/티커): component.py의 변환 코드(예: obu 단위 포맷 변환)가 UI가 기대하는 필드(ap/as/bp/bs)를 제공하는지 검증하세요.
- Redis 관련 오류: REDIS_AVAILABLE 플래그와 import 에러 메시지를 확인. Redis 미설치 환경에서는 관련 퍼블리시 코드가 예외를 발생시키지 않도록 보호되어야 합니다.
- WebSocket 재연결 실패: 네트워크/방화벽, URL/인증값 확인. 재연결 정책이 적절한 지(증감 대기, 최대 재시도 제한 등) 검토하세요.

TESTING CHECKLIST (변경 시 수행할 항목)
- 모듈 임포트 테스트: from src.component import RealtimeManager, Account, Coin 가 정상 동작하는지 확인.
- RealtimeManager 라이프사이클: start → 수신(테스트 더미 데이터) → stop 시 예외 없음.
- Coin 객체 API 호환성: UI(예: OrderbookWidget)가 사용하는 필드(예: ap/as/bp/bs)가 올바로 매핑되는지 단위 검사.
- Redis 퍼블리시: Redis 환경에서 ticker 메시지 발행이 정상인지 확인(필요 시 Redis consumer로 수신 확인).
- 스트레스 테스트: 티커 이벤트 폭주 시 내부 큐/메모리 사용 증가 및 백프레셔 동작 검증.

BACKUP & ROLLBACK
- 주요 변경(특히 데이터 포맷/공개 API 변경) 전에는 반드시 커밋/브랜치 생성 및 docs/previous_stages/에 원본 보관을 권장합니다.
- 포맷 변경 시 영향 범위(어떤 UI/서비스가 영향받는지)와 롤백 절차를 문서화하세요(예: 이전 버전의 Coin getter 복원 절차).

REFERENCES
- src/config.yaml (전역 설정 참조)
- work_order/규칙.md, work_order/README_작성_가이드.md (문서/변경 정책)
- scripts/doc_check.py, verify_phase2.py (레포 검증 툴)

AUTHOR / CONTACT
- 작성자: Copilot (자동 생성 규칙에 따름)
- Last Modified: 2026-01-31

--------------------------------------------------------------------------------
다음으로 작성할 폴더 README.md 제안: src/compute/README.md
(원하시면 바로 작성 시작하겠습니다.)
