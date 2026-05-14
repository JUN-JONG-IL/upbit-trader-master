#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Kafka 연결 설정 다이얼로그 모듈

사용자로부터 Kafka 브로커 접속 파라미터를 입력받습니다.
"""

import os

try:
    from PyQt5.QtWidgets import QDialog
    from PyQt5 import uic

    _HAS_QT = True
except ImportError:
    _HAS_QT = False


class KafkaSettingsDialog(QDialog if _HAS_QT else object):
    """
    Kafka 연결 설정 다이얼로그

    부트스트랩 서버 주소, 클라이언트 ID, 요청 타임아웃을 입력받고
    확인 시 get_params()로 값을 반환합니다.
    """

    def __init__(self, parent=None, initial_params: dict = None):
        """
        KafkaSettingsDialog 초기화

        Args:
            parent: 부모 위젯 (기본값: None).
            initial_params (dict, optional): 초기값 딕셔너리.
                'bootstrap_servers', 'client_id', 'timeout' 키를 포함할 수 있습니다.
        """
        if not _HAS_QT:
            return
        super().__init__(parent)

        ui_path = os.path.join(os.path.dirname(__file__), "settings_dialog.ui")
        uic.loadUi(ui_path, self)

        if initial_params:
            self._apply_initial_params(initial_params)

        self._connect_signals()

    def _apply_initial_params(self, params: dict):
        """
        다이얼로그 위젯에 초기값을 적용합니다.

        Args:
            params (dict): 초기값 딕셔너리.
        """
        if "bootstrap_servers" in params:
            self.edit_bootstrap_servers.setText(str(params["bootstrap_servers"]))
        if "client_id" in params:
            self.edit_client_id.setText(str(params["client_id"]))
        if "timeout" in params:
            try:
                self.spin_timeout.setValue(int(params["timeout"]))
            except (ValueError, TypeError):
                pass

    def _connect_signals(self):
        """OK/Cancel 버튼 시그널 연결"""
        self.btn_ok.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)

    def get_params(self) -> dict:
        """
        현재 입력된 설정값을 딕셔너리로 반환합니다.

        Returns:
            dict: 다음 키를 포함하는 딕셔너리:
                - 'bootstrap_servers' (str): Kafka 브로커 주소.
                - 'client_id' (str): Kafka 클라이언트 식별자.
                - 'timeout' (int): 요청 타임아웃 (초).
        """
        return {
            "bootstrap_servers": self.edit_bootstrap_servers.text().strip(),
            "client_id": self.edit_client_id.text().strip(),
            "timeout": self.spin_timeout.value(),
        }

    @classmethod
    def get_settings(cls, parent=None, initial_params: dict = None) -> tuple:
        """
        다이얼로그를 실행하고 설정값과 승인 여부를 반환하는 편의 클래스 메서드입니다.

        Args:
            parent: 부모 위젯 (기본값: None).
            initial_params (dict, optional): 초기값 딕셔너리.

        Returns:
            tuple: (params: dict, accepted: bool).
                accepted가 False이면 params는 None입니다.
        """
        dialog = cls(parent=parent, initial_params=initial_params)
        if dialog.exec_() == QDialog.Accepted:
            return dialog.get_params(), True
        return None, False
