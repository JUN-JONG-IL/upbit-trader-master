#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Help Dialog Widget
도움말 다이얼로그 위젯

모든 기능에 대한 상세 설명을 제공하는 재사용 가능한 도움말 팝업
"""

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QTextEdit, QScrollArea, QWidget
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QIcon


class HelpDialog(QDialog):
    """
    도움말 다이얼로그
    
    기능에 대한 상세 설명, 사용법, 예시를 표시
    """
    
    def __init__(self, title: str, content: str, parent=None):
        """
        Args:
            title: 도움말 제목
            content: 도움말 내용 (HTML 지원)
            parent: 부모 위젯
        """
        super().__init__(parent)
        
        self.setWindowTitle(f"도움말 - {title}")
        self.setModal(True)
        self.resize(600, 500)
        
        # 다크 테마 스타일시트
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e1e;
                color: #ffffff;
            }
            QLabel {
                color: #ffffff;
                font-size: 16pt;
                font-weight: bold;
                padding: 10px;
            }
            QTextEdit {
                background-color: #2d2d2d;
                color: #ffffff;
                border: 1px solid #444444;
                border-radius: 5px;
                padding: 10px;
                font-size: 11pt;
                line-height: 1.5;
            }
            QPushButton {
                background-color: #1976d2;
                color: #ffffff;
                border: none;
                border-radius: 5px;
                padding: 10px 30px;
                font-size: 12pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1565c0;
            }
            QPushButton:pressed {
                background-color: #0d47a1;
            }
        """)
        
        self._init_ui(title, content)
    
    def _init_ui(self, title: str, content: str):
        """UI 초기화"""
        layout = QVBoxLayout(self)
        
        # 제목
        title_label = QLabel(title)
        title_label.setFont(QFont("맑은 고딕", 16, QFont.Bold))
        layout.addWidget(title_label)
        
        # 내용 (스크롤 가능)
        content_text = QTextEdit()
        content_text.setReadOnly(True)
        content_text.setHtml(content)
        layout.addWidget(content_text)
        
        # 닫기 버튼
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        close_button = QPushButton("닫기")
        close_button.clicked.connect(self.accept)
        button_layout.addWidget(close_button)
        
        layout.addLayout(button_layout)


