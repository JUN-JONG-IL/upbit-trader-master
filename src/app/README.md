# CHANGELOG
# 2026-03-15 | Copilot | 업그레이드: src/app/README.md v4.0. 폴더 구조 최적화.
# 2026-01-31 | Copilot | 생성: src/app/README.md 작성. 영향: src/app 폴더 문서화. 테스트: 로컬 실행 가이드, lint/test 명령 포함.

Version: v4.0
Last Modified: 2026-03-15

# README: src/app
Purpose: 데스크톱 GUI 애플리케이션의 UI 레이어와 메인 윈도우를 포함하는 모듈로, 화면 구성(UI 파일), 윈도우/레이아웃 복원·보관, 스타일 및 윈도우 로직(시그널/이벤트 바인딩)을 담당합니다. 이 README는 src/app 폴더 내 모든 파일을 빠짐없이 설명하고, 실행/개발/배포 시 필요한 구체적 명령과 주의사항을 제공합니다.

Important: 이 폴더는 UI(.ui, layout.json, ui_styles.py)와 윈도우 로직(window_main.py) 및 진입점(main.py)을 포함합니다. README_작성_가이드에 따라 각 파일별로 목적, 사용법(복사·붙여넣기 가능한 명령/예제), 주의사항을 반드시 포함했습니다.

Files (상세 설명 — 각 항목은 '파일명 / 목적 / 사용 예 / 주의사항' 순서로 1문단으로 작성됨):

- README.md
  - 목적: 이 파일은 src/app 폴더의 구성과 각 파일의 역할, 실행 방법, 주의사항, 개발·배포 권장 절차를 문서화합니다.
  - 사용법: 로컬에서 GUI를 실행하거나 패키징하기 전에 반드시 이 README의 지침을 확인하십시오.
  - 주의사항: 문서 변경 시 변경 이유와 영향 범위를 명확히 기록하세요(특히 UI/로직 분리 원칙 위반 시).

- __init__.py
  - 목적: src.app 패키지 초기화 파일로, 패키지 수준에서 필요한 기본 상수나 노출할 심볼을 정의할 수 있습니다.
  - 사용법: 다른 모듈에서 `from src.app import <symbol>` 또는 `import src.app` 방식으로 사용됩니다. 패키지 초기화 시 부작용이 발생하면 안 되므로 가볍게 유지합니다.
  - 주의사항: 무거운 연산, 블로킹 I/O, API 호출을 넣지 마세요. 패키지 임포트 시 실행되는 코드로 인해 테스트/임포트 실패가 발생할 수 있습니다.

- layout.json
  - 목적: 애플리케이션의 윈도우/패널 레이아웃 및 위치/크기/분할 상태를 저장하는 구성 파일입니다. ui_state_manager.py에서 읽고 쓰는 표준 포맷(프로젝트 고유 포맷)으로 사용됩니다.
  - 사용법: 일반적으로 수동으로 편집할 필요가 없으며, 레이아웃 변경은 앱 내 '레이아웃 저장/복원' 기능을 통해 적용됩니다. 수동 복구가 필요하면 이 파일을 백업 후 교체합니다.
  - 주의사항: 포맷을 임의로 변경하면 앱이 레이아웃 복원 실패로 시작하지 못할 수 있으므로 항상 백업을 유지하세요. 자동화 스크립트 또는 버전관리에서 binary/비교가 어렵다면 pretty JSON 저장을 권장합니다.

- main.py
  - 목적: 애플리케이션의 진입점(entry point)으로, QApplication(또는 해당 프레임워크) 초기화, 설정 로드(config), 메인 윈도우 생성 및 이벤트 루프 시작을 담당합니다.
  - 사용법(복사·붙여넣기 예제):
    - macOS / Linux:
      - python -m venv .venv
      - source .venv/bin/activate
      - pip install -r requirements.txt
      - python src/app/main.py
    - Windows:
      - python -m venv .venv
      - .venv\Scripts\activate
      - pip install -r requirements.txt
      - python src\app\main.py
    - (대체) 모듈 형식으로 실행: python -m src.app.main
  - 주의사항: 이 파일이 실제로 UI를 띄우고 환경변수/설정 파일(config.yaml 등)을 읽습니다. 실거래(LIVE) 모드로 동작할 수 있는 경우 API 키·시크릿이나 거래 모듈이 활성화되지 않도록 환경을 분리(예: PAPER/TEST 모드)하세요. 실행 전에 src/config.yaml과 레포 루트의 환경 설정을 확인하십시오. 또한 GUI 실행은 그래픽 환경(X 서버 혹은 macOS/Windows 데스크탑)이 필요합니다.

