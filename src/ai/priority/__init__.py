"""
src/ai/priority 패키지

우선순위 설정 기능 제공 (우선순위 비즈니스 로직 전담).

하위 패키지:
- config/    : 우선순위·ML 설정 관리
- services/  : 우선순위 점수 계산, DB 서비스
             (MLService → src/ai/ai_engine/ml_service.py 로 이동, shim 유지)
             (UpbitDataProvider → src/data_01/clients/upbit_data_provider.py 로 이동, shim 유지)
- models/    : Gap Predictor, Adaptive TF, Anomaly Detector, Drift Monitor
- controllers/: PyQt5 UI 컨트롤러 (우선순위 설정, ML 모델 선택, 대시보드)
- api/       : FastAPI 라우터 (priority_routes, ml_routes)
- ui/        : .ui 파일 (priority_settings, priority_dashboard)
             (ml_model_selector.ui → src/ai/ui/ai_engine/ 로 이동)

CHANGELOG:
- 2026-03-19 | Copilot | MLService → src/ai/ai_engine/ 으로 이동
              UpbitDataProvider → src/data_01/clients/ 으로 이동
              ml_model_selector.ui → src/ai/ui/ai_engine/ 으로 이동
"""
