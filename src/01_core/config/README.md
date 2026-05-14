# config 폴더

## 목적
앱 전역 환경설정과 연결된 파일/코드(loading, 저장, 구조화, 보안 포함)를
중앙화 관리하는 폴더입니다.

---

## 역할
- 환경설정 스키마/입출력 관리 (`config.py`)
- 모든 설정값 보관 및 yaml ↔ 객체 변환
- QSettings(윈도우 레지스트리 포함) 활용한 GUI/실행환경 상태 복원
- 보안 키 관리/마스킹(확장 예정)
- 운영 환경별 자동 경로 판단 지원

---

## 주요파일-기능
- `config.py`  
  통합 Config 클래스, 주요 설정의 in/out, QSettings 포함  
- `config.yaml`
  사용자 환경에 맞춘 실제 실행 설정 (자동 동기화/입출력)
- (예시 템플릿이나 기타 보조 파일은 필요시만 추가...)

---

## 동작 예시 및 전체 구조(관계도)

```mermaid
flowchart LR
    subgraph config[config/]
      configpy(config.py)
      configyaml(config.yaml)
      configinit(__init__.py)
    end
    appmain[app/main.py] --> configpy
    chartwidget[chart/widget_chart.py] --> configpy
    "etc..." --> configpy
    configpy <--> configyaml
    configpy <--> configinit
```
---

## 주요 경로/참조
- 모든 경로 참조/로드는 `utils.get_file_path()` 표준 함수로 처리
- 절대경로/상대경로 병행 지원

---

## 기타
- 설정 파일 포맷, 보안 정책 변경은 Owner 승인 필수
- 저장/로드 로직 및 키 관리 관련 문의: config.py 내 Docstring 참고