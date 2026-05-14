# README: base

CHANGELOG:
- 2026-01-31 | Copilot | 생성: base 폴더 README 작성. 영향: base/Dockerfile 문서화(빌드/보안/운용/권장사항 포함). 테스트: 문서 기반 수동 검토.

Version: v1.0  
Last Modified: 2026-01-31 | Author: Copilot  
References:
 - work_order/README_작성_가이드.md
 - work_order/규칙.md

Purpose:
base 폴더는 컨테이너 이미지 빌드의 기반(Base image) 구성파일(예: Dockerfile)과 관련 리소스를 보관합니다. 이 폴더의 Dockerfile은 프로젝트의 런타임/빌드 환경(시스템 패키지, 파이썬 런타임, 시스템 의존성 등)을 정의하며, 다른 컨테이너/서비스 이미지들이 이 이미지를 기반으로 빌드되도록 설계되어 있습니다. base 이미지는 시스템 레벨 설정(패키지 미러, OS 레벨 도구 설치 등)을 포함하므로 보안·호환성 측면에서 신중한 관리가 필요합니다.

Note: 자동 검색 결과는 일부일 수 있습니다. base 폴더의 최신 파일/변경내역은 GitHub에서 직접 확인하세요:
https://github.com/JUN-JONG-IL/upbit-trader-master/tree/main/base

Files:
 - Dockerfile: base 이미지 정의 (python:3.9.2 기반, 타임존 설정, apt/Pip 미러 설정, LLVM 설치 등)

Detailed file documentation (각 파일별 목적 / 사용법 / 주의사항을 자세히 기술):

1) base/Dockerfile
 - 목적 (한 문장):
   - python:3.9.2 기반의 시스템 레벨 베이스 이미지를 구성하여 프로젝트의 컨테이너 빌드에 일관된 런타임 환경을 제공합니다.
 - 상세 설명 (무엇을/왜 포함하는지):
   - 베이스 이미지로 python:3.9.2를 사용합니다.
   - 시스템 타임존을 Asia/Seoul로 설정합니다(ENV TZ=Asia/Seoul).
   - Debian apt 미러와 pip 인덱스 미러를 로컬/국내 미러(예: mirror.kakao.com, ftp.kaist.ac.kr)로 변경하여 패키지 다운로드 속도를 개선합니다.
   - LLVM(LLVM-10) 관련 패키지를 apt로 설치하고 /usr/bin/llvm-config 심볼릭 링크를 만듭니다.
   - 불필요한 apt 캐시를 제거하여 이미지 크기를 줄입니다.
 - 사용법(복사해서 바로 쓸 수 있는 명령 예제):
   - 로컬에서 빌드:
     - docker build -f base/Dockerfile -t upbit-trader-base:2.0.2 .
   - 캐시 없이 빌드(재현성/디버깅 용):
     - docker build --no-cache -f base/Dockerfile -t upbit-trader-base:latest .
   - 이미지 확인:
     - docker images | grep upbit-trader-base
   - 컨테이너 실행(간단 검사):
     - docker run --rm -it upbit-trader-base:2.0.2 python --version
 - 권장 런타임/배포 옵션:
   - 빌드 시 --pull 옵션으로 베이스 이미지의 최신 패치 버전을 가져오는 것을 권장합니다(단, 재현성 보장이 필요한 경우 특정 태그 고정).
   - production 배포용 이미지는 보안 패치와 최소 설치만 포함하도록 별도의 경량화 스테이지(멀티스테이지 빌드) 사용 권장.
 - 주의사항 / 보안 리스크 (반드시 읽을 것):
   - 사용된 python:3.9.2 이미지는 오래된 버전일 수 있습니다. 보안 패치 및 장기 지원(SLA)을 고려해 주기적으로 베이스 이미지를 업데이트해주세요.
   - Dockerfile 내부에서 apt 미러를 국내 미러(http)로 강제 변경하고 있습니다. HTTP/비신뢰 미러 사용은 중간자 공격(Man-in-the-Middle) 위험을 높일 수 있으므로, 가능한 경우 HTTPS 미러 사용 또는 신뢰 가능한 미러를 선택하세요.
   - `wget --no-check-certificate` 및 apt-key add 사용은 보안 취약점 소지가 있습니다. apt-key는 deprecate 되었으므로 GPG 키를 /etc/apt/trusted.gpg.d 에 안전하게 추가하거나 공식 가이드에 따르세요.
   - pip index-url을 `http://mirror.kakao.com/pypi/simple`로 설정하는 것은 TLS 미사용(http)로 보안상 위험합니다. 패키지 무결성 확인을 위해 HTTPS 및 서명 검증을 권장합니다.
   - 이미지 내부에 개발자 개인 정보(예: 로컬 경로, 키 등)를 하드코딩하지 마십시오.
 - 호환성/의존성 주의:
   - LLVM-10 설치 및 심볼릭 링크 생성은 특정 네이티브 확장 빌드(예: C/C++ 확장, 컴파일러 의존성) 목적입니다. 프로젝트에서 요구하는 LLVM 버전과 맞는지 확인하세요.
   - python 버전/패키지 버전 불일치가 downstream 컨테이너(서비스 이미지)에 영향을 줄 수 있으므로, major 변경 시 changelog·백워드 호환성 테스트를 수행하세요.
 - 테스트(빌드/검증 권장 절차):
   1. docker build -f base/Dockerfile -t upbit-trader-base:test .
   2. docker run --rm upbit-trader-base:test python -c "import sys; print(sys.version)"
   3. 시스템 명령(예: llvm-config --version) 확인: docker run --rm upbit-trader-base:test llvm-config --version
   4. 보안 스캔(권장): trivy 또는 claire 등 도구로 이미지 취약점 스캔 수행
      - 예: trivy image upbit-trader-base:test
   5. linter/Hadolint 검사(권장): hadolint base/Dockerfile
 - 권장 개선 사항 (문서 권고; 코드 변경 시 사용자 승인 필요):
   - apt-key 사용 대신 안전한 GPG 키 처리 방식으로 변경 권장(apt-key deprecation 대응).
   - pip 인덱스는 HTTPS로 설정하거나, 내부 아티팩트 리포지터리(Artifact Registry, Nexus 등) 활용 권장.
   - python:3.9.2 대신 보안패치가 적용된 최신 patch 버전(3.9.x 최신) 또는 장기 지원 버전 사용 고려.
   - 멀티스테이지 빌드 적용으로 빌드 툴/컴파일러는 빌드 스테이지에만 포함하고 런타임 이미지에서는 제거하여 크기 최소화.
 - 운영/배포시 체크리스트:
   - 베이스 이미지 빌드 로그 확인(apt 설치 실패, wget 실패 등).
   - 빌드된 이미지를 취약점 스캐너로 검사.
   - 베이스 이미지 변경 시 downstream 서비스(특히 C-확장 빌드 및 컴파일 플래그)에 영향 여부 확인.
   - 베이스 이미지에 변경이 필요하면 work/branch 규칙 및 docs/previous_stages에 변경 기록을 남기고, 변경 전후 롤백 절차 문서화.

