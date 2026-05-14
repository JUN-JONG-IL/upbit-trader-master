"""
src/06_ai/priority ?⑦궎吏

?곗꽑?쒖쐞 ?ㅼ젙 湲곕뒫 ?쒓났 (?곗꽑?쒖쐞 鍮꾩쫰?덉뒪 濡쒖쭅 ?꾨떞).

?섏쐞 ?⑦궎吏:
- config/    : ?곗꽑?쒖쐞쨌ML ?ㅼ젙 愿由?
- services/  : ?곗꽑?쒖쐞 ?먯닔 怨꾩궛, DB ?쒕퉬??
             (MLService ??src/06_ai/ai_engine/ml_service.py 濡??대룞, shim ?좎?)
             (UpbitDataProvider ??src/data_01/clients/upbit_data_provider.py 濡??대룞, shim ?좎?)
- models/    : Gap Predictor, Adaptive TF, Anomaly Detector, Drift Monitor
- controllers/: PyQt5 UI 而⑦듃濡ㅻ윭 (?곗꽑?쒖쐞 ?ㅼ젙, ML 紐⑤뜽 ?좏깮, ??쒕낫??
- api/       : FastAPI ?쇱슦??(priority_routes, ml_routes)
- ui/        : .ui ?뚯씪 (priority_settings, priority_dashboard)
             (ml_model_selector.ui ??src/06_ai/ui/ai_engine/ 濡??대룞)

CHANGELOG:
- 2026-03-19 | Copilot | MLService ??src/06_ai/ai_engine/ ?쇰줈 ?대룞
              UpbitDataProvider ??src/data_01/clients/ ?쇰줈 ?대룞
              ml_model_selector.ui ??src/06_ai/ui/ai_engine/ ?쇰줈 ?대룞
"""

