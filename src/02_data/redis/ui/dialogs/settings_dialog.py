#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Redis 연결 설정 다이얼로그"""

import os
from typing import Dict, Optional

try:
    from PyQt5.QtWidgets import QDialog
    from PyQt5 import uic
    _HAS_QT = True
    _Base = QDialog
except ImportError:
    _HAS_QT = False
    _Base = object  # type: ignore[assignment,misc]

_UI_PATH = os.path.join(os.path.dirname(__file__), "settings_dialog.ui")


class RedisSettingsDialog(_Base):  # type: ignore[valid-type]
    """Redis 연결 설정을 입력받는 다이얼로그.

    PyQt5가 설치된 환경에서는 settings_dialog.ui를 QDialog로 로드하여
    사용자에게 호스트, 포트, 비밀번호, DB 번호를 입력받습니다.

    Examples:
        dlg = RedisSettingsDialog()
        if dlg.exec_():
            params = dlg.get_params()
    """

    def __init__(self, parent=None) -> None:
        """초기화.

        Args:
            parent: 부모 위젯 (PyQt5 QWidget)
        """
        if not _HAS_QT:
            raise RuntimeError("PyQt5가 설치되어 있지 않습니다.")

        super().__init__(parent)
        # .ui 파일을 self(QDialog)에 직접 로드
        uic.loadUi(_UI_PATH, self)

        # 버튼 연결 (.ui 파일 connections 섹션에서도 처리되지만 명시적으로 등록)
        self.button_ok.clicked.connect(self.accept)
        self.button_cancel.clicked.connect(self.reject)

    # ------------------------------------------------------------------
    # 공개 API
    # ------------------------------------------------------------------

    def exec_(self) -> int:
        """다이얼로그를 모달로 실행합니다.

        Returns:
            QDialog.Accepted(1) 또는 QDialog.Rejected(0)
        """
        return super().exec_()

    def get_params(self) -> Dict:
        """사용자가 입력한 연결 파라미터를 반환합니다.

        Returns:
            host, port, password, db 키를 포함하는 딕셔너리
        """
        password = self.edit_password.text().strip()
        return {
            "host": self.edit_host.text().strip() or "localhost",
            "port": self.spin_port.value(),
            "password": password if password else None,
            "db": self.spin_db.value(),
        }

    def set_params(self, host: str = "localhost", port: int = 6379,
                   password: Optional[str] = None, db: int = 0) -> None:
        """다이얼로그 폼의 초기값을 설정합니다.

        Args:
            host: Redis 호스트명
            port: Redis 포트
            password: 인증 비밀번호 (없으면 None)
            db: 데이터베이스 번호
        """
        self.edit_host.setText(host)
        self.spin_port.setValue(port)
        self.edit_password.setText(password or "")
        self.spin_db.setValue(db)
