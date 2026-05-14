# -*- coding: utf-8 -*-
import sys
import os
import importlib.util

# 현재 작업 디렉터리를 최상단에 추가 (안정성)
sys.path.insert(0, os.getcwd())

# widget_login.py 파일 경로 (숫자 시작 폴더명을 피하기 위해 파일 경로로 직접 로드)
widget_path = os.path.join(os.getcwd(), "src", "01_core", "auth", "ui", "widget_login.py")
if not os.path.isfile(widget_path):
    raise SystemExit(f"widget_login.py not found at: {widget_path}")

spec = importlib.util.spec_from_file_location("widget_login_mod", widget_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)  # type: ignore

# LoginWidget 클래스 취득
LoginWidget = getattr(module, "LoginWidget", None)
if LoginWidget is None:
    raise SystemExit("LoginWidget class not found in widget_login.py")

from PyQt5.QtWidgets import QApplication
from PyQt5 import QtCore

def main():
    app = QApplication(sys.argv)
    w = LoginWidget()
    w.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