# 사전 정의된 도움말 내용
HELP_CONTENTS = {
    "ai_engine_model_selection": """
        <h2>모델 선택</h2>
        <p>AI 모델을 선택하고 버전을 지정합니다.</p>
        
        <h3>사용법:</h3>
        <ol>
            <li>모델 드롭다운에서 원하는 모델 선택</li>
            <li>버전 선택 (최신 버전 권장)</li>
            <li>모델 설명에서 성능 메트릭 확인</li>
        </ol>
        
        <h3>예시:</h3>
        <ul>
            <li><b>LSTM 모델 v2.1.0</b>: 시계열 예측에 특화, 정확도 92.5%</li>
            <li><b>Transformer 모델 v1.5.0</b>: 장기 의존성 포착, 정확도 94.1%</li>
        </ul>
    """,
    
    "ai_engine_canary_deployment": """
        <h2>카나리 배포</h2>
        <p>새 모델을 점진적으로 배포하여 안전하게 업그레이드합니다.</p>
        
        <h3>배포 단계:</h3>
        <ol>
            <li><b>0% → 5%</b>: 소량 트래픽으로 테스트</li>
            <li><b>5% → 25%</b>: 성능 안정 확인</li>
            <li><b>25% → 50%</b>: 절반 트래픽 전환</li>
            <li><b>50% → 75%</b>: 대부분 트래픽 전환</li>
            <li><b>75% → 100%</b>: 완전 전환</li>
        </ol>
        
        <h3>주의사항:</h3>
        <ul>
            <li>각 단계에서 에러율 모니터링</li>
            <li>에러율 5% 초과 시 자동 롤백</li>
            <li>수동 롤백 버튼 사용 가능</li>
        </ul>
    """,
    
    "ai_engine_drift_detection": """
        <h2>드리프트 감지</h2>
        <p>데이터 분포 변화를 감지하여 모델 성능 저하를 예방합니다.</p>
        
        <h3>감지 방법:</h3>
        <ul>
            <li><b>통계적 검증</b>: Kolmogorov-Smirnov 테스트</li>
            <li><b>성능 모니터링</b>: 정확도 저하 추적</li>
            <li><b>분포 비교</b>: 학습 데이터 vs 실시간 데이터</li>
        </ul>
        
        <h3>대응 방법:</h3>
        <ol>
            <li>드리프트 감지 알림 수신</li>
            <li>재학습 필요 여부 판단</li>
            <li>새 데이터로 모델 재학습</li>
            <li>재배포 및 성능 확인</li>
        </ol>
    """,
    
    "prediction_model_selection": """
        <h2>예측 모델 선택</h2>
        <p>다양한 예측 모델 중 상황에 맞는 모델을 선택합니다.</p>
        
        <h3>모델 종류:</h3>
        <ul>
            <li><b>LSTM</b>: 시계열 패턴 학습, 단기 예측에 강점 (지연: ~100ms)</li>
            <li><b>Transformer</b>: 장기 의존성 포착, 장기 예측에 강점 (지연: ~200ms)</li>
            <li><b>XGBoost</b>: 특징 기반 예측, 빠른 추론 (지연: ~50ms)</li>
            <li><b>Direction Classifier</b>: 상승/하락 방향만 예측 (지연: ~30ms)</li>
            <li><b>Anomaly Detector</b>: 비정상 패턴 감지 (지연: ~80ms)</li>
            <li><b>Meta Ensemble</b>: 여러 모델 결과 통합, 최고 정확도 (지연: ~300ms)</li>
        </ul>
        
        <h3>선택 가이드:</h3>
        <ul>
            <li>단기 예측 (1시간 이내): LSTM 또는 XGBoost</li>
            <li>장기 예측 (1일 이상): Transformer 또는 Meta Ensemble</li>
            <li>방향만 필요: Direction Classifier</li>
            <li>리스크 관리: Anomaly Detector</li>
        </ul>
    """,
    
    "prediction_confidence_interval": """
        <h2>신뢰 구간</h2>
        <p>예측값의 불확실성을 나타내는 범위입니다.</p>
        
        <h3>해석 방법:</h3>
        <ul>
            <li><b>좁은 구간</b>: 예측 신뢰도 높음 (80% 이상)</li>
            <li><b>넓은 구간</b>: 예측 불확실성 높음 (50% 이하)</li>
            <li><b>음영 영역</b>: 68% 신뢰 구간 (1σ)</li>
        </ul>
        
        <h3>활용 방법:</h3>
        <ol>
            <li>신뢰 구간이 좁을 때 거래</li>
            <li>구간이 넓으면 관망</li>
            <li>실제값이 구간 밖이면 모델 재검토</li>
        </ol>
    """,
    
    "prediction_feature_importance": """
        <h2>Feature Importance</h2>
        <p>예측에 가장 영향을 준 특징(Feature)을 보여줍니다.</p>
        
        <h3>주요 특징:</h3>
        <ul>
            <li><b>RSI</b>: 상대강도지수 (과매수/과매도)</li>
            <li><b>거래량</b>: 매수/매도 압력</li>
            <li><b>이동평균</b>: 추세 방향</li>
            <li><b>변동성</b>: 가격 변화 폭</li>
            <li><b>뉴스 감성</b>: 시장 심리</li>
        </ul>
        
        <h3>활용 방법:</h3>
        <ol>
            <li>중요도 높은 특징 모니터링</li>
            <li>특징값 변화 시 예측 재실행</li>
            <li>전략에 중요 특징 반영</li>
        </ol>
    """,
    
    "sentiment_source_selection": """
        <h2>소스 선택</h2>
        <p>감성 분석을 수행할 데이터 소스를 선택합니다.</p>
        
        <h3>소스 종류:</h3>
        <ul>
            <li><b>뉴스</b>: 주요 언론사 기사, 신뢰도 높음</li>
            <li><b>트위터</b>: 실시간 반응, 속보성 높음</li>
            <li><b>레딧</b>: 커뮤니티 토론, 심층 분석</li>
            <li><b>블로그</b>: 전문가 의견, 상세 분석</li>
        </ul>
        
        <h3>선택 가이드:</h3>
        <ul>
            <li>실시간 반응: 트위터</li>
            <li>신뢰도 우선: 뉴스 + 블로그</li>
            <li>종합 분석: 모든 소스 선택</li>
        </ul>
    """,
    
    "sentiment_analysis_result": """
        <h2>감성 분석 결과</h2>
        <p>수집된 데이터의 감성을 긍정/중립/부정으로 분류합니다.</p>
        
        <h3>감성 점수:</h3>
        <ul>
            <li><b>+1.0 ~ +0.3</b>: 긍정 (상승 전망)</li>
            <li><b>+0.3 ~ -0.3</b>: 중립 (관망)</li>
            <li><b>-0.3 ~ -1.0</b>: 부정 (하락 전망)</li>
        </ul>
        
        <h3>해석 방법:</h3>
        <ol>
            <li>긍정 비율 60% 이상: 강한 상승 신호</li>
            <li>부정 비율 60% 이상: 강한 하락 신호</li>
            <li>급격한 감성 변화: 주의 신호</li>
        </ol>
        
        <h3>주의사항:</h3>
        <ul>
            <li>가짜 뉴스 필터링 확인</li>
            <li>인플루언서 가중치 고려</li>
            <li>다른 지표와 종합 판단</li>
        </ul>
    """,
    
    "sentiment_topic_modeling": """
        <h2>토픽 모델링</h2>
        <p>수집된 텍스트에서 주요 주제를 자동 추출합니다.</p>
        
        <h3>알고리즘:</h3>
        <ul>
            <li><b>LDA</b>: Latent Dirichlet Allocation</li>
            <li>자동으로 5개 주요 토픽 추출</li>
            <li>각 토픽의 키워드 표시</li>
        </ul>
        
        <h3>활용 방법:</h3>
        <ol>
            <li>주요 토픽 확인</li>
            <li>관심 토픽의 문서 읽기</li>
            <li>토픽 변화 추이 모니터링</li>
        </ol>
        
        <h3>예시:</h3>
        <ul>
            <li>토픽 1: 가격, 상승, 랠리 → 가격 상승 논의</li>
            <li>토픽 2: 규제, 정책, 법 → 규제 이슈</li>
            <li>토픽 3: 기술, 업그레이드, 개발 → 기술 발전</li>
        </ul>
    """
}


def show_help(topic: str, parent=None):
    """
    도움말 다이얼로그 표시
    
    Args:
        topic: 도움말 주제 키 (HELP_CONTENTS의 키)
        parent: 부모 위젯
    """
    if topic not in HELP_CONTENTS:
        topic = "ai_engine_model_selection"  # 기본값
    
    title = topic.replace("_", " ").title()
    content = HELP_CONTENTS[topic]
    
    dialog = HelpDialog(title, content, parent)
    dialog.exec_()


if __name__ == "__main__":
    """테스트 실행"""
    import sys
    from PyQt5.QtWidgets import QApplication
    
    app = QApplication(sys.argv)
    
    # 테스트: AI 엔진 모델 선택 도움말
    show_help("ai_engine_model_selection")
    
    sys.exit(app.exec_())
