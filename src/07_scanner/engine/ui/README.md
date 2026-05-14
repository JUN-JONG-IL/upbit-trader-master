# UI 컴포넌트 (scanner/ui)

## 개요

`ui/` 패키지는 PyQt5 기반 스캐너 UI 위젯을 포함합니다.

---

## 파일 구조

| 파일 | 설명 |
|------|------|
| `widget_scanner_frame.py` | 메인 스캐너 프레임 위젯 |
| `widget_scanner_frame.ui` | 메인 위젯 UI 파일 |
| `popup_scanner_settings.py` | 스캐너 기본 설정 팝업 |
| `popup_scanner_settings.ui` | 기본 설정 팝업 UI 파일 |
| `scanner_settings_advanced_popup.py` | 고급 설정 팝업 |
| `scanner_settings_advanced_popup.ui` | 고급 설정 팝업 UI 파일 |
| `tab_filters.ui` | 필터 탭 UI |
| `tab_basic_indicators.ui` | 기본 지표 탭 UI |
| `tab_advanced_indicators.ui` | 고급 지표 탭 UI |
| `tab_patterns_volume.ui` | 패턴/거래량 탭 UI |
| `tab_alerts_presets.ui` | 알림/프리셋 탭 UI |

---

## 주의사항

- `.ui` 파일은 Qt Designer로 생성된 파일로, **직접 수정 금지**
- 각 `.py` 파일은 대응되는 `.ui` 파일을 로드하여 컨트롤러 역할 수행
