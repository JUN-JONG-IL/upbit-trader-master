# -*- coding: utf-8 -*-
"""
Multi-Chart Dialog - 멀티차트 레이아웃
work_order/규칙.md 준수: UI 파일과 같은 폴더에 배치
"""
import json
from pathlib import Path
from PyQt5.QtWidgets import (
    QWidget, QGridLayout, QMessageBox, QFileDialog, QFrame
)
from PyQt5.QtCore import QThread, pyqtSignal, Qt
from PyQt5.QtGui import QPainter
from PyQt5 import uic


class SyncManager(QThread):
    """
    동기화 관리자 (QThread)
    시간/크로스헤어/줌 동기화
    """
    sync_event = pyqtSignal(dict)
    
    def __init__(self):
        super().__init__()
        self.time_sync_enabled = True
        self.symbol_sync_enabled = False
        self.charts = []
    
    def add_chart(self, chart):
        """차트 추가"""
        if chart not in self.charts:
            self.charts.append(chart)
    
    def remove_chart(self, chart):
        """차트 제거"""
        if chart in self.charts:
            self.charts.remove(chart)
    
    def sync_time(self, start_ts, end_ts, zoom_level):
        """시간 동기화"""
        if not self.time_sync_enabled:
            return
        
        event = {
            'type': 'time_sync',
            'start_ts': start_ts,
            'end_ts': end_ts,
            'zoom_level': zoom_level
        }
        self.sync_event.emit(event)
    
    def sync_symbol(self, symbol):
        """심볼 동기화"""
        if not self.symbol_sync_enabled:
            return
        
        event = {
            'type': 'symbol_sync',
            'symbol': symbol
        }
        self.sync_event.emit(event)
    
    def sync_crosshair(self, x, y, timestamp, price):
        """크로스헤어 동기화"""
        event = {
            'type': 'crosshair_sync',
            'x': x,
            'y': y,
            'timestamp': timestamp,
            'price': price
        }
        self.sync_event.emit(event)


