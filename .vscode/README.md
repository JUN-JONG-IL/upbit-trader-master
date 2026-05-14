# README: .vscode
CHANGELOG:
- 2026-01-31 | Copilot | 생성: .vscode 폴더용 README.md 작성. 영향: 문서화(.vscode/launch.json, .vscode/settings.json). 테스트: 수동 검토.

Version: v1.0
Last Modified: 2026-01-31 | Author: Copilot
References:
 - work_order/README_작성_가이드.md
 - work_order/규칙.md

Purpose:
이 폴더는 Visual Studio Code(이하 VSCode) 작업환경(런치/디버거 설정, 편집기 설정 추천)을 저장합니다. 프로젝트를 VSCode에서 열었을 때 일관된 디버깅 동작과 편집기 보조 기능을 제공하도록 구성 파일(launch.json, settings.json)을 포함합니다.

Files:
 - launch.json: VSCode Run & Debug 구성(현재 파일을 Python 디버거로 실행하는 설정).
 - settings.json: VSCode 워크스페이스 편집기/환경 설정(기본 Python 인터프리터 경로, 터미널 환경 활성화, 맞춤 철자 검사 단어 목록 등).

Detailed file descriptions (각 파일에 대해 목적/사용법/주의사항을 복사하여 바로 사용할 수 있게 상세히 작성):

1) .vscode/launch.json
 - 목적:
   - VSCode의 Run and Debug에서 "Python 디버거: 현재 파일" 구성으로 현재 열려 있는 Python 파일을 통합 터미널에서 디버깅하도록 설정합니다. 디버거 타입은 debugpy(일반적으로 Microsoft Python extension이 제공)입니다.
 - 사용법 (복사하여 바로 사용 가능):
   - VSCode에서 프로젝트 루트 폴더를 엽니다.
   - 왼쪽 사이드바에서 "Run and Debug"(실행 및 디버그)를 선택합니다.
   - "Python 디버거: 현재 파일" 구성을 선택한 후 디버그 버튼(F5) 또는 "Start Debugging"을 클릭하면 현재 편집 중인 파일(${file})이 통합 터미널에서 실행됩니다.
   - 디버거가 설치되지 않은 경우(환경에 debugpy 필요):
     - 터미널에서: python -m pip install debugpy
     - 또는 프로젝트 가상환경을 활성화한 상태에서 위 명령 실행
 - 주의사항:
   - 이 구성은 "현재 파일"을 직접 실행하는 데 적합합니다. 모듈/패키지 단위 실행(예: python -m package.module)을 원하면 launch.json을 별도 구성으로 추가해야 합니다.
   - 통합 터미널(integratedTerminal)을 사용하므로 사용자의 로컬 셸 환경(가상환경 활성화 스크립트 등)이 영향을 줍니다. 디버깅 전에 올바른 가상환경이 선택되었는지 확인하세요.
   - 디버거가 실패하거나 import 경로 문제가 발생하면 VSCode의 Python extension 설정(Interpreter)과 workspace 경로를 확인하세요.

2) .vscode/settings.json
 - 목적:
   - 해당 워크스페이스에서 권장되는 편집기 설정을 저장합니다. 현재 예제는 로컬 개발환경(로컬 Anaconda 가상환경의 절대 경로)을 기본 Python 인터프리터로 지정하고, 터미널에서 가상환경 자동 활성화를 허용하며, 맞춤 철자 검사 단어 목록을 등록합니다.
 - 사용법 (권장 변경 절차 포함):
   - 기본 동작:
     - VSCode에서 이 레포를 열면 settings.json의 설정들이 워크스페이스 레벨로 적용됩니다.
     - Python 확장 설치 후(권장): VSCode 하단 상태바에서 Python 인터프리터를 선택하여 로컬 환경(.venv 또는 conda env)을 지정하세요.
   - 권장(협업/포팅 관점):
     - 절대 경로("C:\\Users\\...\\python.exe") 대신 프로젝트 내부 가상환경(.venv) 또는 "python.defaultInterpreterPath"를 빈 값으로 두고 개발자별로 선택하도록 권장합니다.
     - 또는 .vscode/settings.json을 커밋에서 제외하고(.gitignore) 대신 .vscode/.vscode-recommended.json(확장 추천) 또는 devcontainer 사용을 고려하세요.
   - 예: 가상환경을 사용한 경우 로컬에서 설정하는 방법
     - python -m venv .venv
     - .venv\\Scripts\\activate (Windows) 또는 source .venv/bin/activate (Unix)
     - VSCode에서 Python: Select Interpreter -> .venv/bin/python 선택
 - 주의사항:
   - 현재 settings.json에 포함된 절대 경로는 개인 로컬 환경에 특화되어 있으며 다른 개발자에게는 올바르지 않거나 보안상 문제가 될 수 있습니다. (경로 자체는 민감 키가 아니지만 개인 시스템 구조 노출 가능)
   - 저장소에 개인화된 인터프리터 경로를 커밋하면 CI/다른 개발자의 환경에 혼란을 줄 수 있으므로, 협업 레포에서는 권장 설정을 문서화하고 개인별 설정은 각자 로컬에서 관리하도록 안내하세요.
   - cSpell.words에 UPBIT_API_KEY, UPBIT_SECRET_KEY 등 키 이름들이 포함되어 있는데, 실제 키 값은 절대 저장하지 마세요. 이 항목은 철자 검사에서 키 이름을 허용하기 위한 것으로 보이며, 민감 정보는 반드시 환경변수나 시크릿 관리에 보관하세요.

