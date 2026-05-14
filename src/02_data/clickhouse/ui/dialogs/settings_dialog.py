#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ClickHouse 연결 설정 다이얼로그"""

import os
import logging
from typing import Dict, Any, Optional

try:
    from PyQt5.QtWidgets import QDialog, QMessageBox
    from PyQt5.QtCore import Qt
    from PyQt5 import uic
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

logger = logging.getLogger(__name__)

_UI_FILE = os.path.join(os.path.dirname(__file__), "settings_dialog.ui")

# 기본 연결 파라미터
_DEFAULTS: Dict[str, Any] = {
    "host": "localhost",
    "port": 8123,
    "database": "default",
    "user": "default",
    "password": "",
}


class ClickHouseSettingsDialog(QDialog if _HAS_QT else object):
    """ClickHouse 연결 파라미터를 입력받는 설정 다이얼로그.

    호스트, HTTP 포트, 데이터베이스, 사용자, 비밀번호를 입력받으며
    확인 버튼 클릭 시 입력값을 검증한 후 다이얼로그를 닫습니다.
    """

    def __init__(self, params: Optional[Dict[str, Any]] = None, parent=None):
        """초기화.

        Args:
            params: 초기 연결 파라미터 딕셔너리 (선택).
                    None이면 기본값을 사용합니다.
                    키: host, port, database, user, password
            parent: 부모 위젯 (선택)
        """
        if not _HAS_QT:
            return
        super().__init__(parent)
        uic.loadUi(_UI_FILE, self)
        self._setup_connections()
        if params:
            self._load_params(params)

    def _setup_connections(self):
        """버튼 시그널을 슬롯에 연결합니다."""
        self.btn_ok.clicked.connect(self._on_ok)
        self.btn_cancel.clicked.connect(self.reject)

    def _load_params(self, params: Dict[str, Any]) -> None:
        """딕셔너리에서 UI 위젯으로 파라미터를 불러옵니다.

        Args:
            params: 연결 파라미터 딕셔너리
        """
        if "host" in params:
            self.edit_host.setText(str(params["host"]))
        if "port" in params:
            self.spin_port.setValue(int(params["port"]))
        if "database" in params:
            self.edit_database.setText(str(params["database"]))
        if "user" in params:
            self.edit_user.setText(str(params["user"]))
        if "password" in params:
            self.edit_password.setText(str(params["password"]))

    def _on_ok(self) -> None:
        """확인 버튼 클릭 핸들러. 입력값을 검증한 후 다이얼로그를 수락합니다."""
        host = self.edit_host.text().strip()
        if not host:
            QMessageBox.warning(self, "입력 오류", "호스트를 입력해 주세요.")
            self.edit_host.setFocus()
            return
        database = self.edit_database.text().strip()
        if not database:
            QMessageBox.warning(self, "입력 오류", "데이터베이스를 입력해 주세요.")
            self.edit_database.setFocus()
            return
        self.accept()

    def get_params(self) -> Dict[str, Any]:
        """현재 입력된 연결 파라미터를 딕셔너리로 반환합니다.

        다이얼로그가 수락(accepted)된 후에 호출해야 올바른 값을 얻을 수 있습니다.

        Returns:
            다음 키를 포함하는 딕셔너리:
            - host (str): 서버 호스트명
            - port (int): HTTP 포트 번호
            - database (str): 데이터베이스 이름
            - user (str): 사용자 이름
            - password (str): 비밀번호 (평문)
        """
        if not _HAS_QT:
            return dict(_DEFAULTS)
        return {
            "host": self.edit_host.text().strip() or _DEFAULTS["host"],
            "port": self.spin_port.value(),
            "database": self.edit_database.text().strip() or _DEFAULTS["database"],
            "user": self.edit_user.text().strip() or _DEFAULTS["user"],
            "password": self.edit_password.text(),
        }

    @classmethod
    def get_connection_params(
        cls,
        params: Optional[Dict[str, Any]] = None,
        parent=None,
    ) -> Optional[Dict[str, Any]]:
        """다이얼로그를 열어 연결 파라미터를 반환하는 클래스 메서드.

        사용자가 취소하면 None을 반환합니다.

        Args:
            params: 초기 연결 파라미터 딕셔너리 (선택)
            parent: 부모 위젯 (선택)

        Returns:
            연결 파라미터 딕셔너리 또는 None (취소 시)
        """
        if not _HAS_QT:
            return None
        dialog = cls(params=params, parent=parent)
        if dialog.exec_() == QDialog.Accepted:
            return dialog.get_params()
        return None
