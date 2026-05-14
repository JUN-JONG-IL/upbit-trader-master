#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
[Purpose]
- CoinlistWidget에서 사용하는 시간/임계값 설정 다이얼로그.

[UI Binding]
- src/03_market/coinlist/ui/time_settings.ui
"""
from __future__ import annotations

import os

from PyQt5 import uic
from PyQt5.QtWidgets import QDialog


def _ui_file_path(filename: str) -> str:
    return os.path.join(os.path.dirname(__file__), filename)


class TimeSettingsDialog(QDialog):
    def __init__(
        self,
        parent=None,
        rate_calc=0,
        trade_calc=0,
        trade_reset=0,
        rate_rise=5.0,
        rate_fall=-5.0,
        trade_rise=10.0,
        trade_fall=-10.0,
    ):
        super().__init__(parent)

        uic.loadUi(_ui_file_path("time_settings.ui"), self)

        # 비모달: 메인 조작 가능
        self.setModal(False)

        # 초기값 설정 (ms 단위)
        self.spin_rate_calc_h.setValue(rate_calc // 3600000)
        self.spin_rate_calc_m.setValue((rate_calc % 3600000) // 60000)
        self.spin_rate_calc_s.setValue((rate_calc % 60000) // 1000)
        self.spin_rate_calc_ms.setValue(rate_calc % 1000)

        self.spin_trade_calc_h.setValue(trade_calc // 3600000)
        self.spin_trade_calc_m.setValue((trade_calc % 3600000) // 60000)
        self.spin_trade_calc_s.setValue((trade_calc % 60000) // 1000)
        self.spin_trade_calc_ms.setValue(trade_calc % 1000)

        self.spin_trade_reset_h.setValue(trade_reset // 3600000)
        self.spin_trade_reset_m.setValue((trade_reset % 3600000) // 60000)
        self.spin_trade_reset_s.setValue((trade_reset % 60000) // 1000)
        self.spin_trade_reset_ms.setValue(trade_reset % 1000)

        self.spin_rate_rise_threshold.setValue(rate_rise)
        self.spin_rate_fall_threshold.setValue(rate_fall)
        self.spin_trade_rise_threshold.setValue(trade_rise)
        self.spin_trade_fall_threshold.setValue(trade_fall)

        # buttons
        self.btn_ok.clicked.connect(self.accept)
        if hasattr(self, "btn_cancel"):
            self.btn_cancel.clicked.connect(self.reject)