#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
서버 설정 위젯 (기본 구현 포함)

설명:
- 외부(레포트의 다른 위치)에 이미 구현된 ServerSettingsWidget/SettingsWidget이 있다면 우선 사용합니다.
- 외부 구현이 없거나, 외부 구현이 단순 placeholder인 경우(클래스명이 Placeholder_로 시작)
  이 파일의 기본 GUI 기반 SettingsWidget을 사용합니다.
- pymongo가 설치되어 있으면 "ui_settings" 컬렉션에 간단한 저장/불러오기(upsert)를 시도합니다.
  (모든 DB 작업은 버튼 클릭 시 지연 로드됩니다. 모듈 import 시 DB 접속하지 않음.)
- 모든 주석은 한글로 작성되어 있습니다.
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import os
from typing import Optional, Any

log = logging.getLogger(__name__)

# 먼저 후보 모듈들에서 구현을 찾으려 시도합니다.
_candidate_modules = (
    "server.ui.settings.widget_server_settings",
    "src.server.ui.settings.widget_server_settings",
    "server.ui.settings.widget_settings",
    "src.server.ui.settings.widget_settings",
)

ServerSettingsWidget: Optional[Any] = None

# 1) 후보 네임스페이스에서 직접 가져오기
for mod_name in _candidate_modules:
    try:
        mod = importlib.import_module(mod_name)
        cand = getattr(mod, "ServerSettingsWidget", None) or getattr(mod, "SettingsWidget", None)
        if cand:
            # 외부 구현이 placeholder인지 간단히 체크: 클래스명이 Placeholder_로 시작하면 무시
            try:
                name = getattr(cand, "__name__", "") or str(cand)
                if isinstance(name, str) and name.startswith("Placeholder_"):
                    log.debug("[widget_settings] 후보가 placeholder여서 내부 구현 사용 예정: %s", mod_name)
                else:
                    ServerSettingsWidget = cand
                    log.debug("[widget_settings] Loaded Settings widget from %s", mod_name)
                    break
            except Exception:
                # 안전하게 사용
                ServerSettingsWidget = cand
                log.debug("[widget_settings] Loaded Settings widget from %s", mod_name)
                break
    except Exception:
        continue

# 2) (후보가 없으면) 파일 기반 fallback 탐색은 최대한 안전하게 처리
if ServerSettingsWidget is None:
    # 현재 파일 경로와 주변 후보 위치 검사 (하지만 자기 자신을 재귀 로드하지 않음)
    here = os.path.dirname(os.path.abspath(__file__))
    repo_src = os.path.abspath(os.path.join(here, "..", "..", ".."))  # 가능하면 src 상위
    fallback_candidates = [
        os.path.join(here, "widget_server_settings.py"),
        os.path.join(here, "..", "widget_server_settings.py"),
        os.path.join(here, "..", "..", "settings", "ui", "widget_settings.py"),
        os.path.join(here, "..", "..", "server", "ui", "settings", "widget_server_settings.py"),
        os.path.join(repo_src, "server", "ui", "settings", "widget_server_settings.py"),
        os.path.join(repo_src, "src", "server", "ui", "settings", "widget_server_settings.py"),
    ]
    this_file_norm = os.path.normcase(os.path.normpath(os.path.abspath(__file__)))
    for fp in fallback_candidates:
        try:
            if not fp:
                continue
            fp_abs = os.path.normcase(os.path.normpath(os.path.abspath(fp)))
            if fp_abs == this_file_norm:
                # 자기 자신을 재실행하지 않음
                continue
            if not os.path.isfile(fp_abs):
                continue
            spec = importlib.util.spec_from_file_location("widget_server_settings_fallback", fp_abs)
            if spec is None or getattr(spec, "loader", None) is None:
                continue
            mod = importlib.util.module_from_spec(spec)
            # 최소한의 패키지명 설정으로 상대 import 가능성 보강 (간단)
            try:
                mod.__package__ = os.path.basename(os.path.dirname(fp_abs)) or ""
            except Exception:
                mod.__package__ = ""
            try:
                spec.loader.exec_module(mod)  # type: ignore
            except Exception as e:
                log.debug("[widget_settings] fallback 모듈 실행 실패(무시): %s", e)
                continue
            cand = getattr(mod, "ServerSettingsWidget", None) or getattr(mod, "SettingsWidget", None)
            if cand:
                # placeholder 판정
                try:
                    name = getattr(cand, "__name__", "") or str(cand)
                    if isinstance(name, str) and name.startswith("Placeholder_"):
                        log.debug("[widget_settings] 파일 후보가 placeholder임: %s", fp_abs)
                        continue
                except Exception:
                    pass
                ServerSettingsWidget = cand
                log.debug("[widget_settings] Loaded Settings widget from file fallback: %s", fp_abs)
                break
        except Exception:
            continue

