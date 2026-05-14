# CHANGELOG
# 2026-03-15 | Copilot | 업그레이드: src/core/auth/README.md v4.0. 폴더 구조 최적화.
# 2026-01-31 | Copilot | 생성/재작성: src/login/README.md. 영향: src/login 폴더 문서화(로그인 UI/더미 계정/주의사항 포함). 테스트: 로컬 GUI 시작 예시 포함.

Version: v4.0
Last Modified: 2026-03-15

# README: src/login
Purpose: 애플리케이션 시작 시 사용자 인증(실계정 또는 데모/임시 로그인)을 처리하는 UI 및 관련 유틸을 제공합니다. 로그인 위젯은 API 키 입력, 키 저장 옵션, 데모 계정(더미 계정) 지원을 제공하며, MainWindow로 안전하게 전환하는 역할을 합니다. 이 문서는 src/login 폴더의 직접 포함 파일만 다루며, 각 파일별 목적, 사용법, 주의사항을 상세히 기술합니다.

Important: README_작성_가이드.md 규칙을 준수하여 CHANGELOG/Version/Last Modified를 상단에 포함했습니다. 검색 결과가 도구 제한으로 불완전할 수 있으므로 전체 파일 목록은 GitHub에서 확인하세요:
https://github.com/JUN-JONG-IL/upbit-trader-master/tree/main/src/login

FILES (각 항목: 파일명 / Purpose / Usage / Cautions)

- README.md
  - Purpose: src/login 폴더의 구성, 파일별 책임, 실행·개발 절차 및 주의사항을 통합 제공합니다.
  - Usage: 로그인 관련 변경 전 본 파일을 읽고 더미 계정/실계정 전환 로직을 숙지하세요.
  - Cautions: 로그인 로직 변경(특히 인증 흐름, 키 저장 방식)은 보안에 민감하므로 문서화 및 검토가 필요합니다.

- __init__.py
  - Purpose: login 패키지 진입점으로 gui_main 및 LoginWidget을 외부에 노출합니다.
  - Usage:
    - from src.login import gui_main, LoginWidget
  - Cautions: __init__.py에 무거운 초기화를 넣지 마세요.

- login.ui
  - Purpose: Qt Designer 형식의 로그인 화면 UI를 정의합니다(접속 정보 입력란, 키 저장 체크박스, 커스텀 타이틀바 등).
  - Usage:
    - 편집: Qt Designer로 src/login/login.ui 열기/수정
    - 런타임: uic.loadUi(_ui_file_path("login.ui"), self)
  - Cautions: UI에서 사용되는 위젯 객체명은 widget_login.py에서 참조하므로 이름 변경 시 코드도 함께 업데이트해야 합니다.

- widget_login.py
  - Purpose: LoginWidget과 데모 계정(DummyAccountForMemberLogin/DummyUpbit)을 구현하며, 로그인 성공 시 MainWindow로 전환하는 로직을 포함합니다. 더미 계정은 메인 앱에서 기대하는 최소한의 API(stub)를 제공하여 데모 모드로 앱을 실행할 수 있게 합니다.
  - Usage (개발용 예):
    - from src.login.widget_login import gui_main, LoginWidget
    - gui_main()  # Qt 애플리케이션 시작 및 로그인 UI 표시(로컬 테스트)
    - 또는
    - w = LoginWidget(); w.show()
  - Cautions:
    - 민감정보: Access/Secret 키 입력/저장은 매우 민감합니다. 키 저장 기능은 암호화 또는 OS 시크릿 스토어 사용을 권장합니다. 절대 평문으로 Git에 커밋하지 마세요.
    - Dummy 계정: DummyUpbit/DummyAccount는 데모·개발용 스텁이며 실제 거래 기능을 제공하지 않습니다. 데모 계정을 사용하여 실거래를 시도하지 마세요.
    - UI 경로: loadUi는 파일 시스템 경로를 기반으로 하므로 배포 시 패키징(예: cx_Freeze) 방식에 따라 경로가 달라질 수 있습니다. 실행 환경에서 ui 파일 경로가 올바른지 점검하세요.
    - Application attributes: PyQt5의 setAttribute 호출은 QApplication 생성 전에 이루어져야 합니다. 코드 구조 변경 시 이 순서를 유지하세요.

USAGE — 로컬 개발 및 실행(복사·붙여넣기 가능한 명령)
1) 개발 환경 준비
- python -m venv .venv
- source .venv/bin/activate   # Windows: .\.venv\Scripts\Activate.ps1
- pip install -r requirements.txt

2) 로그인 UI 단독 실행(개발용)
- python -c "from src.login.widget_login import gui_main; gui_main()"
  (또는) python -m src.login.widget_login  # 파일에 __main__ 핸들러가 있을 경우

3) 애플리케이션 전체 실행(로그인 포함)
- python -m src.app.main

SECURITY / CONFIGURATION NOTES
- 키 저장: checkBox_save_user 옵션 사용 시 키 저장 방식을 암호화하거나 OS 시크릿 스토어(Windows Credential Manager / macOS Keychain / Linux Secret Service) 이용 권장.
- 환경 분리: 개발/테스트와 실거래(LIVE) 환경은 분리된 설정을 사용하도록 config 또는 환경변수 설정을 분명히 하세요.
- 로그: 로그인 실패나 예외는 민감 정보를 포함하지 않도록 sanitize해서 로그에 기록하세요.

WARNINGS / CRITICAL NOTES
- 실거래 호출 금지: widget_login의 더미 계정/데모 기능을 유효하게 사용하더라도 실거래 API 호출을 의도치 않게 발생시키지 않도록 주의하세요. 실거래용 Account 인스턴스와 데모용 DummyAccount는 명확히 구분되어야 합니다.
- 변경 시 승인: 인증 흐름·키 저장·복구 로직 변경은 보안 검토를 거쳐야 하며 필요 시 관리자 승인을 받으세요.

TROUBLESHOOTING (문제 & 해결 팁)
- UI 파일 로드 실패: _ui_file_path 경로가 올바른지 확인(패키징 환경에서 경로 문제 흔함).
- DummyUpbit 동작 문제: DummyUpbit의 메서드(get_balances 등)가 메인 코드에서 기대하는 반환 형태와 일치하는지 확인하세요.
- QApplication 속성 문제: QApplication 인스턴스 생성 전 Qt 애트리뷰트 설정(setAttribute)을 호출하지 않았을 경우 예외가 발생할 수 있습니다.

TESTING CHECKLIST
- GUI 시작: gui_main() 실행 시 로그인 창이 뜨는지 확인.
- 더미 계정: 더미 계정으로 로그인 후 MainWindow로 전환되는지 확인(주요 위젯들이 존재하는지).
- 키 저장: 체크박스 사용 시 키 저장/불러오기가 안전하게 동작하는지 확인(암호화/권한 이슈).
- lint/mypy/pytest: static 분석 도구 실행 권장.

REFERENCES
- src/config.yaml (전역 설정 참조)
- work_order/README_작성_가이드.md, work_order/규칙.md (문서·변경 정책)
- scripts/doc_check.py (문서 검사 도구)

AUTHOR / CONTACT
- 작성자: Copilot (자동 생성 규칙에 따름)
- Last Modified: 2026-01-31

--------------------------------------------------------------------------------
다음으로 작성할 폴더 README.md 제안: src/orderbook/README.md  
(진행하겠습니다면 바로 작성 시작합니다.)
