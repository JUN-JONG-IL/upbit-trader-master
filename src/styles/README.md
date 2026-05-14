# CHANGELOG
# 2026-01-31 | Copilot | 생성/재작성: src/static/README.md. 영향: src/static 폴더 문서화(전역 상태/상수/로깅 초기화 규칙 포함). 테스트: 모듈 임포트 시 초기화 로그 확인 권장.

Version: v1.0
Last Modified: 2026-01-31 | Copilot

# README: src/static
Purpose: 애플리케이션 전역에서 사용하는 상수, 설정(config), 로거, 싱글톤 관리자(Chart, Account, SignalManager 등)의 중앙 저장소입니다. static 모듈은 전체 앱의 '글로벌 상태'와 초기화 로직을 책임지며, 다른 모듈들이 `import static`을 통해 공통 인스턴스에 접근하도록 합니다.

Important: 상단에 CHANGELOG/Version/Last Modified를 포함했으며, README_작성_가이드.md 규칙을 따랐습니다. 이 문서는 src/static 폴더 내부 파일만 다루며, 검색 결과가 도구 제한으로 완전하지 않을 수 있으니 GitHub에서 전체 파일 목록 확인 권장:
https://github.com/JUN-JONG-IL/upbit-trader-master/tree/main/src/static

FILES (각 항목: 파일명 / Purpose / Usage / Cautions)

- README.md
  - Purpose: static 패키지의 목적/구성/운영 규약을 서술합니다.
  - Usage: 전역 상태 변경 전 반드시 본 문서를 검토하고 영향 범위를 파악하세요.
  - Cautions: 전역 객체 추가/변경은 팀 합의 및 문서화가 필요합니다.

- static.py
  - Purpose: 전역 상수(MIN_TRADE_PRICE, FEES, FIAT 등), config 인스턴스, 로거 초기화 및 전역 라이브러리 로거 설정을 수행합니다. 또한 프로그램 전역에서 사용되는 싱글톤 인스턴스(예: upbit, chart, account 등)를 초기화/노출하는 역할을 담당합니다.
  - Usage:
    - import static
    - print(static.FIAT)
    - static.log.info("message")
  - Cautions:
    - initialization side-effects: static 모듈은 import 시 바로 실행되어 로거 설정 및 config.load() 등을 수행하므로 테스트 시에는 import에 주의하세요(예: 테스트 전용 mock 사용).
    - 전역 상태 변경: static.config, static.account 등 전역 객체를 직접 수정하는 것은 예측 불가능한 부작용을 일으킬 수 있으므로 표준 API(메서드)를 통해 변경하세요.
    - 패키징: _get_src_dir / utils.get_file_path 경로와 마찬가지로 패키징 환경에서 경로/리소스 접근 문제가 발생할 수 있으므로 빌드 테스트 필요.

- __init__.py
  - Purpose: static 패키지 진입점으로 전역 상수/핵심 인스턴스를 외부에서 편리하게 import 할 수 있게 합니다.
  - Usage:
    - from static import log, config, MIN_TRADE_PRICE
  - Cautions: __init__에서 존재하지 않는 심볼을 노출하면 ImportError를 발생시킬 수 있으므로 export 대상 심볼의 존재 여부를 확인하세요.

RUNTIME / OPERATION GUIDELINES
- 전역 인스턴스 접근:
  - 권장 방식: 읽기 전용 접근(read-only) 권장. 수정이 필요한 경우 명시적 메서드(예: config.set(...)) 사용.
- 로깅:
  - static.log는 초기화 시점에 설정되며, 전역 로거 레벨 및 핸들러는 config 값에 따라 구성됩니다. 프로덕션 환경에서는 로그 레벨 및 파일 경로를 적절히 구성하세요.
- 환경 설정:
  - config.load()가 static 초기화 과정에서 호출됩니다. 설정 파일 변경 후에는 앱 재시작 또는 config.reload()와 같은 명시적 로직을 구현하세요.

WARNINGS / CRITICAL NOTES
- 전역 상태 오염: 전역 객체를 임의로 생성/변경하면 테스트 및 동시성 문제를 야기합니다. 변경 시 문서화 및 테스트 케이스 작성 필수.
- Import-time effects: static 모듈이 import 시 외부 라이브러리를 설정하거나 시스템 출력을 남기므로(로그 초기화) 모듈 임포트만으로 부작용이 발생할 수 있습니다. 유닛 테스트에서는 import 시점 부작용을 격리(mock)하세요.
- Singleton lifecycle: 일부 전역 인스턴스는 start/stop가 필요합니다(예: signal_manager.start()). 애플리케이션 종료 시 적절히 종료하도록 종료 훅을 등록하세요.

TROUBLESHOOTING
- static import 실패: utils.get_file_path나 config 로딩 경로 문제일 가능성이 높습니다. 패키징(frozen) 환경에서 경로 기반 로직을 우선 점검하세요.
- 로거 불일치: 로그가 출력되지 않거나 레벨이 다를 때는 static.config.log_level 및 root logger 핸들러 구성을 확인하세요.
- 전역 객체 미존재: static.__init__ 또는 static.static.py에서 특정 인스턴스가 export되지 않은 경우, 해당 심볼의 초기화 시점을 확인하고 lazy-init 방식을 고려하세요.

REFERENCES
- utils (리소스 경로 및 로거 초기화 관련)
- work_order/README_작성_가이드.md, work_order/규칙.md (변경 정책)
- 기타: app/window_main.py (전역 인스턴스 사용 예)

AUTHOR / CONTACT
- 작성자: Copilot (자동 생성 규칙에 따름)
- Last Modified: 2026-01-31

--------------------------------------------------------------------------------
Next proposed README.md to write: src/styles/README.md or src/server/README.md (already created). 진행하겠습니다면 선택해주세요.