# 3) 그래도 못 찾거나 후보가 placeholder라면 자체 구현 제공
if ServerSettingsWidget is None:
    try:
        # PyQt5 기반 위젯을 제공
        from PyQt5.QtWidgets import (
            QWidget,
            QLabel,
            QVBoxLayout,
            QHBoxLayout,
            QLineEdit,
            QPushButton,
            QMessageBox,
            QDialog,
        )
        from PyQt5.QtCore import Qt

        class ServerSettingsWidget(QDialog):
            """
            기본 Settings 위젯 (간단한 UI + MongoDB 저장 기능(선택적))
            - pymongo가 설치되어 있으면 'ui_settings' 컬렉션에 {'_id':'ui_settings', 'data': {...}} 형태로 저장/로드 시도
            - DB 작업은 버튼 클릭 시 지연 로드합니다 (모듈 import 시 DB 연결 없음)
            """

            def __init__(self, parent=None):
                super().__init__(parent)
                self.setWindowTitle("서버 설정")
                self.setModal(False)
                self.resize(480, 240)

                # 레이아웃
                v = QVBoxLayout(self)

                # 단순한 설정 항목 예: Mongo URI
                row = QHBoxLayout()
                row.addWidget(QLabel("Mongo URI:"))
                self.mongo_uri_edit = QLineEdit(self)
                self.mongo_uri_edit.setPlaceholderText("mongodb://localhost:27017/upbit_trader")
                row.addWidget(self.mongo_uri_edit)
                v.addLayout(row)

                # 예시: UI 설정 저장 키
                row2 = QHBoxLayout()
                row2.addWidget(QLabel("UI 테마 키:"))
                self.theme_edit = QLineEdit(self)
                self.theme_edit.setPlaceholderText("default")
                row2.addWidget(self.theme_edit)
                v.addLayout(row2)

                # 버튼
                btn_row = QHBoxLayout()
                self.load_btn = QPushButton("불러오기", self)
                self.save_btn = QPushButton("저��", self)
                btn_row.addWidget(self.load_btn)
                btn_row.addWidget(self.save_btn)
                v.addLayout(btn_row)

                # 상태 라벨
                self.status_label = QLabel("", self)
                v.addWidget(self.status_label)

                # 이벤트 연결
                self.load_btn.clicked.connect(self._on_load)
                self.save_btn.clicked.connect(self._on_save)

            def _on_load(self):
                """버튼 클릭 시 MongoDB에서 설정을 불���옵니다(가능한 경우)."""
                try:
                    uri = self.mongo_uri_edit.text().strip() or "mongodb://localhost:27017/upbit_trader"
                    # pymongo는 버튼 클릭 시 동적으로 import
                    try:
                        from pymongo import MongoClient  # type: ignore
                    except Exception:
                        QMessageBox.information(self, "정보", "pymongo가 설치되어 있지 않습니다. (DB 불러오기 불가)")
                        self.status_label.setText("pymongo 미설치: 로드 불가")
                        return

                    client = MongoClient(uri, serverSelectionTimeoutMS=2000)
                    dbname = uri.rsplit("/", 1)[-1] if "/" in uri else "upbit_trader"
                    db = client[dbname]
                    coll = db.get_collection("ui_settings")
                    doc = coll.find_one({"_id": "ui_settings"})
                    if doc and "data" in doc:
                        data = doc["data"]
                        # 안전하게 각 필드 업데이트
                        if isinstance(data, dict):
                            self.theme_edit.setText(data.get("theme", ""))
                            self.status_label.setText("설정 불러오기 성공")
                        else:
                            self.status_label.setText("설정 문서 포맷 불일치")
                    else:
                        self.status_label.setText("설정 문서가 없음")
                except Exception as e:
                    log.debug("[widget_settings] load 예외: %s", e)
                    QMessageBox.warning(self, "불러오기 실패", f"설정 불러오기 실패: {e}")
                    self.status_label.setText("불러오기 실패")

            def _on_save(self):
                """버튼 클릭 시 현재 필드들을 MongoDB에 저장합니다(가능한 경우)."""
                try:
                    uri = self.mongo_uri_edit.text().strip() or "mongodb://localhost:27017/upbit_trader"
                    try:
                        from pymongo import MongoClient  # type: ignore
                    except Exception:
                        QMessageBox.information(self, "정보", "pymongo가 설치되어 있지 않습니다. (DB 저장 불가)")
                        self.status_label.setText("pymongo 미설치: 저장 불가")
                        return

                    client = MongoClient(uri, serverSelectionTimeoutMS=2000)
                    dbname = uri.rsplit("/", 1)[-1] if "/" in uri else "upbit_trader"
                    db = client[dbname]
                    coll = db.get_collection("ui_settings")
                    data = {
                        "theme": self.theme_edit.text().strip() or "default",
                    }
                    coll.update_one({"_id": "ui_settings"}, {"$set": {"data": data}}, upsert=True)
                    self.status_label.setText("저장 성공")
                    QMessageBox.information(self, "저장", "설정이 저장되었습니다.")
                except Exception as e:
                    log.debug("[widget_settings] save 예외: %s", e)
                    QMessageBox.warning(self, "저장 실패", f"설정 저장 실패: {e}")
                    self.status_label.setText("저장 실패")

        log.debug("[widget_settings] Using builtin ServerSettingsWidget (GUI)")
    except Exception:
        # PyQt5가 없을 경우 아주 간단한 non-GUI placeholder 클래스 제공
        class ServerSettingsWidget:
            def __init__(self, parent=None):
                # 아무 동작도 하지 않는 객체
                pass

        log.debug("[widget_settings] Using non-GUI ServerSettingsWidget fallback")

# 노출되는 API (WidgetFactory가 기대하는 이름들)
def create_widget(parent: Optional[Any] = None) -> Any:
    """WidgetFactory 호환 create_widget 함수"""
    try:
        if callable(ServerSettingsWidget):
            try:
                return ServerSettingsWidget(parent)  # type: ignore
            except TypeError:
                return ServerSettingsWidget()  # type: ignore
    except Exception:
        log.debug("[widget_settings] create_widget 인스턴스화 실패(무시)")
    try:
        return ServerSettingsWidget()  # type: ignore
    except Exception:
        # 극단적 실패 시 빈 객체 반환
        class _Empty:
            pass
        return _Empty()

# SettingsWidget 이름�� 직접 import용으로 제공
SettingsWidget = ServerSettingsWidget  # type: ignore

__all__ = ["SettingsWidget", "create_widget"]