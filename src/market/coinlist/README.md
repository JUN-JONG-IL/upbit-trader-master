# CHANGELOG
# 2026-01-31 | Copilot | 생성/재작성: src/coinlist/README.md. 영향: src/coinlist 폴더의 모든 파일(위젯/UI/로직/워커 등) 문서화. 테스트: 로컬 UI 시작 · 워커 시뮬레이션 명령 포함.

Version: v1.0
Last Modified: 2026-01-31 | Copilot

# README: src/coinlist
Purpose: 홈 화면의 "종목 테이블(코인 리스트)" 기능을 제공하는 모듈로, 실시간 티커·체결 집계, 목록 정렬/검색/관심종목 관리, UI 상태(프로그레스/설정/타임 옵션) 및 백그라운드 워커를 포함합니다. 이 폴더는 CoinlistWidget과 연관된 UI(.ui)와 로직/워커/유틸을 포함하며, Chart/Orderbook/Trade 위젯과의 심볼 동기화를 책임집니다.

Important: README_작성_가이드.md 규칙을 100% 준수하여 상단 CHANGELOG/Version/Last Modified를 포함했습니다. 아래 문서는 src/coinlist 폴더에 직접 포함된 파일만 다루며(하위 폴더/다른 경로 파일 제외), 각 파일에 대해 Purpose / Usage(복사·붙여넣기 가능한 예제) / Cautions(주의사항)를 하나의 문단으로 상세히 기록했습니다.

Note on listing completeness: 코드 검색 결과는 도구 제한으로 인해 일부 파일이 누락될 수 있습니다. 전체 파일 목록과 최신 상태는 GitHub에서 직접 확인하세요:
https://github.com/JUN-JONG-IL/upbit-trader-master/tree/main/src/coinlist

FILES (각 항목: 파일명 / Purpose / Usage / Cautions)

- README.md
  - Purpose: src/coinlist 폴더의 전체 개요와 파일별 상세 설명, 실행·개발 지침 및 테스트 체크리스트를 제공합니다.
  - Usage: Coinlist 관련 개발/버그 수정 전에 본 문서를 먼저 읽어 아키텍처와 외부 의존성을 이해하세요.
  - Cautions: README 수정 시 변경 사유와 영향 범위(Chart/Orderbook/Trade 연동 포함)를 기록하세요.

- __init__.py
  - Purpose: coinlist 패키지의 진입점으로, 외부에서 CoinlistWidget을 간단히 import할 수 있도록 노출합니다.
  - Usage (예):
    - from src.coinlist import CoinlistWidget
  - Cautions: __init__.py에 네트워크/스레드 초기화 같은 무거운 코드 삽입 금지 — 임포트 시 사이드 이펙트를 최소화하세요.

- widget_coin_list.py
  - Purpose: 실제 UI 위젯(CoinlistWidget)을 구현하며, coin_list.ui를 로드하고 UI 이벤트(검색, 정렬, 클릭), 가상 스크롤, 관심종목/설정 연동, UIStateManager 동기화를 담당합니다. CoinListLogic, ProgressController, CoinListWorker/TradeWorker, FavoriteWidget 등을 조합합니다.
  - Usage (예):
    - from src.coinlist.widget_coin_list import CoinlistWidget
    - widget = CoinlistWidget(parent)
    - parent_layout.addWidget(widget)
  - Cautions: 이 파일은 UI 바인딩과 이벤트 핸들링을 포함하므로 비즈니스 로직(네트워크 호출·DB 쓰기)은 worker로 위임해야 합니다(P2 규칙). QThread를 통한 워커 시그널 연결 시 위젯이 종료되면 시그널 연결 해제를 확실히 하여 참조 누수를 방지하세요. 대량 갱신 시 setUpdatesEnabled(False) 등의 최적화가 적용되어 있으니, 업데이트 방식 변경 시 성능 영향을 검증하세요.

- coinlist_logic.py
  - Purpose: CoinlistWidget의 데이터 처리/정렬/부분 업데이트/캐싱 로직을 제공하여 "변한 것만" UI에 반영하는 성능 개선 기능을 담당합니다. 셀별 캐시를 유지하여 불필요한 repaint를 줄입니다.
  - Usage (예):
    - from src.coinlist.coinlist_logic import CoinListLogic
    - logic = CoinListLogic(widget); logic.init_accumulators(); logic._set_text(row, col, "...")
  - Cautions: 내부 캐시 구조를 건드는 변경은 업데이트 최적화 동작을 깨트릴 수 있으므로 주의하세요. UI 컬럼 인덱스/열 이름 변경 시 cache key 규칙을 함께 업데이트해야 합니다.

