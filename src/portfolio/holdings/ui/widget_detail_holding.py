# !/usr/bin/python
# -*- coding: utf-8 -*-
"""
[Purpose]
- 계정 보유 코인의 상세 정보를 테이블로 표시한다.

[UI Binding]
- src/portfolio/holdings/ui/detailholdinglist.ui
"""
from __future__ import annotations

import os
import time
import math
import asyncio as aio

from PyQt5 import QtGui
from PyQt5.QtCore import *
from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
from PyQt5 import uic

try:
    from app import static
except ImportError:
    try:
        import importlib as _il
        static = _il.import_module("src.server.app").static  # type: ignore[assignment]
    except Exception:
        static = None  # type: ignore[assignment]


def _ui_file_path(filename: str) -> str:
    return os.path.join(os.path.dirname(__file__), filename)


class DetailholdinglistWorker(QThread):
    dataSent = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.alive = False

    def run(self):
        self.alive = True
        while self.alive:
            time.sleep(0.5)
            self.dataSent.emit(static.account.coins)

    def close(self):
        self.alive = False
        return super().terminate()


class DetailholdinglistWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        # 기능 폴더 기준 UI 로드
        uic.loadUi(_ui_file_path("detailholdinglist.ui"), self)

        self.detailholdinglist.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.detailholdinglist.setShowGrid(False)

        self.color_red = QBrush(QColor(207, 48, 74))  # CF304A
        self.color_green = QBrush(QColor(2, 192, 118))  # 02C076
        self.color_white = QBrush(QColor(255, 255, 255))

        self.dw = DetailholdinglistWorker()
        self.dw.dataSent.connect(self.updateData)

    def updateData(self, data):
        try:
            if self.detailholdinglist.rowCount() != len(data):
                self.detailholdinglist.clearContents()
                self.items = []
                count_codes = len(data)
                self.detailholdinglist.setRowCount(count_codes)

                font = QFont()
                font.setBold(True)
                for i in range(count_codes):
                    self.items.append(
                        [
                            QTableWidgetItem(),
                            QTableWidgetItem(),
                            QTableWidgetItem(),
                            QTableWidgetItem(),
                            QTableWidgetItem(),
                            QTableWidgetItem(),
                        ]
                    )
                    for j in range(6):
                        self.items[i][j].setFont(font)
                        align = Qt.AlignRight | Qt.AlignVCenter
                        if j == 0:
                            align = Qt.AlignLeft | Qt.AlignVCenter
                        self.items[i][j].setTextAlignment(align)
                        self.detailholdinglist.setItem(i, j, self.items[i][j])

            for i, coin in enumerate(data):
                self.items[i][0].setText(
                    static.chart.get_coin(f"{static.FIAT}-{coin}").korean_name + "(" + coin + ")"
                )
                self.items[i][1].setText(f"{data[coin]['balance'] + data[coin]['locked']:,.8f}")
                self.items[i][2].setText(f"{(lambda x: x if x < 100 else math.ceil(x))(data[coin]['avg_buy_price']):,}")
                self.items[i][3].setText(f"{math.ceil(data[coin]['purchase']):,}")
                self.items[i][4].setText(f"{math.floor(data[coin]['evaluate']):,}")
                self.items[i][5].setText(f"{data[coin]['yield']:,.2f}")

                if data[coin]["yield"] < 0:
                    self.items[i][5].setForeground(self.color_red)
                elif data[coin]["yield"] > 0:
                    self.items[i][5].setForeground(self.color_green)
                else:
                    self.items[i][5].setForeground(self.color_white)

        except Exception as e:
            print("Error in updateData:", e)

    def closeEvent(self, a0: QtGui.QCloseEvent) -> None:
        self.dw.close()
        return super().closeEvent(a0)


if __name__ == "__main__":
    import sys
    from component import RealtimeManager, Account
    import aiopyupbit
    from config import Config
    from utils import set_windows_selector_event_loop_global

    set_windows_selector_event_loop_global()
    static.config = Config()
    static.config.load()

    loop = aio.new_event_loop()
    aio.set_event_loop(loop)
    codes = loop.run_until_complete(aiopyupbit.get_tickers(fiat=static.FIAT, contain_name=True))
    static.chart = RealtimeManager(codes=codes)
    static.chart.start()

    static.account = Account(
        access_key=static.config.upbit_access_key, secret_key=static.config.upbit_secret_key
    )
    static.account.start()

    app = QApplication(sys.argv)
    GUI = DetailholdinglistWidget()
    GUI.show()
    sys.exit(app.exec_())