# CHANGELOG
# 2026-03-05 | Copilot | Updated: Added logic/ directory with orderbook_calc.py, added __all__ export
# 2026-01-31 | Copilot | 생성/재작성: src/orderbook/README.md. 영향: src/orderbook 폴더 문서화(위젯/워커/주의사항 포함). 테스트: 로컬 UI 실행 및 워커 주기 변경 권장.

Version: v1.1
Last Modified: 2026-03-05 | Copilot

# README: src/orderbook
Purpose: 호가창(Orderbook) UI와 관련 로직(실시간 호가, 체결, 거래 강도, 마켓뎁스 시각화)을 제공합니다. 이 폴더는 OrderbookWidget, OrderbookWorker, depth chart 캔버스 및 관련 UI 파일을 포함하고 있으며, component.RealtimeManager가 관리하는 Coin 객체의 orderbook 데이터를 UI에 안전하게 표시하는 역할을 합니다.

Important: README_작성_가이드.md 규칙을 준수하여 상단 CHANGELOG/Version/Last Modified를 포함했습니다. 이 문서는 src/orderbook 폴더의 직접 포함 파일만 다루며, 파일별로 Purpose / Usage / Cautions를 상세히 기술합니다. 검색 결과가 도구 제한으로 일부 파일이 누락되었을 수 있으므로 전체 파일 목록은 GitHub에서 확인하세요:
https://github.com/JUN-JONG-IL/upbit-trader-master/tree/main/src/orderbook

FILES (각 항목: 파일명 / Purpose / Usage / Cautions)

- README.md
  - Purpose: src/orderbook 폴더의 개요, 파일별 설명, 실행/개발 지침 및 주의사항을 제공합니다.
  - Usage: Orderbook 관련 개발 또는 UI 변경 전 본 문서를 먼저 확인하세요.
  - Cautions: UI/데이터 포맷 변경 시 영향을 받는 다른 모듈(예: Chart, Component)을 문서화하세요.

- __init__.py
  - Purpose: orderbook 패키지 진입점으로 OrderbookWidget 심볼을 외부에 노출합니다.
  - Usage:
    - from src.orderbook import OrderbookWidget
  - Cautions: __init__.py에 네트워크/워커 초기화 같은 무거운 로직을 넣지 마세요.

- orderbook.ui
  - Purpose: Qt Designer로 작성된 호가창 UI 정의 파일(테이블, depth chart 영역, 컨트롤 버튼 등).
  - Usage:
    - 편집: Qt Designer에서 src/orderbook/orderbook.ui 열기/수정
    - 런타임: uic.loadUi(_ui_file_path("orderbook.ui"), self) 또는 pyuic 변환
  - Cautions: UI 위젯 이름과 코드에서 참조하는 객체명이 일치해야 합니다. UI 변경 시 위젯 바인딩을 확인하세요.

- widget_orderbook.py
  - Purpose: OrderbookWidget 구현체로, OrderbookWorker를 통해 Coin 객체의 orderbook을 주기적으로 조회하고 UI를 업데이트하며, depth chart(FigureCanvas)를 사용하여 시각화합니다. 또한 UIStateManager와 심볼 동기화를 담당합니다.
  - Usage (예):
    - from src.orderbook.widget_orderbook import OrderbookWidget
    - w = OrderbookWidget(parent); layout.addWidget(w)
  - Cautions:
    - Worker 라이프사이클: OrderbookWorker는 내부에서 루프를 돌며 데이터를 폴링하므로 위젯 closeEvent에서 worker.close()/wait() 등 안전 종료 절차를 반드시 호출해야 합니다.
    - 폴링 주기: 기본 0.5초(권장)로 설정되어 있으며 과도한 빈도로 설정하면 CPU 부하 및 네트워크/데이터 경쟁이 발생할 수 있습니다. 필요 시 throttle 유틸을 이용하여 redraw 빈도를 제어하세요.
    - 데이터 포맷: Coin 객체의 orderbook 포맷을 변경하면 OrderbookWidget에서 기대하는 필드(ap/as/bp/bs 등)이 달라져 UI가 깨질 수 있습니다. 포맷 변경 시 어댑터 레이어를 추가하고 영향 범위를 문서화해야 합니다.
    - Depth Chart 렌더링: matplotlib 기반 렌더링은 무거울 수 있으므로 Blit 또는 draw_idle/스레드 스케줄링을 적절히 사용하여 GUI 스레드 블로킹을 방지하세요.

