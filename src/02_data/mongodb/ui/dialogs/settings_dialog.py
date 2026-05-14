#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MongoDB 연결 설정 다이얼로그 모듈"""

import os
import logging
from typing import Dict, Any

try:
    from PyQt5.QtWidgets import QDialog
    from PyQt5 import uic
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

logger = logging.getLogger(__name__)

_UI_PATH = os.path.join(os.path.dirname(__file__), "settings_dialog.ui")


class MongoSettingsDialog(QDialog if _HAS_QT else object):
    """MongoDB 연결 설정 다이얼로그.

    호스트, 포트, 데이터베이스, 사용자, 비밀번호를 입력받아
    연결 파라미터를 반환합니다.

    사용 예시::

        dlg = MongoSettingsDialog(parent=self)
        if dlg.exec_() == QDialog.Accepted:
            params = dlg.get_params()
    """

    def __init__(self, parent=None, defaults: Dict[str, Any] = None):
        """초기화.

        Args:
            parent: 부모 위젯.
            defaults: 초기값 딕셔너리.
                      키: host, port, database, user, password.
        """
        if not _HAS_QT:
            return
        super().__init__(parent)
        self._setup_ui()
        if defaults:
            self._apply_defaults(defaults)

    def _setup_ui(self):
        """UI 파일 로드 및 위젯 초기화."""
        uic.loadUi(_UI_PATH, self)

    def _apply_defaults(self, defaults: Dict[str, Any]) -> None:
        """초기값을 폼 위젯에 적용합니다.

        Args:
            defaults: 적용할 기본값 딕셔너리.
        """
        if "host" in defaults:
            self.edit_host.setText(str(defaults["host"]))
        if "port" in defaults:
            self.spin_port.setValue(int(defaults["port"]))
        if "database" in defaults:
            self.edit_database.setText(str(defaults["database"]))
        if "user" in defaults:
            self.edit_user.setText(str(defaults["user"]))
        if "password" in defaults:
            self.edit_password.setText(str(defaults["password"]))

    def get_params(self) -> Dict[str, Any]:
        """현재 폼에 입력된 연결 파라미터를 반환합니다.

        Returns:
            다음 키를 포함하는 딕셔너리:
            - host (str): MongoDB 호스트.
            - port (int): MongoDB 포트.
            - database (str): 데이터베이스 이름.
            - user (str): 사용자 이름 (빈 문자열 가능).
            - password (str): 비밀번호 (빈 문자열 가능).
        """
        if not _HAS_QT:
            return {}
        return {
            "host": self.edit_host.text().strip() or "localhost",
            "port": self.spin_port.value(),
            "database": self.edit_database.text().strip(),
            "user": self.edit_user.text().strip(),
            "password": self.edit_password.text(),
        }

    def get_connection_uri(self) -> str:
        """입력된 파라미터를 MongoDB 연결 URI로 조합하여 반환합니다.

        Returns:
            mongodb://[user:password@]host:port[/database] 형식의 URI.
        """
        params = self.get_params()
        host = params["host"]
        port = params["port"]
        database = params["database"]
        user = params["user"]
        password = params["password"]
        if user and password:
            credentials = f"{user}:{password}@"
        elif user:
            credentials = f"{user}@"
        else:
            credentials = ""
        uri = f"mongodb://{credentials}{host}:{port}"
        if database:
            uri = f"{uri}/{database}"
        return uri
