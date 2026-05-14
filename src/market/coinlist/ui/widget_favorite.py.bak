#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
[Purpose]
- 관심종목 관리 팝업(QDialog).
- CoinlistWidget에서 favorites를 편집하고, 변경 시 favorites_updated 시그널로 알린다.

[UI Binding]
- src/03_market/coinlist/ui/favorite.ui
"""
from __future__ import annotations

import os
import csv

from PyQt5 import uic
from PyQt5.QtWidgets import QDialog, QTableWidgetItem, QFileDialog
from PyQt5.QtCore import pyqtSignal, QTimer


def _ui_file_path(filename: str) -> str:
    return os.path.join(os.path.dirname(__file__), filename)


class FavoriteWidget(QDialog):
    favorites_updated = pyqtSignal(set)  # 관심종목 업데이트 시그널

    def __init__(self, favorites, all_coins, parent=None):
        super().__init__(parent)

        # 기능 폴더 기준 UI 로드
        uic.loadUi(_ui_file_path("favorite.ui"), self)

        self.setModal(False)  # 팝업 독립 동작
        self.favorites = favorites
        self.all_coins = all_coins
        self.groups = {"고성장": set(), "안정": set()}  # 그룹 예시

        self.btn_add.clicked.connect(self.add_favorite)
        self.btn_remove.clicked.connect(self.remove_favorite)
        self.btn_export.clicked.connect(self.export_csv)
        self.search_fav.textChanged.connect(self.filter_fav_table)
        self.check_real_time.stateChanged.connect(self.toggle_real_time)

        self.real_time_timer = QTimer(self)
        self.real_time_timer.timeout.connect(self.update_fav_table)

        self.update_fav_table()

    def add_favorite(self):
        text = self.search_fav.text()
        for coin in self.all_coins:
            if coin.code[4:] not in self.favorites and (
                text.lower() in coin.korean_name.lower() or text.lower() in coin.english_name.lower()
            ):
                self.favorites.add(coin.code[4:])
                group = self.combo_group.currentText()
                if group != "모든 그룹":
                    self.groups[group].add(coin.code[4:])
                break
        self.update_fav_table()
        self.favorites_updated.emit(self.favorites)

    def remove_favorite(self):
        selected = self.fav_table.selectedItems()
        if selected:
            ticker = self.fav_table.item(selected[0].row(), 0).text().split("\n")[1][4:]
            self.favorites.discard(ticker)
            for group_set in self.groups.values():
                group_set.discard(ticker)
            self.update_fav_table()
            self.favorites_updated.emit(self.favorites)

    def toggle_real_time(self, state):
        if state:
            self.real_time_timer.start(5000)  # 5초마다 업데이트
        else:
            self.real_time_timer.stop()

    def filter_fav_table(self, text):
        group = self.combo_group.currentText()
        for row in range(self.fav_table.rowCount()):
            item = self.fav_table.item(row, 0)
            group_item = self.fav_table.item(row, 3)
            match_text = text.lower() in item.text().lower()
            match_group = group == "모든 그룹" or group_item.text() == group
            self.fav_table.setRowHidden(row, not (match_text and match_group))

    def update_fav_table(self):
        self.fav_table.setRowCount(0)
        for ticker in self.favorites:
            coin = next((c for c in self.all_coins if c.code[4:] == ticker), None)
            if coin:
                row = self.fav_table.rowCount()
                self.fav_table.insertRow(row)
                name_text = f"{coin.korean_name}\nKRW-{ticker}"
                self.fav_table.setItem(row, 0, QTableWidgetItem(name_text))
                self.fav_table.setItem(row, 1, QTableWidgetItem(f"{coin.get_trade_price():,.0f}"))
                self.fav_table.setItem(row, 2, QTableWidgetItem(f"{coin.get_signed_change_rate() * 100:.2f}%"))
                group = next((g for g, s in self.groups.items() if ticker in s), "")
                self.fav_table.setItem(row, 3, QTableWidgetItem(group))

    def export_csv(self):
        path = QFileDialog.getSaveFileName(self, "CSV 저장", "", "CSV (*.csv)")[0]
        if path:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["종목명", "현재가", "등락률", "그룹"])
                for row in range(self.fav_table.rowCount()):
                    if not self.fav_table.isRowHidden(row):
                        writer.writerow([self.fav_table.item(row, col).text() for col in range(4)])

    def closeEvent(self, event):
        self.real_time_timer.stop()
        super().closeEvent(event)