USAGE — 로컬 개발 및 실행(복사·붙여넣기 가능한 명령)

1) 개발 환경 준비
- python -m venv .venv
- source .venv/bin/activate  # Windows: .\.venv\Scripts\Activate.ps1
- pip install -r requirements.txt

2) 앱 실행(전체)
- python -m src.app.main
  (OrderbookWidget은 MainWindow 레이아웃 내에 로드됩니다.)

3) 위젯 단위 빠른 검사(개발용)
- python -c "from src.orderbook.widget_orderbook import OrderbookWidget; print('import ok')"

4) Worker 시뮬레이션(샘플)
- python -c "from src.orderbook.widget_orderbook import OrderbookWorker; w=OrderbookWorker('BTC'); w.dataSent.connect(lambda c: print('tick', c)); w.start(); import time; time.sleep(1); w.alive=False; w.quit()"

DEVELOPMENT · LINT · TEST
- pip install -r requirements-dev.txt
- black --check src/orderbook
- flake8 src/orderbook
- mypy src/orderbook
- bandit -r src/orderbook
- pytest tests/orderbook -q  # 존재할 경우

RUNTIME CONFIGURATION
- 데이터 소스: component.RealtimeManager가 관리하는 Coin 객체(static.chart.coins[ticker])에서 orderbook/체결 데이터를 조회합니다. RealtimeManager 설정 및 Coin API의 필드 스키마를 확인하세요.
- 폴링/스로틀: OrderbookWorker 폴링 주기와 depth chart redraw throttle 값을 환경 설정으로 노출하는 것을 권장합니다(예: config.yaml).
- 민감정보: Orderbook 자체는 민감정보를 다루지 않지만, 연동된 모듈(Account/Order 등은 민감정보 취급). 연동 시 보안 정책을 준수하세요.

WARNINGS / CRITICAL NOTES
- 실시간 데이터 부하: 다수의 위젯이 동시에 높은 빈도로 데이터를 폴링하거나 렌더링하면 전체 UI 성능에 큰 영향을 미칩니다. 가능한 경우 이벤트 기반 푸시(예: Redis Pub/Sub 또는 WebSocket)로 전환하세요.
- 기능 변질 금지: 기존 UI 동작(컬럼, 색상 규칙, 버튼 동작 등)을 임의로 변경하지 마세요. 변경이 필요한 경우 영향 범위를 문서화하고 테스트를 수행하세요.
- 워커 안전 종료 필수: 위젯 close/앱 종료 시 모든 worker에 대해 안전한 종료(stop/quit/wait)를 보장하세요.

TROUBLESHOOTING (자주 발생 문제 및 해결 팁)
- UI가 자주 깜빡임: redraw 빈도가 너무 높음 — throttle 값 또는 worker 폴링 주기(더 긴 간격)로 조정.
- Orderbook 데이터가 보이지 않음: static.chart.coins에 해당 ticker 데이터가 있는지, Coin 객체의 필드(ap/as/bp/bs)가 존재하는지 확인.
- Depth 차트 렌더 오류: matplotlib Figure나 Canvas의 상태(backend, 스레드 컨텍스트)를 확인. draw_idle 사용 권장.

TESTING CHECKLIST (변경 시 수행)
- 위젯 임포트 테스트: from src.orderbook import OrderbookWidget
- Worker 라이프사이클: OrderbookWorker start → dataSent emit → worker stop
- UI 상호작용: 심볼 변경 시 RealtimeManager와 연동되어 데이터가 바뀌는지 확인
- lint/mypy/pytest 실행 및 통과

REFERENCES
- component.RealtimeManager (데이터 소스)
- static 모듈 (전역 차트/코인 데이터 싱글톤)
- work_order/README_작성_가이드.md, work_order/규칙.md (문서·변경 정책)
- scripts/doc_check.py (문서 검사)

AUTHOR / CONTACT
- 작성자: Copilot (자동 생성 규칙에 따름)
- Last Modified: 2026-01-31

--------------------------------------------------------------------------------
다음으로 작성할 폴더 README.md 제안: src/trade/README.md  
(진행하겠습니다면 바로 작성 시작합니다.)
