#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TimescaleDB 연결 설정 다이얼로그"""

import os
import logging

try:
    from PyQt5.QtWidgets import QDialog
    from PyQt5 import uic
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

logger = logging.getLogger(__name__)

_UI_PATH = os.path.join(os.path.dirname(__file__), "settings_dialog.ui")

# 기본값
_DEFAULT_HOST = "localhost"
_DEFAULT_PORT = 5432
_DEFAULT_DB = "postgres"
_DEFAULT_USER = "postgres"


class TimescaleSettingsDialog(QDialog if _HAS_QT else object):
    """TimescaleDB 연결 설정 다이얼로그.

    호스트, 포트, 데이터베이스, 사용자, 비밀번호를 입력받아
    연결 파라미터 딕셔너리로 반환합니다.

    Example::

        dlg = TimescaleSettingsDialog(parent=self)
        if dlg.exec_() == QDialog.Accepted:
            params = dlg.get_params()
            conn = psycopg2.connect(**params)
    """

    def __init__(self, parent=None, initial_params: dict | None = None):
        """초기화.

        Args:
            parent: 부모 위젯
            initial_params: 초기값 딕셔너리
                {'host': str, 'port': int, 'dbname': str, 'user': str, 'password': str}
        """
        if not _HAS_QT:
            raise RuntimeError("PyQt5가 설치되지 않았습니다.")
        super().__init__(parent)
        uic.loadUi(_UI_PATH, self)
        self._apply_initial(initial_params or {})

    # ------------------------------------------------------------------
    # 공개 인터페이스
    # ------------------------------------------------------------------

    def get_params(self) -> dict:
        """현재 입력값을 psycopg2 connect() 호환 딕셔너리로 반환합니다.

        Returns:
            dict: {'host', 'port', 'dbname', 'user', 'password'} 키를 가진 딕셔너리
        """
        return {
            "host": self.edit_host.text().strip() or _DEFAULT_HOST,
            "port": self.spin_port.value(),
            "dbname": self.edit_database.text().strip() or _DEFAULT_DB,
            "user": self.edit_user.text().strip() or _DEFAULT_USER,
            "password": self.edit_password.text(),
        }

    # ------------------------------------------------------------------
    # 내부 설정
    # ------------------------------------------------------------------

    def _apply_initial(self, params: dict):
        """초기 파라미터를 위젯에 적용합니다.

        Args:
            params: 초기값 딕셔너리
        """
        self.edit_host.setText(str(params.get("host", _DEFAULT_HOST)))
        port = params.get("port", _DEFAULT_PORT)
        try:
            self.spin_port.setValue(int(port))
        except (ValueError, TypeError):
            self.spin_port.setValue(_DEFAULT_PORT)
        self.edit_database.setText(str(params.get("dbname", _DEFAULT_DB)))
        self.edit_user.setText(str(params.get("user", _DEFAULT_USER)))
        self.edit_password.setText(str(params.get("password", "")))
