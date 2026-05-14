# automation 폴더

> **목적**: 완전 자동화 시스템 제공  
> **버전**: v2.0  
> **작성일**: 2026-02-03  
> **작성자**: Copilot

---

## 📌 개요

automation 폴더는 개발 작업을 자동화하는 핵심 도구들을 제공합니다.  
초보자도 "N단계 시작"이라는 한 마디로 모든 작업을 자동으로 완료할 수 있도록 설계되었습니다.

### 핵심 철학

1. **단순함**: 복잡한 명령어 제거, 간단한 한 문장으로 작업 요청
2. **자동화**: 사용자 개입 최소화, Copilot이 모든 작업 자동 수행
3. **안전성**: 기존 코드 수정 금지, 신규 파일만 생성
4. **검증**: 자동 테스트 및 문서 검증으로 품질 보장

---

## 📂 파일 목록

### 📖 문서

#### WORKFLOW_COMPLETE_GUIDE.md
- **목적**: 완전 자동화 작업 순서도 및 초보자 가이드
- **대상**: 초보자 및 모든 개발자
- **내용**: 전체 작업 흐름도, N단계 작업 요청 방법, 테스트 방법

#### TEST_GUIDE.md
- **목적**: 테스트 자동화 가이드
- **대상**: 개발자 및 QA
- **내용**: 테스트 자동화 전략, 테스트 종류별 실행 방법, CI/CD 연동

---

### 🔧 핵심 자동화 스크립트

#### env_check.py
**환경 자동 검증**
- Python 3.11.11 버전 확인
- .env 파일 및 필수 키 확인
- Docker 서비스 실행 확인
- MongoDB, Redis, Kafka 연결 테스트
- 포트 충돌 확인

```bash
python automation/env_check.py
python automation/env_check.py --verbose
python automation/env_check.py --json
python automation/env_check.py --fix
```

#### auto_workflow.py
**통합 워크플로우 자동화**
- N단계 작업 자동 실행 (7단계 프로세스)
- 환경 체크 → 문서 읽기 → 코드 스캔 → 작업 → 테스트 → 문서 업데이트

```bash
python automation/auto_workflow.py --stage 2
python automation/auto_workflow.py --stage 2 --dry-run
python automation/auto_workflow.py --stage 2 --auto-approve
```

#### test_runner.py
**테스트 자동 실행**
- 문서/단위/통합 테스트 자동 실행
- 성능 테스트 (P95 < 500ms)
- 테스트 결과 요약 보고

```bash
python automation/test_runner.py --all
python automation/test_runner.py --doc-only
python automation/test_runner.py --unit-only
python automation/test_runner.py --performance
```

#### doc_updater.py
**문서 자동 업데이트**
- CHANGELOG.md 자동 업데이트
- README.md 자동 생성/업데이트
- 단계 문서 완료 표시

```bash
python automation/doc_updater.py --stage 2 --summary "환경 구축 완료"
python automation/doc_updater.py --folder src/coinlist
python automation/doc_updater.py --all-folders
```

---

### 🆕 신규 자동화 도구 (v2.0)

#### error_predictor.py
**AI 기반 에러 예측 및 예방**
- 과거 로그 분석으로 잠재적 오류 예측
- ML 모델 (scikit-learn) 사용
- 에러 발생 시 자동 롤백 (Git)
- 패턴 기반 오류 탐지

```bash
python automation/error_predictor.py --analyze
python automation/error_predictor.py --predict
python automation/error_predictor.py --auto-rollback
```

#### monitoring_dashboard.py
**실시간 모니터링 대시보드**
- 시스템 상태 실시간 모니터링 (CPU, 메모리, 디스크)
- 웹 대시보드 (Flask)
- 성능 메트릭 시각화
- 알림 시스템

```bash
python automation/monitoring_dashboard.py
python automation/monitoring_dashboard.py --watch
python automation/monitoring_dashboard.py --web --port 5000
```

#### test_framework.py
**테스트 프레임워크 업그레이드**
- pytest 통합 (단위/통합 테스트)
- 커버리지 리포트 자동 생성 (80% 미만 시 중단)
- 백테스팅 자동화 (Backtrader)
- 성능 벤치마크

```bash
python automation/test_framework.py --run-all
python automation/test_framework.py --coverage --min 80
python automation/test_framework.py --backtest
```