- main.ui
  - 목적: Qt Designer(또는 호환 도구)로 설계된 UI 정의 파일(.ui)로, 화면 레이아웃, 위젯 구조 및 기본 속성을 XML 형식으로 보관합니다.
  - 사용법: 애플리케이션은 PyQt/PySide에서 uic로 로드하거나 pyuic로 변환하여 사용합니다. 예: pyuic5 src/app/main.ui -o src/app/ui_main.py (프로젝트는 런타임에 직접 로드할 수 있음).
  - 주의사항: UI 파일은 순수 '뷰'로 취급하고 로직(window_main.py 등)과 분리해야 합니다. Qt Designer 외의 텍스트 편집기로 직접 수동 수정 시 구조가 깨질 수 있으므로 반드시 도구로 편집하세요. UI 변경 시 버전관리에서 diff 확인과 함께 레이아웃 테스트를 수행하세요.

- ui_state_manager.py
  - 목적: 윈도우 위치/크기, 분할 바 위치, 열/행 표시 설정 등의 UI 상태를 저장하고 복원하는 책임을 가집니다. layout.json과 상호작용합니다.
  - 사용법: main.py 또는 window_main.py에서 import 후 `UiStateManager.save(state)` / `UiStateManager.load()` 형태로 사용됩니다. 수동 호출 예: from src.app.ui_state_manager import UiStateManager; UiStateManager.backup_layout('backup.json')
  - 주의사항: 상태 저장/복원 로직은 사용자가 의도치 않게 커스텀 레이아웃을 덮어쓸 수 있으므로 '백업-검증-적용' 흐름을 권장합니다. layout.json을 직접 수정하지 말고, 가능하면 UI에서 '내보내기/가져오기' 기능을 제공하세요.

- ui_styles.py
  - 목적: 애플리케이션 전역 스타일(CSS 유사 스타일시트), 테마 색상, 폰트 규칙을 정의합니다. UI 일관성 유지와 빠른 테마 변경을 목적으로 중앙에서 스타일을 관리합니다.
  - 사용법: main.py 또는 window_main.py에서 import 후 `app.setStyleSheet(ui_styles.APP_STYLE)` 또는 필요한 위젯에 적용합니다.
  - 주의사항: 스타일 파일이 매우 클 수 있으므로 변경 시 렌더링 성능(특히 복잡한 셀렉터)을 검증하세요. 스타일 변경은 접근성(가독성, 대비)과 위젯 동작에 영향을 줄 수 있으므로 UX 테스트 필수입니다.

- window_main.py
  - 목적: 메인 윈도우 클래스(예: MainWindow)를 정의하며, UI에서 발생하는 시그널/이벤트와 어플리케이션의 응답(버튼 클릭, 메뉴, 단축키 바인딩)을 구현합니다. 뷰와 비즈니스 로직의 '바인딩' 역할을 수행합니다.
  - 사용법: main.py에서 인스턴스화하여 show()를 호출합니다. 예: from src.app.window_main import MainWindow; win = MainWindow(config); win.show()
  - 주의사항: 비즈니스 로직(데이터 처리, 주문 실행, 외부 API 호출)은 가능한 한 별도 모듈(예: src/trade, src/compute)로 분리하세요. window_main.py에는 UI-이벤트 바인딩과 간단한 어댑터 로직만 남겨야 합니다(P2 규칙 준수). 실거래 모드와 연결되는 부분은 반드시 명시적 사용자 확인 절차를 추가하고 로그를 남기십시오.

Usage (로컬 개발 및 실행 — 복사·붙여넣기 가능한 명령):

1) 로컬 개발 환경 (권장)
- Linux / macOS:
  - python -m venv .venv
  - source .venv/bin/activate
  - pip install -r requirements.txt
  - python src/app/main.py
- Windows (PowerShell):
  - python -m venv .venv
  - .\.venv\Scripts\Activate.ps1
  - pip install -r requirements.txt
  - python src\app\main.py

2) 패키징(예시 — cx_Freeze 기반)
- 참고: 패키징은 플랫폼별 이슈가 크므로 테스트 환경에서 먼저 수행하세요.
  - python src/setup_cxfreeze.py build
  - 생성된 dist 폴더의 실행 파일을 검증(그래픽 환경 필요)

3) 개발·정적 검사(권장)
- pip install -r requirements-dev.txt
- black --check .
- flake8
- mypy .
- bandit -r .
- pytest -q