- coinlist_workers.py
  - Purpose: UI의 블로킹을 방지하기 위한 백그라운드 워커 모음. CoinListWorker는 주기 스냅샷(기본 5초)을 emit하고, TradeWorker는 Upbit WebSocket(체결) 수신 후 누적값을 emit합니다. Worker는 UI를 직접 조작하지 않고 시그널로 통신합니다.
  - Usage (예):
    - from src.coinlist.coinlist_workers import CoinListWorker, TradeWorker
    - w = CoinListWorker(interval_sec=5); w.dataSent.connect(on_data); w.start()
    - t = TradeWorker(); t.tradeAccum.connect(on_trade_accum); t.start()
  - Cautions: 워커는 UI 스레드와 분리되어야 하며 UI 접근은 시그널/슬롯으로만 해야 합니다. TradeWorker는 네트워크 오류(429 등)를 처리하므로 로그/백오프 정책을 확인하세요. 워커 종료 시 close()/quit()/wait()를 호출하여 스레드를 안전히 정리해야 합니다.

- coinlist_format.py
  - Purpose: 종목 테이블에서 사용하는 숫자/가격 표기 유틸리티(format_price) 제공 — 가격에 따라 소수점 자리수를 자동으로 조정합니다.
  - Usage (예):
    - from src.coinlist.coinlist_format import format_price
    - s = format_price(1234.5)
  - Cautions: 포맷 규칙 변경 시 UI 표시가 달라져 사용자 혼란을 초래할 수 있으니 변경 내역을 문서화하세요.

- widget_time_settings.py
  - Purpose: Coinlist에서 사용하는 시간/임계값 설정 다이얼로그(TimeSettingsDialog)를 제공하여 계산 주기·임계값 등을 조정할 수 있게 합니다.
  - Usage (예):
    - from src.coinlist.widget_time_settings import TimeSettingsDialog
    - dlg = TimeSettingsDialog(parent, rate_calc=5000); dlg.exec_()
  - Cautions: 다이얼로그는 비모달/모달 옵션 모두 지원하므로 호출 컨텍스트에 맞게 사용하세요. 설정 변경은 즉시 적용되는 옵션과 재시작이 필요한 옵션으로 구분하여 UX를 제공해야 합니다.

- widget_favorite.py
  - Purpose: 관심종목 관리 팝업(FavoriteWidget)을 구현하여 사용자 관심 목록 편집, CSV 내보내기/가져오기, 그룹 관리 기능을 제공합니다. FavoriteWidget는 favorites_updated 시그널을 통해 변경을 알립니다.
  - Usage (예):
    - from src.coinlist.widget_favorite import FavoriteWidget
    - fav = FavoriteWidget(favorites, all_coins, parent); fav.show()
  - Cautions: 파일 입출력(export/import) 기능은 사용자의 파일 권한/경로를 검증해야 합니다. favorites_updated 시그널을 받는 쪽에서 동시성 처리(예: 다중 팝업) 유의하세요.

- coin_list.ui
  - Purpose: Qt Designer 형식의 UI 정의 파일로 종목 테이블 레이아웃, 검색, 버튼, 프로그레스바 등을 정의합니다.
  - Usage:
    - 편집: Qt Designer로 src/coinlist/coin_list.ui 열기/수정
    - 런타임: uic.loadUi(_ui_file_path("coin_list.ui"), self) 또는 pyuic로 변환
  - Cautions: .ui 파일은 오로지 '뷰'만 포함해야 하며 로직/비즈니스 코드를 넣지 마세요. UI 변경 후 위젯 이름이 코드에서 참조되는 이름과 일치하는지 반드시 확인하세요.

- coinlist_progress.py
  - Purpose: 진행 상태(프로그레스바 및 상태 라벨)를 큐 기반으로 관리하며 애니메이션·스로틀 등을 통해 부드러운 UX를 제공합니다. ProgressController는 start_progress / set_idle_status / shutdown 등을 제공합니다.
  - Usage (예):
    - from src.coinlist.coinlist_progress import ProgressController
    - pc = ProgressController(widget); pc.start_progress("Scanning", 100)
  - Cautions: ProgressController.shutdown()을 호출하여 위젯 참조 해제를 수행하지 않으면 위젯이 제거된 후 접근 시 예외가 발생할 수 있습니다. min_show_seconds 등 옵션을 조정해 작은 작업에서 불필요한 UI 깜박임을 억제하세요.

- coinlist_search.py  (참조: widget_coin_list imports)
  - Purpose: 검색/자동완성(초성/로마자 등) 관련 로직을 제공하여 빠른 종목 검색을 지원합니다.
  - Usage (예):
    - from src.coinlist.coinlist_search import CoinListSearchController
    - sc = CoinListSearchController(widget); sc.search("비트")
  - Cautions: 검색 알고리즘(특히 초성/로마자 변환)은 지역화 이슈를 유발할 수 있으므로 테스트 케이스(한글/영문/혼합)를 충분히 작성하세요.

USAGE — 로컬 개발 및 실행(복사·붙여넣기 가능한 명령)

1) 개발 환경 준비
- python -m venv .venv
- source .venv/bin/activate   # Windows: .\.venv\Scripts\Activate.ps1
- pip install -r requirements.txt

2) UI 실행(앱 전체가 제공되는 경우)
- python -m src.app.main
  (CoinlistWidget은 window_main 또는 패널 레이아웃에서 로드됩니다.)

