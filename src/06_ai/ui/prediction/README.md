# UI 컴포넌트 (prediction/ui)

## 개요

`ui/` 패키지는 PyQt5 기반 가격 예측 결과 표시 UI 위젯을 포함합니다.

---

## 파일 구조

| 파일 | 설명 |
|------|------|
| `widget_prediction.py` | 예측 결과 위젯 |
| `prediction.ui` | 예측 결과 위젯 UI 파일 |

---

## 주의사항

- `.ui` 파일은 Qt Designer로 생성된 파일로, **직접 수정 금지**
- 각 `.py` 파일은 대응되는 `.ui` 파일을 로드하여 컨트롤러 역할 수행
