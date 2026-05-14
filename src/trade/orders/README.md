# CHANGELOG
# 2026-01-31 | Copilot | 생성/재작성: src/trade/README.md. 영향: src/trade 폴더 문서화(주문 위젯/워커/주의사항 포함). 테스트: 로컬 GUI 실행 및 워커 시뮬레이션 권장.

Version: v1.0
Last Modified: 2026-01-31 | Copilot

# README: src/trade
Purpose: 주문 입력(지정가/시장가/예약), 미체결/체결 내역 조회, 주문 취소 기능을 제공하는 트레이드(Trade) 모듈입니다. TradeWidget과 TradeWorker를 포함하며, Orderbook/Chart/Account 모듈과 연동되어 사용자의 주문 흐름을 관리합니다.

Important: README_작성_가이드.md 규칙을 준수하여 상단 CHANGELOG/Version/Last Modified를 포함했습니다. 이 문서는 src/trade 폴더의 직접 포함 파일만 다루며, 각 파일에 대해 Purpose / Usage / Cautions를 상세히 제공하고 있습니다. 검색 결과가 도구 제한으로 일부 파일 누락 가능성이 있으므로 전체 목록은 GitHub에서 확인하세요:
https://github.com/JUN-JONG-IL/upbit-trader-master/tree/main/src/trade

FILES (각 항목: 파일명 / Purpose / Usage / Cautions)

- README.md
  - Purpose: src/trade 폴더의 목적, 파일별 설명, 사용·개발 지침 및 주의사항을 통합 제공합니다.
  - Usage: 주문/체결 관련 개발 작업 전 이 파일을 읽어 아키텍처와 연동 포인트를 숙지하세요.
  - Cautions: 주문/결제 흐름 변경은 실거래 리스크와 직결되므로 문서화 및 승인 절차를 거치세요.

- __init__.py
  - Purpose: trade 패키지 진입점으로 TradeWidget을 외부에 노출합니다.
  - Usage: from src.trade import TradeWidget
  - Cautions: __init__.py에서의 부작용 최소화(네트워크 호출 등).

- trade.ui
  - Purpose: Qt Designer로 작성된 주문 위젯 UI 정의(매수/매도 탭, 입력 필드, 주문 버튼, 미체결/체결 테이블 등).
  - Usage: 수정 시 Qt Designer 사용. 런타임에서 uic.loadUi(_ui_file_path("trade.ui"), self) 방식으로 로드.
  - Cautions: UI 변경 시 widget_trade.py 내 위젯명을 함께 업데이트해야 합니다.

- widget_trade.py
  - Purpose: TradeWidget 구현 파일로, trade.ui를 로드하고 주문 입력 로직(가격/수량 계산, 주문 타입 전환), TradeWorker 기반의 주문 상태 폴링 및 UI 갱신을 담당합니다. 주문 API는 static.account.upbit을 통해 호출되며, 데모 모드에서는 시뮬레이션 처리됩니다.
  - **비동기 처리 (Async)**: TradeWorker는 asyncio 이벤트 루프를 사용하여 0.5초마다 주문 상태를 폴링하며, `asyncio.sleep(0.5)`로 UI 블로킹을 방지합니다.
  - Usage (예):
    - from src.trade.widget_trade import TradeWidget
    - w = TradeWidget(parent); layout.addWidget(w)
  - Cautions:
    - TradeWorker는 완전 비동기 패턴으로 구현되어 있어 UI 프리징을 방지합니다. 기존 `time.sleep()` 호출은 제거되었습니다.
    - 주문/취소 로직은 실거래 리스크가 있으므로 반드시 확인 대화상자(confirmation) 또는 다중 인증을 통해 오작동을 방지해야 합니다.
    - static.account.upbit API 호출 실패(네트워크/인증 오류) 시 사용자에게 명확한 에러 메시지를 제공하고 재시도 로직을 구현하세요.

USAGE — 로컬 개발 및 실행(복사·붙여넣기 가능한 명령)

1) 개발 환경 준비
- python -m venv .venv
- source .venv/bin/activate  # Windows: .\.venv\Scripts\Activate.ps1
- pip install -r requirements.txt

2) 전체 앱 실행(주문 UI 포함)
- python -m src.app.main

3) 위젯 단위 테스트(빠른 임포트 검사)
- python -c "from src.trade.widget_trade import TradeWidget; print('import ok')"

4) TradeWorker 시뮬레이션(개발용)
- python -c "from src.trade.widget_trade import TradeWorker; w=TradeWorker('KRW-BTC'); w.dataSent.connect(lambda d,t: print('data', t)); w.start(); import time; time.sleep(2); w.close()"

DEV · LINT · TEST
- pip install -r requirements-dev.txt
- black --check src/trade
- flake8 src/trade
- mypy src/trade
- bandit -r src/trade
- pytest tests/trade -q  # 존재 시

RUNTIME CONFIGURATION
- 데모 모드: static.config.upbit_access_key 여부로 데모/실거래 모드 결정. 데모 모드에서는 주문/취소가 시뮬레이션됩니다.
- 민감정보: API 키는 환경변수 또는 OS 시크릿 스토어로 관리. 절대 레포에 평문 저장 금지.
- 주문 확인: 실거래 전 사용자가 확인할 수 있는 절차(예: 모달 확인, 2단계 확인)을 구현하세요.

WARNINGS / CRITICAL NOTES
- 실거래 리스크: 주문 로직 변경은 금전적 손실을 초래할 수 있습니다. 변경 시 영향 분석 및 사용자 승인 필요(P4 조건 준수).
- **성능 최적화 완료**: TradeWorker는 asyncio 기반으로 완전히 재작성되어 UI 블로킹이 제거되었습니다. 기존 `time.sleep()` 사용은 `asyncio.sleep()`로 대체되었습니다.
- 데이터 동기화: Orderbook/Chart와 가격 동기화가 정확해야 주문 가격/수량 계산이 일관됩니다. 심볼/환율 매핑 오류 주의.

TROUBLESHOOTING (일반 문제 & 해결 팁)
- 주문 실패: static.account.upbit의 예외/응답 코드 확인(잔고 부족, 인증 실패, 시장 상태 등).
- 미체결/체결 갱신 누락: TradeWorker가 정상적으로 실행 중인지 및 static.account.upbit.get_order가 정상 응답하는지 확인.
- UI 입력값 불일치: 단가/수량 계산 로직(슬라이더/버튼)이 잘못 연결되었는지 확인.

TESTING CHECKLIST (변경 시 수행)
- 위젯 임포트 테스트: from src.trade import TradeWidget
- TradeWorker 라이프사이클: start → dataSent emit → close
- 주문 API 호출 테스트: 데모 모드와 실거래 모드에서의 동작 확인(가능한 경우 sandbox)
- lint/mypy/pytest 통과

REFERENCES
- static.account (계정/Upbit API 래퍼)
- orderbook/coinlist/chart 모듈과의 연동점
- work_order/README_작성_가이드.md, work_order/규칙.md (문서·변경 정책)

AUTHOR / CONTACT
- 작성자: Copilot (자동 생성 규칙에 따름)
- Last Modified: 2026-01-31

--------------------------------------------------------------------------------
다음으로 작성할 폴더 README.md 제안: src/userinfo/README.md  
(원하시면 바로 시작하겠습니다.)