3) 위젯 단위 빠른 검사(간단 REPL)
- python -c "from src.coinlist.widget_coin_list import CoinlistWidget; print('import ok')"

4) 워커 시뮬레이션(개발용)
- python -c "from src.coinlist.coinlist_workers import CoinListWorker; w=CoinListWorker(1); w.dataSent.connect(lambda d: print(len(d))); w.start(); import time; time.sleep(3); w.close()"

DEVELOPMENT · LINT · TEST
- pip install -r requirements-dev.txt
- black --check src/coinlist
- flake8 src/coinlist
- mypy src/coinlist
- bandit -r src/coinlist
- pytest tests/coinlist -q  # 테스트가 존재할 경우

RUNTIME CONFIGURATION
- 데이터 소스: static.chart.coins 와 같은 전역 싱글톤 데이터 구조를 사용하여 UI와 동기화합니다. static 모듈의 변경은 전체 UI 동작에 영향을 미치므로 주의하세요.
- 타이머/주기: CoinListWorker 기본 주기는 5초(구성 가능)입니다. TradeWorker는 Upbit WebSocket(체결)에서 이벤트를 받아 누적 업데이트를 보냅니다.
- 민감정보: Coinlist는 API 키를 직접 사용하지 않지만 TradeWorker/다른 모듈이 인증을 필요로 하는 경우 민감정보는 환경변수/시크릿으로 관리하세요.

WARNINGS / CRITICAL NOTES
- UI 스레드 블로킹 금지: 모든 네트워크/IO/무거운 계산은 QThread(또는 백그라운드 태스크)에서 실행되어야 합니다. UI에서 직접 sleep/IO 호출 금지.
- 데이터 포맷 호환성: widget_coin_list 및 coinlist_logic이 기대하는 데이터 구조(static.chart.coins의 Coin 객체 필드 등)를 변경하지 마세요. 필드 변경이 필요하면 변환 어댑터를 추가하고 영향을 받는 모든 위젯을 업데이트하세요.
- 파일 이름/인터페이스 변경: 파일/심볼명 변경은 window_main/다른 위젯에서의 import 경로를 깨뜨릴 수 있으므로 사전 합의 및 테스트를 거치세요.
- Worker 종료: 앱 종료 또는 위젯 제거 시 모든 워커에 대해 close()/quit()/wait()를 호출해 스레드가 안전히 종료되도록 하세요.

TROUBLESHOOTING (자주 발생 문제 및 해결 팁)
- 테이블이 갱신되지 않음: CoinListWorker.dataSent 신호가 emit 되는지 확인. signal-slot 연결을 확인하고, widget이 유효한지(삭제되지 않았는지) 확인하세요.
- Trade 누적이 이상함: TradeWorker.on_message에서 파싱된 amount 계산(가격 * 체결량) 및 ask_bid 값('BID'/'ASK') 필터링 로직을 검증하세요.
- 검색 성능 저하: coinlist_search의 인덱스/자동완성 로직을 프로파일링하고 debounce(입력 지연) 설정을 최적화하세요.
- UI 깨짐/플리커: 대량 갱신 시 CoinListLogic의 "변한 것만" 업데이트가 제대로 동작하는지 확인 — cache 키 충돌이나 컬럼 인덱스 변경이 원인일 수 있습니다.

BACKUP & ROLLBACK
- UI/로직 변경 전 커밋을 하고 브랜치 생성. 중요 변경(예: 컬럼 삭제/스키마 변경)은 docs/previous_stages/에 원본 저장 권장.
- 롤백: 이전 커밋으로 체크아웃하고 smoke test(앱 시작 → Coinlist 로드 → 샘플 데이터 반영) 수행.

TESTING CHECKLIST (변경 시 수행)
- 위젯 임포트 테스트: from src.coinlist import CoinlistWidget 가 정상 동작하는지 확인.
- 워커 라이프사이클: CoinListWorker/TradeWorker start → emit → close 시 예외 없음.
- UI 상호작용: 검색/정렬/클릭 시 chart/orderbook/trade 핸들러가 호출되어 심볼 동기화 되는지 확인.
- 관심종목: FavoriteWidget에서 추가/삭제/내보내기 기능 동작 확인 및 favorites_updated 이벤트 수신 확인.
- lint/mypy/pytest 통과.

REFERENCES
- window_main.py (위젯 통합 및 setOrder/setChart 연결 지점)
- static (전역 chart/coins 구조 참조)
- work_order/README_작성_가이드.md, work_order/규칙.md (문서·변경 정책)
- scripts/doc_check.py, verify_phase2.py (레포 검증 도구)

AUTHOR / CONTACT
- 작성자: Copilot (자동 생성 규칙에 따름)
- Last Modified: 2026-01-31

--------------------------------------------------------------------------------
다음으로 작성할 폴더 README.md 제안: src/login/README.md  
(진행할 경우 바로 작성 시작하겠습니다.)
