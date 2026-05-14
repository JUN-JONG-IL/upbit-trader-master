# UI 컴포넌트 (portfolio/ui)

## 개요

`ui/` 패키지는 PyQt5 기반 포트폴리오 및 보유 목록 UI 위젯을 포함합니다.

---

## 파일 구조

| 파일 | 설명 |
|------|------|
| `widget_portfolio.py` | 포트폴리오 메인 위젯 |
| `widget_holding_list.py` | 보유 목록 위젯 |
| `holding_list.ui` | 보유 목록 위젯 UI 파일 |
| `widget_detail_holding.py` | 보유 상세 정보 위젯 |
| `detail_holding_list.ui` | 보유 상세 목록 UI 파일 |
| `detailholdinglist.ui` | 보유 상세 목록 레거시 UI 파일 |

---

## 주의사항

- `.ui` 파일은 Qt Designer로 생성된 파일로, **직접 수정 금지**
- 각 `.py` 파일은 대응되는 `.ui` 파일을 로드하여 컨트롤러 역할 수행
