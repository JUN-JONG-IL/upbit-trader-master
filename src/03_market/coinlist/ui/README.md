# UI 컴포넌트 (market/ui)

## 개요

`ui/` 패키지는 PyQt5 기반 코인 목록 및 마켓 데이터 표시 UI 위젯을 포함합니다.

---

## 파일 구조

| 파일 | 설명 |
|------|------|
| `widget_coin_list.py` | 코인 목록 위젯 |
| `coin_list.ui` | 코인 목록 위젯 UI 파일 |
| `widget_favorite.py` | 즐겨찾기 위젯 |
| `favorite.ui` | 즐겨찾기 위젯 UI 파일 |
| `widget_time_settings.py` | 시간 설정 위젯 |
| `time_settings.ui` | 시간 설정 위젯 UI 파일 |

---

## 주의사항

- `.ui` 파일은 Qt Designer로 생성된 파일로, **직접 수정 금지**
- 각 `.py` 파일은 대응되는 `.ui` 파일을 로드하여 컨트롤러 역할 수행