Runtime configuration (환경 구성 관련):
- 민감정보: API 키, 비밀 키, 인증 토큰 등은 절대 레포지토리에 커밋하지 마세요. 환경변수 또는 로컬 비공개 설정 파일(예: ~/.config/upbit-trader/config.yaml, 또는 CI/Secrets)로 관리하십시오.
- 설정 파일: src/config.yaml 등의 전역 설정 파일을 참조합니다(루트의 config 파일 존재 여부 확인). 실행 전 설정 파일의 내용(모드: PAPER/LIVE, API 엔드포인트 등)을 확인하세요.
- 모드 분리: 개발/테스트용과 실거래(LIVE)용 설정을 엄격히 분리하십시오. 실거래 변경은 로그·검증·승인 절차를 거치십시오.

Warnings / Important Notes:
- 실거래 위험: 애플리케이션이 거래 모듈과 연결되도록 설계된 경우 실거래 버튼 또는 자동 주문 기능을 잘못 활성화하면 금전적 손실이 발생합니다. 실거래 관련 설정 변경은 사용자 확인(또는 다중 인증)을 거치고, 변경 내역을 문서화하세요.
- UI/로직 분리 준수(P2): .ui 파일은 화면, .py(특히 window_main.py)는 시그널/이벤트 바인딩, 비즈니스 로직은 src/compute, src/trade 등 별도 모듈에 둡니다. UI에 비즈니스 로직이 섞이지 않도록 주의하세요.
- 파일 크기·모듈 분리(P3): ui_styles.py나 window_main.py가 지나치게 커지면 모듈 분리를 고려하세요(파일당 500~800줄 권장).
- STAGE_LOCKED: 이 폴더의 파일은 일반적으로 개발 중 변경 가능하나, work_order 또는 상위 운영 규칙에서 STAGE 잠금 규칙이 적용되는 경우 해당 규칙을 준수하세요. 레포 전역 규칙(work_order/규칙.md)을 먼저 확인하십시오.
- 레이아웃 백업: layout.json 변경 전 또는 자동화 적용 전 반드시 백업을 생성하십시오(예: layout.json.bak.TIMESTAMP).

Development notes (개발자용 권장 사항):
- UI 변경 워크플로:
  1. Qt Designer로 main.ui 수정.
  2. pyuic로 변환(혹은 런타임 로드 방식으로 적절히 반영).
  3. window_main.py에서 시그널 바인딩 점검.
  4. ui_state_manager에 레이아웃 업데이트 로직 추가(필요시).
  5. UI/기능 통합 테스트(수동/자동) 수행.
- 코드 스타일 & 검사: requirements-dev.txt에 맞춘 lint/mypy/black 규칙을 준수하세요.
- 테스트: GUI 관련 자동화 테스트는 제한적이므로 smoke test(앱 시작/종료, 주요 위젯 존재 확인)를 포함한 수동 검사 시나리오를 문서화해 두세요.

Troubleshooting (자주 발생하는 문제와 해결 팁):
- 앱이 시작하지 않음: 그래픽 환경(X11/Wayland/Windows 데스크탑) 여부 확인. 원격 서버에서는 X 포워딩 또는 가상 디스플레이(Xvfb) 사용 필요.
- 레이아웃 로드 실패: layout.json 포맷 손상 가능성 — layout.json.bak에서 복원.
- 스타일 적용 실패: ui_styles.py의 문자열이 올바른 CSS 문법인지(특히 줄바꿈·이스케이프) 확인.
- 모듈 임포트 오류: 패키지 경로가 잘못되었거나 virtualenv 미활성화 상태. `python -m src.app.main` 권장.

Files to not modify unless necessary:
- main.ui: UI 설계 도구로 편집하세요.
- layout.json: 자동 저장 파일이므로 수동 편집 전 반드시 백업하세요.
- ui_styles.py, ui_state_manager.py, window_main.py: 변경 시 코드 리뷰와 테스트를 권장합니다.

Backup & Rollback (자동 변경 시 규칙):
- 변경 전에 docs/previous_stages/ 또는 로컬 백업 디렉터리에 원본을 보관하세요.
- 변경 기록은 간단한 changelog 항목(변경자, 변경일, 요약, 영향)을 남기십시오.
- 롤백: 원본 파일로 교체 후 앱을 재시작하고 smoke test 수행.

Reference & Related Files:
- 전역 설정: src/config.yaml
- 패키징 스크립트: src/setup_cxfreeze.py
- 레포 문서화 도구: scripts/doc_check.py (레포 루트 참조)
- 전체 개발 가이드: work_order/README_작성_가이드.md 및 work_order/규칙.md (레포 루트에서 반드시 확인)

Contact / Author:
- 작성자: Copilot (자동 생성 규칙에 따름)
- Last Modified: 2026-01-31

--------------------------------------------------------------------------------
(END OF src/app/README.md)
