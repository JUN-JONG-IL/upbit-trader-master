# 🧪 테스트 자동화 가이드

> **파일**: automation/TEST_GUIDE.md  
> **버전**: v1.0  
> **작성일**: 2026-02-01  
> **작성자**: Copilot  
> **목적**: 테스트 자동화 전략 및 실행 방법 안내

---

## 📌 목차

1. [테스트 자동화 전략](#테스트-자동화-전략)
2. [테스트 종류](#테스트-종류)
3. [테스트 실행 방법](#테스트-실행-방법)
4. [CI/CD 연동](#cicd-연동)
5. [테스트 작성 가이드](#테스트-작성-가이드)
6. [문제 해결](#문제-해결)

---

## 🎯 테스트 자동화 전략

### 테스트 피라미드

```
        ┌─────────────┐
        │    E2E      │  ← 소수 (느리지만 중요)
        │   테스트     │
        ├─────────────┤
        │   통합      │  ← 중간 수
        │   테스트     │
        ├─────────────┤
        │   단위      │  ← 다수 (빠르고 많이)
        │   테스트     │
        └─────────────┘
```

### 테스트 원칙

1. **빠른 피드백**: 코드 변경 후 즉시 테스트 실행
2. **자동화**: 수동 테스트 최소화
3. **독립성**: 각 테스트는 독립적으로 실행 가능
4. **반복 가능**: 같은 입력에 대해 항상 같은 결과
5. **명확한 실패**: 실패 시 원인 명확히 표시

---

## 📋 테스트 종류

### 1️⃣ 문서 검증

**목적**: 문서 표준 준수 확인

**검사 항목**:
- UTF-8 인코딩
- 표준 헤더 존재
- 링크 유효성
- 누락된 README 확인

**실행 방법**:
```bash
# 기본 실행
python scripts/doc_check.py

# 자동 수정 적용
python scripts/doc_check.py --apply

# 테스트 러너 사용
python automation/test_runner.py --doc-only
```

**기대 결과**:
```
✅ work_order/규칙.md - 표준 준수
✅ work_order/통합_개발_가이드.md - 표준 준수
✅ automation/README.md - 표준 준수
```

---

### 2️⃣ 단위 테스트

**목적**: 개별 함수/클래스 동작 확인

**테스트 대상**:
- 개별 함수
- 클래스 메서드
- 유틸리티 함수
- 데이터 변환 로직

**실행 방법**:
```bash
# 전체 단위 테스트
python -m pytest tests/ -v

# 특정 파일만
python -m pytest tests/test_coinlist.py -v

# 특정 테스트만
python -m pytest tests/test_coinlist.py::test_filter -v

# 커버리지 포함
python -m pytest tests/ --cov=src --cov-report=html

# 테스트 러너 사용
python automation/test_runner.py --unit-only
```

**예시 테스트**:
```python
# tests/test_coinlist.py
def test_coin_filter():
    """종목 필터링 테스트"""
    coins = [
        {'symbol': 'KRW-BTC', 'price': 50000000},
        {'symbol': 'KRW-ETH', 'price': 3000000},
        {'symbol': 'KRW-XRP', 'price': 500}
    ]
    
    # 가격 필터
    filtered = filter_by_price(coins, min_price=1000000)
    
    assert len(filtered) == 2
    assert all(c['price'] >= 1000000 for c in filtered)
```

---

### 3️⃣ 통합 테스트

**목적**: 모듈 간 연동 확인

**테스트 대상**:
- 모듈 간 통신
- API 연동
- DB 연동
- WebSocket 연동

**실행 방법**:
```bash
# Phase 2 검증
python verify_phase2.py

# 테스트 러너 사용
python automation/test_runner.py --integration-only
```

**예시 시나리오**:
```
1. CoinList에서 종목 선택
2. UIStateManager에 symbol 설정
3. Chart, Orderbook, Trade 위젯이 자동 갱신
4. 각 위젯의 데이터 일치 확인
```

---

### 4️⃣ 성능 테스트

**목적**: 성능 기준 만족 확인

**성능 기준**:
- P95 지연 < 500ms
- GUI 응답성 < 100ms
- CoinList 갱신 ≤ 10fps
- Orderbook 갱신 ≤ 2fps
- Chart redraw ≤ 2fps

**실행 방법**:
```bash
# 성능 테스트
python automation/test_runner.py --performance

# 프로파일링
python -m cProfile -o output.prof src/main.py
python -m pstats output.prof
```

**예시**:
```python
# tests/test_performance.py
import time

def test_coinlist_update_speed():
    """CoinList 갱신 속도 테스트"""
    start = time.time()
    
    # 1000개 코인 업데이트
    for _ in range(1000):
        update_coin({'symbol': 'KRW-BTC', 'price': 50000000})
    
    elapsed = time.time() - start
    
    # 100ms 이내 (10fps 기준)
    assert elapsed < 0.1, f"너무 느림: {elapsed:.3f}초"
```

---

### 5️⃣ E2E 테스트 (선택)

**목적**: 실제 사용자 시나리오 확인

**테스트 시나리오**:
```
1. 앱 시작
2. 거래소 연결
3. 종목 검색
4. 차트 확인
5. 주문 생성 (PAPER 모드)
6. 주문 취소
7. 앱 종료
```

**도구**:
- pytest-qt (Qt 앱 테스트)
- pytest-mock (모킹)

---

## 🚀 테스트 실행 방법

### 기본 사용법

#### 1. 빠른 테스트 (문서만)

```bash
python automation/test_runner.py --quick
```

**실행 시간**: ~10초  
**용도**: 빠른 피드백, 문서 변경 확인

#### 2. 전체 테스트

```bash
python automation/test_runner.py --all
```

**실행 시간**: ~5분  
**용도**: PR 전, 배포 전 최종 확인

#### 3. 특정 카테고리

```bash
# 문서만
python automation/test_runner.py --doc-only

# 단위 테스트만
python automation/test_runner.py --unit-only

# 통합 테스트만
python automation/test_runner.py --integration-only
```

---

### 고급 사용법

#### 상세 모드

```bash
python automation/test_runner.py --all --verbose
```

**출력**: 전체 로그 표시

#### JSON 출력

```bash
python automation/test_runner.py --all --json
```

**출력**: 프로그래밍 방식 연동용 JSON

#### 병렬 실행

```bash
# pytest 병렬 실행 (pytest-xdist 필요)
python -m pytest tests/ -n auto
```

**주의**: DB/네트워크 테스트는 병렬 실행 주의

---

## 🔄 CI/CD 연동

### GitHub Actions

```yaml
# .github/workflows/test.yml
name: 자동 테스트

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main ]

jobs:
  test:
    runs-on: windows-latest
    
    steps:
      - uses: actions/checkout@v3
      
      - name: Python 설정
        uses: actions/setup-python@v4
        with:
          python-version: '3.11.11'
      
      - name: 의존성 설치
        run: |
          pip install -r requirements.txt
          pip install pytest pytest-cov
      
      - name: 환경 체크
        run: python automation/env_check.py
      
      - name: 문서 검증
        run: python automation/test_runner.py --doc-only
      
      - name: 단위 테스트
        run: python automation/test_runner.py --unit-only
      
      - name: 커버리지 업로드
        uses: codecov/codecov-action@v3
        with:
          file: ./coverage.xml
```

### 로컬 CI 시뮬레이션

```bash
# .env 파일 생성 (CI 환경 시뮬레이션)
cp .env.example .env.ci

# CI 모드로 테스트 실행
python automation/test_runner.py --all --ci-mode
```

---

## 📝 테스트 작성 가이드

### 단위 테스트 작성

#### 기본 구조

```python
# tests/test_module.py
import pytest
from src.module import function_to_test


class TestModuleName:
    """모듈명 테스트"""
    
    def test_basic_functionality(self):
        """기본 기능 테스트"""
        # Given (준비)
        input_data = "test"
        
        # When (실행)
        result = function_to_test(input_data)
        
        # Then (검증)
        assert result == "expected"
    
    def test_edge_case(self):
        """엣지 케이스 테스트"""
        # 빈 입력
        assert function_to_test("") == ""
        
        # None 입력
        assert function_to_test(None) is None
    
    def test_error_handling(self):
        """에러 처리 테스트"""
        with pytest.raises(ValueError):
            function_to_test("invalid")
```

#### 픽스처 사용

```python
# conftest.py (공통 픽스처)
import pytest


@pytest.fixture
def sample_coins():
    """테스트용 코인 데이터"""
    return [
        {'symbol': 'KRW-BTC', 'price': 50000000},
        {'symbol': 'KRW-ETH', 'price': 3000000}
    ]


@pytest.fixture
def mock_api(monkeypatch):
    """API 모킹"""
    def mock_get(*args, **kwargs):
        return {'data': 'mocked'}
    
    monkeypatch.setattr('requests.get', mock_get)
```

#### 파라미터화 테스트

```python
@pytest.mark.parametrize('input,expected', [
    ('KRW-BTC', True),
    ('KRW-ETH', True),
    ('INVALID', False),
    ('', False),
    (None, False),
])
def test_validate_symbol(input, expected):
    """심볼 검증 테스트 (여러 케이스)"""
    assert validate_symbol(input) == expected
```

---

### 통합 테스트 작성

```python
# tests/test_integration.py
import pytest
from src.coinlist import CoinList
from src.chart import Chart
from src.uistate import UIStateManager


class TestCoinListChartIntegration:
    """CoinList ↔ Chart 통합 테스트"""
    
    @pytest.fixture
    def setup_widgets(self):
        """위젯 설정"""
        uistate = UIStateManager()
        coinlist = CoinList(uistate)
        chart = Chart(uistate)
        
        return {'uistate': uistate, 'coinlist': coinlist, 'chart': chart}
    
    def test_symbol_change_updates_chart(self, setup_widgets):
        """종목 변경 시 차트 업데이트 확인"""
        # Given
        widgets = setup_widgets
        
        # When
        widgets['uistate'].set_symbol('upbit', 'KRW-BTC')
        
        # Then
        assert widgets['chart'].current_symbol == 'KRW-BTC'
```

---

### 성능 테스트 작성

```python
# tests/test_performance.py
import pytest
import time


class TestPerformance:
    """성능 테스트"""
    
    def test_p95_latency(self):
        """P95 지연 테스트"""
        latencies = []
        
        for _ in range(100):
            start = time.time()
            # 테스트할 함수
            process_data()
            elapsed = time.time() - start
            latencies.append(elapsed)
        
        # P95 계산
        latencies.sort()
        p95 = latencies[94]  # 95번째 값
        
        assert p95 < 0.5, f"P95 지연 초과: {p95:.3f}초"
    
    @pytest.mark.benchmark
    def test_render_speed(self, benchmark):
        """렌더링 속도 벤치마크"""
        result = benchmark(render_chart, data)
        assert result is not None
```

---

## 🔧 문제 해결

### 문제 1: 테스트 타임아웃

**증상**:
```
❌ 테스트 타임아웃 (30초 초과)
```

**해결**:
```bash
# 타임아웃 증가
python -m pytest tests/ --timeout=60

# 느린 테스트 식별
python -m pytest tests/ --durations=10
```

---

### 문제 2: 테스트 의존성 오류

**증상**:
```
ModuleNotFoundError: No module named 'pytest'
```

**해결**:
```bash
# pytest 설치
pip install pytest pytest-cov pytest-qt pytest-mock

# 또는 requirements-dev.txt 사용
pip install -r requirements-dev.txt
```

---

### 문제 3: 환경 차이로 인한 실패

**증상**:
```
❌ 테스트 실패: 로컬에서는 통과, CI에서는 실패
```

**해결**:
```python
# conftest.py에서 환경 통일
import os
import pytest


@pytest.fixture(scope='session', autouse=True)
def setup_test_env():
    """테스트 환경 설정"""
    os.environ['TESTING'] = 'true'
    os.environ['LOG_LEVEL'] = 'ERROR'
```

---

### 문제 4: DB 테스트 충돌

**증상**:
```
❌ DB 연결 실패: 다른 테스트에서 사용 중
```

**해결**:
```python
# 테스트용 DB 사용
import pytest
from sqlalchemy import create_engine


@pytest.fixture
def test_db():
    """테스트용 DB"""
    engine = create_engine('sqlite:///:memory:')
    # 스키마 생성
    create_tables(engine)
    
    yield engine
    
    # 정리
    engine.dispose()
```

---

## 📊 테스트 커버리지

### 커버리지 확인

```bash
# 커버리지 측정
python -m pytest tests/ --cov=src --cov-report=html

# 리포트 확인
open htmlcov/index.html  # macOS/Linux
start htmlcov/index.html  # Windows
```

### 목표 커버리지

- **최소**: 70%
- **권장**: 80%
- **핵심 모듈**: 90% 이상

### 커버리지 개선

```python
# 누락된 부분 확인
python -m pytest tests/ --cov=src --cov-report=term-missing

# 특정 라인 표시
# coverage.py 사용
```

---

## 🎯 요약

### 테스트 실행 순서

1. **환경 체크**: `python automation/env_check.py`
2. **빠른 테스트**: `python automation/test_runner.py --quick`
3. **전체 테스트**: `python automation/test_runner.py --all`
4. **커버리지 확인**: `pytest --cov`

### 권장 워크플로우

```
코드 작성
   ↓
단위 테스트 작성
   ↓
단위 테스트 실행 (빠른 피드백)
   ↓
코드 수정
   ↓
전체 테스트 실행
   ↓
커버리지 확인
   ↓
PR 생성
```

---

**작성자**: Copilot  
**작성일**: 2026-02-01  
**버전**: v1.0

---

**END OF DOCUMENT**