CI / Automation integration:
 - CI에서 base 이미지 빌드를 자동화하는 경우:
   - 워크플로 예:
     - job: build-base
       steps:
         - checkout
         - docker build -f base/Dockerfile -t ${REGISTRY}/upbit-trader-base:${GIT_SHA} .
         - trivy image ${REGISTRY}/upbit-trader-base:${GIT_SHA}
         - docker push ${REGISTRY}/upbit-trader-base:${GIT_SHA}
 - 주의: CI에서 외부 미러(http) 접속 시 네트워크 안정성/보안정책(방화벽, 프록시)을 확인해야 합니다.
 - 권장: 빌드 결과물(이미지)은 레지스트리(Private Docker Registry, GitHub Container Registry)로 푸시하고, 이미지 태그에 버전과 커밋 SHA를 포함하여 재현 가능성 보장.

Troubleshooting (자주 발생하는 문제 및 해결안):
 - 문제: apt update/apt install 중 특정 패키지 다운로드 실패
   - 원인/해결:
     - 미러 불안정 또는 미러 주소 변경(블록) 가능. 공식 deb.debian.org로 복원하거나 다른 신뢰 가능한 미러로 전환하세요.
     - 네트워크(프록시, 방화벽) 설정 확인.
 - 문제: wget --no-check-certificate로 키 가져오기 실패
   - 원인/해결:
     - 네트워크 정책/서버 인증서 문제. 가능한 경우 HTTPS + 검증을 사용하거나 운영 정책에 맞는 키 배포 방식으로 전환하세요.
 - 문제: llvm-config 심볼릭 링크가 존재하지 않음
   - 원인/해결:
     - 설치된 LLVM 버전이 다르거나 패키지 네이밍이 다른 경우 apt 검색 결과 및 설치 로그 확인 후 링크 대상 경로를 조정하세요.

Maintenance (유지보수 권고 절차):
 - 베이스 이미지 수정 전:
   1. 변경 이유·영향 요약 문서화
   2. 영향 범위(하위 이미지/서비스) 식별
   3. 테스트 계획(이미지 빌드 → 단순 smoke test → 서비스 테스트)
   4. docs/previous_stages 또는 CHANGELOG에 기록
 - 변경 후:
   - 이미지 태그, 변경 요약, 테스트 결과 업로드 및 관련 PR에 영향 범위 명시
 - 긴급 보안 패치:
   - 베이스 이미지 관련 보안 이슈 발생 시 즉시 패치하고 롤아웃 계획 수립(다운타임 최소화/롤링 배포 권장)

Last Modified: 2026-01-31 | Author: Copilot

Next README.md 제안 (우선순위):
 - 제안 1 (권장): scripts/ — scripts/doc_check.py, verify_phase2.py 등 자동화·검증 스크립트 문서화 우선권. 이유: 문서화 자동화 및 CI 연계에 즉시 영향.
 - 제안 2: work_order/ — 프로젝트 단계별 운영 지침 및 규칙 통합 문서화(규모가 큼: 단계별로 분할 작업 권장).