class MultiChartDialog(QWidget):
    """
    멀티차트 레이아웃 다이얼로그
    
    기능:
    - 4~16개 차트 동시 표시
    - 그리드/탭 레이아웃
    - 시간축/줌 동기화
    - 레이아웃 저장/로드 (JSON)
    - 테마 (다크/라이트)
    - 스플릿 뷰
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # UI 로드 (.ui 파일과 같은 폴더에 있음)
        ui_path = Path(__file__).parent / "multi_chart_dialog.ui"
        uic.loadUi(str(ui_path), self)
        
        # 비모달 독립 창 설정 (메인과 동시 조작 가능)
        self.setWindowFlags(self.windowFlags() | Qt.Window)
        
        # 최소 크기 설정 (1000x600px)
        self.gridContainer.setMinimumSize(1000, 600)
        
        # 동기화 관리자
        self.sync_manager = SyncManager()
        self.sync_manager.sync_event.connect(self._on_sync_event)
        
        # 그리드 레이아웃 설정
        self.grid_layout = QGridLayout(self.gridContainer)
        self.grid_layout.setSpacing(2)
        
        # 차트 위젯 목록
        self.chart_widgets = []
        
        # 현재 레이아웃
        self.current_layout = None
        
        # 시그널 연결
        self._connect_signals()
        
        # 초기 레이아웃 로드
        self._load_default_layout()
    
    def _connect_signals(self):
        """시그널 연결"""
        # Layout icon buttons (6 types)
        try:
            self.btn_layout_1x1.clicked.connect(lambda: self.apply_quick_layout("1x1"))
            self.btn_layout_2x1.clicked.connect(lambda: self.apply_quick_layout("2x1"))
            self.btn_layout_1x2.clicked.connect(lambda: self.apply_quick_layout("1x2"))
            self.btn_layout_2x2.clicked.connect(lambda: self.apply_quick_layout("2x2"))
            self.btn_layout_3x2.clicked.connect(lambda: self.apply_quick_layout("3x2"))
            self.btn_layout_4x4.clicked.connect(lambda: self.apply_quick_layout("4x4"))
        except AttributeError:
            pass  # Buttons may not exist in older UI files
        
        # 레이아웃 버튼
        self.btnNewLayout.clicked.connect(self.on_new_layout)
        self.btnLoadLayout.clicked.connect(self.on_load_layout)
        self.btnSaveLayout.clicked.connect(self.on_save_layout)
        
        # 프리셋 선택
        self.comboPresets.currentIndexChanged.connect(self.on_preset_changed)
        
        # 그리드 크기 변경
        self.spinGridCols.valueChanged.connect(self.on_grid_size_changed)
        self.spinGridRows.valueChanged.connect(self.on_grid_size_changed)
        
        # 동기화 설정
        self.chkSyncTime.stateChanged.connect(self.on_sync_time_changed)
        self.chkSyncSymbol.stateChanged.connect(self.on_sync_symbol_changed)
        
        # 테마 변경
        self.comboTheme.currentIndexChanged.connect(self.on_theme_changed)
        
        # 도움말 버튼
        self.btnHelp.clicked.connect(self.on_help_clicked)
    
    def _load_default_layout(self):
        """기본 레이아웃 로드"""
        # Single Chart 프리셋 적용
        self._apply_preset("single_chart")
        self.labelStatus.setText("기본 레이아웃 로드 완료")
    
    def on_new_layout(self):
        """새 레이아웃 생성"""
        # 현재 차트 모두 제거
        self._clear_charts()
        
        # 빈 그리드 생성
        self.labelStatus.setText("새 레이아웃 생성됨")
        self.labelChartCount.setText("차트: 0개")
    
    def on_load_layout(self):
        """레이아웃 불러오기"""
        # 파일 다이얼로그
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "레이아웃 불러오기",
            str(Path.home() / ".config" / "UpbitTrader" / "layouts"),
            "Layout Files (*.json)"
        )
        
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    layout_data = json.load(f)
                
                self._apply_layout(layout_data)
                self.labelStatus.setText(f"레이아웃 로드 완료: {Path(file_path).name}")
            except Exception as e:
                QMessageBox.warning(self, "오류", f"레이아웃 로드 실패:\n{e}")
    
    def on_save_layout(self):
        """레이아웃 저장"""
        # 레이아웃 데이터 생성
        layout_data = self._create_layout_data()
        
        # 파일 다이얼로그
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "레이아웃 저장",
            str(Path.home() / ".config" / "UpbitTrader" / "layouts" / "layout.json"),
            "Layout Files (*.json)"
        )
        
        if file_path:
            try:
                # 디렉토리 생성
                Path(file_path).parent.mkdir(parents=True, exist_ok=True)
                
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(layout_data, f, indent=2, ensure_ascii=False)
                
                self.labelStatus.setText(f"레이아웃 저장 완료: {Path(file_path).name}")
            except Exception as e:
                QMessageBox.warning(self, "오류", f"레이아웃 저장 실패:\n{e}")
    
    def on_preset_changed(self, index):
        """프리셋 변경"""
        if index == 0:  # "프리셋 선택..."
            return
        
        preset_name = self.comboPresets.currentText()
        preset_map = {
            "Single Chart": "single_chart",
            "Dual Timeframe": "dual_timeframe",
            "Quad Chart (2x2)": "quad_chart",
            "Symbol Comparison": "symbol_comparison",
            "Analysis Workspace": "analysis_workspace"
        }
        
        preset_id = preset_map.get(preset_name)
        if preset_id:
            self._apply_preset(preset_id)
    
    def on_grid_size_changed(self):
        """그리드 크기 변경"""
        cols = self.spinGridCols.value()
        rows = self.spinGridRows.value()
        self.labelStatus.setText(f"그리드 크기 변경: {cols}x{rows}")
    
    def on_sync_time_changed(self, state):
        """시간 동기화 설정 변경"""
        self.sync_manager.time_sync_enabled = (state == Qt.Checked)
        status = "활성화" if state == Qt.Checked else "비활성화"
        self.labelStatus.setText(f"시간 동기화 {status}")
    
    def on_sync_symbol_changed(self, state):
        """심볼 동기화 설정 변경"""
        self.sync_manager.symbol_sync_enabled = (state == Qt.Checked)
        status = "활성화" if state == Qt.Checked else "비활성화"
        self.labelStatus.setText(f"심볼 동기화 {status}")
    
    def on_theme_changed(self, index):
        """테마 변경"""
        theme = "dark" if index == 0 else "light"
        self._apply_theme(theme)
        self.labelStatus.setText(f"테마 변경: {theme}")
    
    def on_help_clicked(self):
        """도움말 버튼 클릭"""
        from ui.widgets.help_dialog import HelpDialog
        
        help_content = """
        <h2>멀티차트 레이아웃</h2>
        <p>여러 차트를 동시에 표시하고 동기화할 수 있습니다.</p>
        
        <h3>주요 기능:</h3>
        <ul>
            <li><b>다중 차트</b>: 최대 16개 차트 동시 표시</li>
            <li><b>그리드 레이아웃</b>: 12x6 그리드 기반 배치</li>
            <li><b>시간 동기화</b>: 모든 차트의 시간 범위 동기화</li>
            <li><b>심볼 동기화</b>: 모든 차트에 같은 심볼 적용</li>
            <li><b>레이아웃 저장/불러오기</b>: JSON 형식으로 저장</li>
            <li><b>프리셋</b>: 5가지 사전 정의된 레이아웃</li>
        </ul>
        
        <h3>사용법:</h3>
        <ol>
            <li>프리셋 선택 또는 새 레이아웃 생성</li>
            <li>그리드 크기 조정 (cols x rows)</li>
            <li>동기화 옵션 선택</li>
            <li>레이아웃 저장</li>
        </ol>
        
        <h3>프리셋:</h3>
        <ul>
            <li><b>Single Chart</b>: 전체 화면 단일 차트</li>
            <li><b>Dual Timeframe</b>: 같은 심볼, 다른 타임프레임</li>
            <li><b>Quad Chart</b>: 2x2 그리드, 4개 차트</li>
            <li><b>Symbol Comparison</b>: 여러 심볼 비교</li>
            <li><b>Analysis Workspace</b>: 차트 + 지표 + 도구</li>
        </ul>
        
        <h3>단축키:</h3>
        <ul>
            <li><b>Ctrl+N</b>: 새 레이아웃</li>
            <li><b>Ctrl+O</b>: 레이아웃 불러오기</li>
            <li><b>Ctrl+S</b>: 레이아웃 저장</li>
            <li><b>Ctrl+T</b>: 시간 동기화 토글</li>
        </ul>
        """
        
        dialog = HelpDialog("멀티차트 레이아웃", help_content, self)
        dialog.exec_()
    
    def _apply_preset(self, preset_id):
        """프리셋 적용"""
        from ...presets.chart_presets import ChartPresets
        
        # 프리셋 로드
        try:
            if preset_id == "single_chart":
                layout_data = ChartPresets.single_chart("KRW-BTC")
            elif preset_id == "dual_timeframe":
                layout_data = ChartPresets.dual_timeframe("KRW-BTC")
            elif preset_id == "quad_chart":
                layout_data = ChartPresets.quad_chart("KRW-BTC")
            elif preset_id == "symbol_comparison":
                layout_data = ChartPresets.symbol_comparison(
                    ["KRW-BTC", "KRW-ETH", "KRW-XRP", "KRW-ADA"]
                )
            elif preset_id == "analysis_workspace":
                layout_data = ChartPresets.analysis_workspace("KRW-BTC")
            else:
                layout_data = ChartPresets.single_chart("KRW-BTC")
            
            self._apply_layout(layout_data)
        except Exception as e:
            QMessageBox.warning(self, "오류", f"프리셋 적용 실패:\n{e}")
    
    def _apply_layout(self, layout_data):
        """레이아웃 적용"""
        # 현재 차트 제거
        self._clear_charts()
        
        # 그리드 크기 설정
        grid = layout_data.get('grid', {'cols': 12, 'rows': 6})
        self.spinGridCols.setValue(grid['cols'])
        self.spinGridRows.setValue(grid['rows'])
        
        # 위젯 추가
        widgets = layout_data.get('widgets', [])
        for widget_data in widgets:
            self._add_chart_widget(widget_data)
        
        # 동기화 설정
        sync = layout_data.get('sync', {'time': True, 'symbol': False})
        self.chkSyncTime.setChecked(sync.get('time', True))
        self.chkSyncSymbol.setChecked(sync.get('symbol', False))
        
        # 상태 업데이트
        self.labelChartCount.setText(f"차트: {len(widgets)}개")
        self.current_layout = layout_data
    
    def _add_chart_widget(self, widget_data):
        """차트 위젯 추가"""
        # 차트 위젯 생성 (실제 구현에서는 적절한 차트 위젯 사용)
        chart_widget = QFrame()
        chart_widget.setFrameShape(QFrame.StyledPanel)
        chart_widget.setMinimumSize(200, 150)
        
        # Antialiasing 설정
        if hasattr(chart_widget, 'setRenderHint'):
            chart_widget.setRenderHint(QPainter.Antialiasing)
        
        # 그리드에 추가
        x = widget_data.get('x', 0)
        y = widget_data.get('y', 0)
        w = widget_data.get('w', 12)
        h = widget_data.get('h', 6)
        
        self.grid_layout.addWidget(chart_widget, y, x, h, w)
        self.chart_widgets.append(chart_widget)
        
        # 동기화 관리자에 추가
        self.sync_manager.add_chart(chart_widget)
    
    def _clear_charts(self):
        """모든 차트 제거"""
        for widget in self.chart_widgets:
            self.grid_layout.removeWidget(widget)
            self.sync_manager.remove_chart(widget)
            widget.deleteLater()
        
        self.chart_widgets.clear()
    
    def _create_layout_data(self):
        """레이아웃 데이터 생성"""
        widgets_data = []
        
        # 각 차트 위젯 정보 수집 (실제 구현에서는 차트 설정도 포함)
        for i, widget in enumerate(self.chart_widgets):
            widget_data = {
                'id': f'chart-{i+1}',
                'type': 'candles',
                'symbol': 'KRW-BTC',
                'tf': '1m',
                'x': 0,
                'y': 0,
                'w': 12,
                'h': 6
            }
            widgets_data.append(widget_data)
        
        return {
            'version': '1.0',
            'name': 'custom-layout',
            'grid': {
                'cols': self.spinGridCols.value(),
                'rows': self.spinGridRows.value()
            },
            'widgets': widgets_data,
            'sync': {
                'time': self.chkSyncTime.isChecked(),
                'symbol': self.chkSyncSymbol.isChecked()
            }
        }
    
    def _apply_theme(self, theme):
        """테마 적용"""
        if theme == "dark":
            stylesheet = """
                QWidget {
                    background-color: #1e1e1e;
                    color: #ffffff;
                }
                QPushButton {
                    background-color: #2d2d2d;
                    color: #ffffff;
                    border: 1px solid #444444;
                    padding: 5px 15px;
                    border-radius: 3px;
                }
                QPushButton:hover {
                    background-color: #3d3d3d;
                }
                QFrame {
                    background-color: #2d2d2d;
                    border: 1px solid #444444;
                }
            """
        else:
            stylesheet = """
                QWidget {
                    background-color: #ffffff;
                    color: #000000;
                }
                QPushButton {
                    background-color: #f0f0f0;
                    color: #000000;
                    border: 1px solid #cccccc;
                    padding: 5px 15px;
                    border-radius: 3px;
                }
                QPushButton:hover {
                    background-color: #e0e0e0;
                }
                QFrame {
                    background-color: #f8f8f8;
                    border: 1px solid #cccccc;
                }
            """
        
        self.setStyleSheet(stylesheet)
    
    def _on_sync_event(self, event):
        """동기화 이벤트 처리"""
        event_type = event.get('type')
        
        if event_type == 'time_sync':
            # 모든 차트의 시간 범위 동기화
            pass
        elif event_type == 'symbol_sync':
            # 모든 차트의 심볼 동기화
            pass
        elif event_type == 'crosshair_sync':
            # 모든 차트의 크로스헤어 동기화
            pass
    
    def apply_quick_layout(self, layout_type: str):
        """
        Quick layout application with icon buttons.
        
        Args:
            layout_type: "1x1", "2x1", "1x2", "2x2", "3x2", "4x4"
        """
        try:
            # Define layout configurations
            layouts = {
                "1x1": {"grid": (1, 1), "icon": "⬜"},
                "2x1": {"grid": (2, 1), "icon": "▤"},
                "1x2": {"grid": (1, 2), "icon": "▥"},
                "2x2": {"grid": (2, 2), "icon": "田"},
                "3x2": {"grid": (3, 2), "icon": "⚏"},
                "4x4": {"grid": (4, 4), "icon": "⊞"}
            }
            
            if layout_type not in layouts:
                return
            
            rows, cols = layouts[layout_type]["grid"]
            
            # Clear existing charts
            self._clear_charts()
            
            # Create chart widgets in grid
            from ...ui.widget_chart import ChartWidget
            
            for row in range(rows):
                for col in range(cols):
                    # Create chart widget
                    chart = ChartWidget(parent=self.gridContainer)
                    chart.setMinimumSize(200, 150)
                    
                    # Add to grid
                    self.grid_layout.addWidget(chart, row, col)
                    
                    # Add to sync manager
                    self.sync_manager.add_chart(chart)
                    self.chart_widgets.append(chart)
            
            # Update button colors
            self._update_layout_button_colors(layout_type)
            
            # Update status
            chart_count = rows * cols
            self.labelStatus.setText(f"레이아웃 적용: {layout_type}")
            self.labelChartCount.setText(f"차트: {chart_count}개")
            self.current_layout = layout_type
            
        except Exception as e:
            QMessageBox.warning(self, "오류", f"레이아웃 적용 실패:\n{e}")
    
    def _update_layout_button_colors(self, selected_layout: str):
        """Update layout button colors to highlight the selected layout."""
        try:
            selected_style = "QPushButton { border:1px solid #c8c8c8; background:#3b82f6; color:#ffffff; border-radius:4px; font-size:18px; } QPushButton:hover { background:#2563eb; }"
            unselected_style = "QPushButton { border:1px solid #c8c8c8; background:#2c2c2c; color:#ffffff; border-radius:4px; font-size:18px; } QPushButton:hover { background:#2563eb; }"
            
            layout_buttons = {
                "1x1": getattr(self, "btn_layout_1x1", None),
                "2x1": getattr(self, "btn_layout_2x1", None),
                "1x2": getattr(self, "btn_layout_1x2", None),
                "2x2": getattr(self, "btn_layout_2x2", None),
                "3x2": getattr(self, "btn_layout_3x2", None),
                "4x4": getattr(self, "btn_layout_4x4", None)
            }
            
            for layout_name, button in layout_buttons.items():
                if button:
                    style = selected_style if layout_name == selected_layout else unselected_style
                    button.setStyleSheet(style)
                    
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error updating layout button colors: {e}")


if __name__ == "__main__":
    """테스트 실행"""
    import sys
    from PyQt5.QtWidgets import QApplication
    
    app = QApplication(sys.argv)
    
    dialog = MultiChartDialog()
    dialog.show()
    
    sys.exit(app.exec_())
