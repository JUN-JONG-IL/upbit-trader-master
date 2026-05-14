#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
[Purpose]
- 계정 보유 코인 목록과 수익률을 테이블로 표시하는 위젯이다.

[UI Binding]
- src/08_portfolio/holdings/ui/holding_list.ui

CHANGELOG:
- 2026-03-16 | Copilot | import 경로 수정 (static → src.01_core.lib.static)
"""
from __future__ import annotations

import os
import time
import logging
from pathlib import Path

from PyQt5 import QtGui
from PyQt5.QtCore import QThread, pyqtSignal, Qt
from PyQt5.QtWidgets import QWidget, QHeaderView, QTableWidgetItem, QApplication
from PyQt5.QtGui import QFont, QBrush, QColor
from PyQt5 import uic

try:
    from app import static
except (ImportError, Exception):
    static = None  # type: ignore[assignment]

log = logging.getLogger(__name__)


def _ui_file_path(filename: str) -> str:
    """UI 파일 경로 반환 (동일 디렉토리 기준)"""
    return str(Path(__file__).parent / filename)


class HoldingListWorker(QThread):
    """보유 종목 데이터 갱신 워커"""
    dataSent = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.alive = False

    def run(self):
        """0.5초마다 보유 종목 데이터 전송"""
        self.alive = True
        while self.alive:
            time.sleep(0.5)
            try:
                if hasattr(static, 'account') and static.account:
                    self.dataSent.emit(static.account.coins)
            except Exception as e:
                log.warning(f"[HoldingListWorker] 데이터 전송 실패: {e}")

    def close(self):
        """워커 종료"""
        self.alive = False
        self.quit()
        self.wait()


class HoldingListWidget(QWidget):
    """보유 종목 목록 위젯"""
    
    def __init__(self, parent=None):
        super().__init__(parent)

        # UI 로드 (동일 디렉토리 기준)
        ui_path = _ui_file_path("holding_list.ui")
        if not Path(ui_path).exists():
            log.error(f"[HoldingListWidget] UI 파일 없음: {ui_path}")
            raise FileNotFoundError(f"holding_list.ui not found: {ui_path}")
        
        uic.loadUi(ui_path, self)
        log.info(f"[HoldingListWidget] UI 로드 완료: {ui_path}")

        # 테이블 설정
        self.hold_list.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.hold_list.setShowGrid(False)

        # 워커 초기화
        self.hw = HoldingListWorker()
        self.hw.dataSent.connect(self.updateData)

        # 색상 정의
        self.color_red = QBrush(QColor(207, 48, 74))      # 손실 (CF304A)
        self.color_green = QBrush(QColor(2, 192, 118))    # 수익 (02C076)
        self.color_white = QBrush(QColor(255, 255, 255))  # 중립

        self.items = []

    def updateData(self, data):
        """보��� 종목 데이터 업데이트"""
        try:
            if not data:
                return
            
            # 행 개수가 다르면 테이블 재생성
            if self.hold_list.rowCount() != len(data):
                self.hold_list.clearContents()
                self.items = []
                count_codes = len(data)
                self.hold_list.setRowCount(count_codes)

                font = QFont()
                font.setBold(True)
                
                for i in range(count_codes):
                    item_name = QTableWidgetItem()
                    item_yield = QTableWidgetItem()
                    
                    item_name.setFont(font)
                    item_name.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                    
                    item_yield.setFont(font)
                    item_yield.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    
                    self.items.append([item_name, item_yield])
                    self.hold_list.setItem(i, 0, item_name)
                    self.hold_list.setItem(i, 1, item_yield)

            # 데이터 업데이트
            for i, coin in enumerate(data):
                # 코인 이름 가져오기
                try:
                    if hasattr(static, 'chart') and static.chart:
                        coin_obj = static.chart.get_coin(f"{static.FIAT}-{coin}")
                        korean_name = coin_obj.korean_name if coin_obj else coin
                    else:
                        korean_name = coin
                except Exception:
                    korean_name = coin
                
                self.items[i][0].setText(f"{korean_name}({coin})")
                
                # 수익률 표시
                yield_val = data[coin].get('yield', 0.0)
                self.items[i][1].setText(f"{yield_val:,.2f} %")
                
                # 수익률에 따른 색상 적용
                if yield_val < 0:
                    self.items[i][1].setForeground(self.color_red)
                elif yield_val > 0:
                    self.items[i][1].setForeground(self.color_green)
                else:
                    self.items[i][1].setForeground(self.color_white)

        except Exception as e:
            log.error(f"[HoldingListWidget] updateData 실패: {e}")
            import traceback
            traceback.print_exc()

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        """위젯 종료 시 워커 정리"""
        self.hw.close()
        super().closeEvent(event)


# ✅ 스탠드얼론 테스트 코드
if __name__ == "__main__":
    import sys
    import asyncio as aio
    
    try:
        from src.component import RealtimeManager, Account
        from src.app.lib.config import Config
        from src.utils import set_windows_selector_event_loop_global
        import aiopyupbit
    except ImportError:
        log.warning("[HoldingListWidget] 스탠드얼론 모드 import 실패 (정상 동작은 메인 앱에서 확인)")
        sys.exit(0)

    set_windows_selector_event_loop_global()
    static.config = Config()
    static.config.load()

    loop = aio.new_event_loop()
    aio.set_event_loop(loop)
    codes = loop.run_until_complete(aiopyupbit.get_tickers(fiat=static.FIAT, contain_name=True))
    static.chart = RealtimeManager(codes=codes)
    static.chart.start()

    static.account = Account(
        access_key=static.config.upbit_access_key, 
        secret_key=static.config.upbit_secret_key
    )
    static.account.start()

    app = QApplication(sys.argv)
    GUI = HoldingListWidget()
    GUI.show()
    sys.exit(app.exec_())