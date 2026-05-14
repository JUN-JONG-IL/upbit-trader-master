# CHANGELOG
# 2026-03-15 | Copilot | 업그레이드: src/06_ai/prompt/README.md v4.0. 폴더 구조 최적화.
# 2026-01-31 | Copilot | 생성/재작성: src/prompt/README.md. 영향: prompt 폴더 문서화(CLI 프롬프트 인터페이스 설명). 테스트: prompt_main 메뉴 흐름 수동 테스트 권장.

Version: v4.0
Last Modified: 2026-03-15

# README: src/prompt
Purpose: GUI와 별도인 콘솔 기반 프롬프트(명령행) 인터페이스를 제공하여 개발자/운영자가 빠르게 시스템 상태를 조회하거나 전략을 수동으로 트리거할 수 있도록 합니다. prompt_main.py가 메인 루프이며, 전략 테스트, WebSocket 제어, 가격 조회 등 주요 기능을 CLI로 제공합니다.

Important: 이 문서는 src/prompt 폴더의 직접 포함 파일만 다루며, prompt_main의 메뉴 흐름·사용법·주의사항을 상세히 기술합니다. 검색 결과는 도구 제한으로 일부 항목이 누락될 수 있으니 전체 파일 목록은 GitHub에서 확인하세요:
https://github.com/JUN-JONG-IL/upbit-trader-master/tree/main/src/prompt

FILES
- prompt_main.py
  - Purpose: 콘솔 메뉴 루프, 각 메뉴 항목별 기능(전체가격, 개별가격, 보유목록, 전략 테스트, WS 제어)을 제공. 비동기/동기 함수를 혼합 사용하여 로컬 개발·운영 시 빠른 검사 도구로 사용.
  - Usage:
    - python -c "from src.prompt.prompt_main import prompt_main; prompt_main()"
  - Cautions: 터미널 환경 의존성(msvcrt/termios 등). GUI와 동시에 실행하는 경우 공유 전역(static.chart 등)의 상태 동기화를 주의하세요.

- __init__.py
  - Purpose: prompt 패키지 진입점으로 prompt_main을 내보냅니다.
  - Usage: from src.prompt import prompt_main
  - Cautions: CLI는 GUI와 동일한 프로세스에서 실행할 때 동시성/경쟁 상태를 유발할 수 있으므로 주의하세요.

AUTHOR / CONTACT
- 작성자: Copilot (자동 생성 규칙에 따름)
- Last Modified: 2026-01-31

--------------------------------------------------------------------------------
다음 제안: 주세요.