Usage (프로젝트에서 VSCode로 작업할 때 권장 절차 — 순서대로)
1. 레포 클론:
   - git clone https://github.com/JUN-JONG-IL/upbit-trader-master.git
2. 가상환경 생성 및 활성화(권장):
   - python -m venv .venv
   - Windows: .venv\Scripts\activate
   - macOS/Linux: source .venv/bin/activate
3. 의존성 설치:
   - pip install -r requirements.txt
   - (dev 의존성) pip install -r requirements-dev.txt
4. VSCode에서 레포 폴더 열기:
   - File -> Open Folder -> upbit-trader-master
5. Python 확장 설치(아직 설치 안 된 경우):
   - 확장: "Python" (ms-python.python)
6. 인터프리터 선택:
   - Command Palette(Ctrl+Shift+P) -> Python: Select Interpreter -> .venv의 python 선택
7. 디버깅:
   - Run and Debug -> "Python 디버거: 현재 파일" 선택 -> Start Debugging(F5)
   - 필요 시 launch.json에 새 구성 추가(예: 모듈 실행, 테스트 러너 등)

Warnings / Locked files:
 - 이 폴더에 STAGE_LOCKED 토큰은 적용되지 않았습니다(문서/규칙과 무관).
 - 중요한 주의사항:
   - .vscode/settings.json에 절대 경로(예: 개인 Anaconda 경로)가 포함되어 있으므로 협업 환경에서는 이 파일을 그대로 커밋/사용하지 않는 것을 권장합니다. 다른 참여자에게 혼란을 줍니다.
   - 민감정보(UPBIT API KEY 등)는 이 폴더의 설정에 포함시키지 마세요. 환경변수 또는 시크릿 스토어(예: GitHub Secrets, OS 키체인)를 사용하세요.
   - 커밋 전에는 settings.json의 개인화된 항목을 제거하거나, 프로젝트 정책(예: .vscode/settings.json은 커밋하지 않음)을 따르세요.

Editor / Debugger recommendations (권장 설정)
 - 필수 확장:
   - ms-python.python (Python support + debugpy)
   - ms-toolsai.jupyter (필요 시)
   - streetsidesoftware.code-spell-checker (cSpell) — repository cSpell.words 사용 시
 - 권장 추가 설정(협업 시):
   - devcontainer 또는 .env 파일 사용하여 통일된 개발환경을 제공
   - .vscode/extensions.json에 권장 확장 목록 추가
 - CI 연동 주의:
   - VSCode 전용 설정은 CI에 영향을 주지 않지만, 디버깅 전용 스크립트나 환경 변수를 사용하는 경우 README나 scripts/에 동작 방법을 문서화하세요.

FAQ (짧고 실무적인 답변)
 - Q: launch.json의 "program": "${file}"를 모듈 모드로 바꾸려면?
   - A: 새 구성에서 "request": "launch", "module": "package.module" 또는 "program": "${workspaceFolder}/run.py" 형태로 추가하세요.
 - Q: settings.json의 인터프리터 경로를 모든 개발자에게 강제하려면?
   - A: 권장하지 않습니다. 대신 devcontainer 또는 마이크로소프트의 "Python: Create Environment" 워크플로를 문서화하여 일관된 방법을 안내하세요.

Next steps — 다음에 작성할 폴더 README.md 제안 (우선순위)
 - 제안 1 (권장 우선순위): scripts/
   - 이유: 본 레포의 자동화·검증 도구들(scripts/doc_check.py, verify_phase2.py 등)이 scripts/에 존재하는 것으로 추정됩니다. 자동화 스크립트는 문서화가 우선되어야 하며, .vscode에서 권장한 워크플로(검증 → 적용)에 직접 연동됩니다.
 - 제안 2: work_order/
   - 이유: 프로젝트 핵심 워크플로와 단계별 가이드(1~23 단계)가 모두 이 폴더에 있고, 각 단계를 문서화/검증하는 README가 중요합니다. 단, 작업량이 큽니다 — 단계별로 나누어(예: work_order/1~6, 7~12 등) 순차 작성 권장.

---

Last Modified: 2026-01-31 | Author: Copilot
