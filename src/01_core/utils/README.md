# utils 폴더

## 목적
- 트레이딩 플랫폼 전역에서 반복적으로 사용하는 다양한 **유틸리티 함수/클래스**를 집중 관리

## 포함 기능 (예시)
- 로깅 설정(`get_logger`)
- 리소스/UI/스타일 경로 관리(`get_file_path`, `ui_path`, `style_path`)
- frozen(PyInstaller 빌드) 환경 경로 처리(`_get_src_dir`)
- OS·실행환경별 정책 적용(`set_windows_selector_event_loop_global`, `set_multiprocessing_context`)
- 그 외 데이터 변환/파일 도구 등(추후 helpers 서브 모듈로 확장 가능)

## 구조/참조
- import utils (from utils import get_logger ...) 형태로 일관 호출 권장
- src 내 app/component/chart 등 모든 기능폴더에서 경로 호환됨
- PyInstaller 등 빌드/frozen 환경도 지원

---

## 확장 계획 및 주의사항
- **공통/비즈니스 로직 분리**: 유틸리티성 코드만 보관, 도메인/주문/신호 관련은 별도 모듈로 구분 유지
- 파일 추가·이름변경은 Owner 승인 必