#### security_checker.py
**보안 및 컴플라이언스 자동 체크**
- API 키/비밀 관리 자동화
- 하드코딩된 비밀 스캔
- 보안 취약점 스캔 (bandit)
- 암호화폐 거래 규제 준수 체크

```bash
python automation/security_checker.py --scan
python automation/security_checker.py --fix
python automation/security_checker.py --compliance
```

#### docker_automation.py
**Docker 컨테이너화 자동화**
- Dockerfile 자동 생성
- docker-compose.yml 검증
- 이미지 빌드 및 배포 자동화
- Kubernetes 매니페스트 생성

```bash
python automation/docker_automation.py --generate-dockerfile
python automation/docker_automation.py --build
python automation/docker_automation.py --deploy
python automation/docker_automation.py --k8s-manifest
```

#### feedback_collector.py
**사용자 피드백 루프**
- 작업 후 자동 설문/로그 수집
- GitHub Issues 템플릿 생성
- 피드백 분석
- 개선 사항 자동 제안

```bash
python automation/feedback_collector.py --collect --task "자동화 스크립트 실행"
python automation/feedback_collector.py --analyze
python automation/feedback_collector.py --create-issue --title "버그" --description "설명"
```

---

## 🚀 빠른 시작

### 1. 환경 체크

```bash
python automation/env_check.py
```

### 2. 보안 체크

```bash
python automation/security_checker.py --scan
```

### 3. N단계 작업 시작

```bash
python automation/auto_workflow.py --stage 2
```

### 4. 모니터링

```bash
python automation/monitoring_dashboard.py --watch
```

---

## 📖 전체 문서

상세한 자동화 기능 목록은 다음 문서를 참조하세요:
- **[docs/automation_full_features.md](../docs/automation_full_features.md)** - 전체 자동화 기능 상세 설명

---

## 🔄 워크플로우

### N단계 작업 전체 프로세스

```bash
# 1. 환경 체크
python automation/env_check.py --verbose

# 2. 보안 체크
python automation/security_checker.py --scan

# 3. 백업 생성
python ../scripts/backup_manager.py --full

# 4. N단계 작업 실행
python automation/auto_workflow.py --stage N

# 5. 테스트 실행
python automation/test_framework.py --run-all --coverage --min 80

# 6. 문서 업데이트
python automation/doc_updater.py --stage N --summary "N단계 완료"

# 7. 모니터링 확인
python automation/monitoring_dashboard.py

# 8. 피드백 수집
python automation/feedback_collector.py --collect --task "N단계 작업"
```

---

## ⚠️ 주의사항

### 필수 사전 준비

1. **Python 3.11.11 설치**
2. **.env 파일 생성 및 키 입력**
3. **Docker Desktop 실행**
4. **requirements.txt 설치**

### 안전 규칙

1. **기존 코드 수정 금지**: 자동화 도구는 기존 .py, .ui 파일을 수정하지 않습니다
2. **백업 필수**: 중요한 작업 전 백업 생성
3. **드라이런 먼저**: 실제 실행 전 `--dry-run`으로 테스트
4. **단계별 확인**: 각 단계 완료 후 결과 확인

---

## 🔗 관련 문서

### 필수 참조

- [WORKFLOW_COMPLETE_GUIDE.md](./WORKFLOW_COMPLETE_GUIDE.md) - 완전 작업 순서도
- [TEST_GUIDE.md](./TEST_GUIDE.md) - 테스트 자동화 가이드
- [../docs/automation_full_features.md](../docs/automation_full_features.md) - 전체 자동화 기능
- [../work_order/규칙.md](../work_order/규칙.md) - 개발 규칙
- [../work_order/통합_개발_가이드.md](../work_order/통합_개발_가이드.md) - 통합 가이드

---

## 📝 변경 이력

- **2026-02-03**: v2.0 업그레이드
  - 6개 신규 자동화 도구 추가
    - error_predictor.py (AI 기반 에러 예측)
    - monitoring_dashboard.py (실시간 모니터링)
    - test_framework.py (테스트 프레임워크 업그레이드)
    - security_checker.py (보안 체커)
    - docker_automation.py (Docker 자동화)
    - feedback_collector.py (피드백 수집)
  - docs/automation_full_features.md 추가
  - README.md 업데이트
  
- **2026-02-01**: v1.0 초기 생성
  - 기본 자동화 도구 작성
  - WORKFLOW_COMPLETE_GUIDE.md 작성

---

**작성자**: Copilot  
**최종 업데이트**: 2026-02-03  
**버전**: v2.0
