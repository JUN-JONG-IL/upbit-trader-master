# -*- coding: utf-8 -*-
# Form implementation generated from reading ui file 'userinfo.ui'
#
# Modified to be headless/container-safe: PyQt5 imports are wrapped and minimal
# fallback stubs are provided so the UI module can be imported even if PyQt5 is
# not available (server environment). When PyQt5 is present, normal Qt objects
# are used.
#
# Created by: PyQt5 UI code generator 5.15.4 (original)
# WARNING: Manual changes will be preserved in this modified file.

from .widget_piechart import PieChartWidget  # FIX: relative import
import logging

# Try real PyQt5 imports; otherwise provide safe fallbacks for headless execution.
try:
    from PyQt5 import QtCore, QtGui, QtWidgets
    _HAS_QT = True
except Exception as _e:
    logging.warning("PyQt5 not available: %s. Using headless stubs for ui_userinfo.", _e)
    _HAS_QT = False

    # Minimal QtCore stub
    class _QtCore:
        class Qt:
            AlignRight = 0x0001
            AlignTrailing = 0x0002
            AlignVCenter = 0x0004

        class QCoreApplication:
            @staticmethod
            def translate(ctx, text):
                return text

        class QMetaObject:
            @staticmethod
            def connectSlotsByName(obj):
                # no-op in headless
                return None

    QtCore = _QtCore()

    # Minimal QtGui stub
    class _QtGui:
        class QFont:
            def __init__(self):
                pass
            def setFamily(self, *args, **kwargs): pass
            def setPointSize(self, *args, **kwargs): pass
            def setBold(self, *args, **kwargs): pass
            def setWeight(self, *args, **kwargs): pass

    QtGui = _QtGui()

    # Minimal QtWidgets stub with lightweight behavior
    class _QtWidgets:
        class QWidget:
            def __init__(self, *args, **kwargs):
                self._children = []

            def setObjectName(self, name): pass
            def resize(self, w, h): pass
            def show(self): pass

        class QLabel:
            def __init__(self, *args, **kwargs):
                self._text = ""
            def setFont(self, f): pass
            def setAlignment(self, a): pass
            def setObjectName(self, name): pass
            def setText(self, text):
                self._text = text
            def text(self):
                return getattr(self, "_text", "")

        class QFrame:
            HLine = 0
            Sunken = 0
            def __init__(self, *args, **kwargs): pass
            def setFrameShape(self, shape): pass
            def setFrameShadow(self, shadow): pass
            def setObjectName(self, name): pass

        class QVBoxLayout:
            def __init__(self, parent=None):
                self.parent = parent
                self._items = []
            def setContentsMargins(self, *args, **kwargs): pass
            def setSpacing(self, *args, **kwargs): pass
            def setObjectName(self, name): pass
            def addLayout(self, layout): self._items.append(layout)
            def addWidget(self, widget): self._items.append(widget)
            def addStretch(self, s=0): pass

        class QHBoxLayout(QVBoxLayout):
            def setStretch(self, idx, val): pass

        class QApplication:
            def __init__(self, argv): pass
            def exec_(self): return 0

        class QPushButton:
            def __init__(self, *args, **kwargs): pass

    QtWidgets = _QtWidgets()


class Ui_Form(object):
    def setupUi(self, Form):
        try:
            Form.setObjectName("Form")
        except Exception:
            pass
        try:
            Form.resize(805, 231)
        except Exception:
            pass

        # Layout and widgets creation (works with real Qt or headless stubs)
        self.verticalLayout = QtWidgets.QVBoxLayout(Form)
        try:
            self.verticalLayout.setContentsMargins(0, 0, 0, 0)
            self.verticalLayout.setSpacing(0)
        except Exception:
            pass
        try:
            self.verticalLayout.setObjectName("verticalLayout")
        except Exception:
            pass

        self.user_info = QtWidgets.QWidget(Form)
        try:
            self.user_info.setObjectName("user_info")
        except Exception:
            pass

        self.horizontalLayout = QtWidgets.QHBoxLayout(self.user_info)
        try:
            self.horizontalLayout.setContentsMargins(0, 0, 0, 0)
            self.horizontalLayout.setSpacing(0)
        except Exception:
            pass
        try:
            self.horizontalLayout.setObjectName("horizontalLayout")
        except Exception:
            pass

        self.verticalLayout_3 = QtWidgets.QVBoxLayout()
        try:
            self.verticalLayout_3.setObjectName("verticalLayout_3")
        except Exception:
            pass

        self.frame_2 = QtWidgets.QVBoxLayout()
        try:
            self.frame_2.setSpacing(0)
            self.frame_2.setObjectName("frame_2")
        except Exception:
            pass

        self.horizontalLayout_6 = QtWidgets.QHBoxLayout()
        try:
            self.horizontalLayout_6.setContentsMargins(10, -1, 10, -1)
            self.horizontalLayout_6.setSpacing(10)
            self.horizontalLayout_6.setObjectName("horizontalLayout_6")
        except Exception:
            pass

        self.label_10 = QtWidgets.QLabel(self.user_info)
        try:
            font = QtGui.QFont()
            font.setFamily("Segoe UI")
            font.setPointSize(15)
            font.setBold(True)
            font.setWeight(75)
            self.label_10.setFont(font)
            self.label_10.setObjectName("label_10")
            try:
                self.horizontalLayout_6.addWidget(self.label_10)
            except Exception:
                pass
        except Exception:
            pass

        self.userdata4 = QtWidgets.QLabel(self.user_info)
        try:
            font = QtGui.QFont()
            font.setFamily("Segoe UI")
            font.setPointSize(15)
            font.setBold(True)
            font.setWeight(75)
            self.userdata4.setFont(font)
            try:
                self.userdata4.setAlignment(QtCore.Qt.AlignRight|QtCore.Qt.AlignTrailing|QtCore.Qt.AlignVCenter)
            except Exception:
                pass
            self.userdata4.setObjectName("userdata4")
            try:
                self.horizontalLayout_6.addWidget(self.userdata4)
            except Exception:
                pass
        except Exception:
            pass

        self.label_11 = QtWidgets.QLabel(self.user_info)
        try:
            font = QtGui.QFont()
            font.setFamily("Segoe UI")
            font.setPointSize(15)
            font.setBold(True)
            font.setWeight(75)
            self.label_11.setFont(font)
            self.label_11.setObjectName("label_11")
            try:
                self.horizontalLayout_6.addWidget(self.label_11)
                self.horizontalLayout_6.setStretch(1, 2)
            except Exception:
                pass
        except Exception:
            pass
        try:
            self.frame_2.addLayout(self.horizontalLayout_6)
        except Exception:
            pass

        self.line = QtWidgets.QFrame(self.user_info)
        try:
            self.line.setFrameShape(QtWidgets.QFrame.HLine)
            self.line.setFrameShadow(QtWidgets.QFrame.Sunken)
            self.line.setObjectName("line")
            try:
                self.frame_2.addWidget(self.line)
            except Exception:
                pass
        except Exception:
            pass

        self.horizontalLayout_8 = QtWidgets.QHBoxLayout()
        try:
            self.horizontalLayout_8.setContentsMargins(10, -1, 10, -1)
            self.horizontalLayout_8.setSpacing(10)
            self.horizontalLayout_8.setObjectName("horizontalLayout_8")
        except Exception:
            pass

        self.label_14 = QtWidgets.QLabel(self.user_info)
        try:
            font = QtGui.QFont()
            font.setFamily("Segoe UI")
            font.setPointSize(15)
            font.setBold(True)
            font.setWeight(75)
            self.label_14.setFont(font)
            self.label_14.setObjectName("label_14")
            try:
                self.horizontalLayout_8.addWidget(self.label_14)
            except Exception:
                pass
        except Exception:
            pass

        self.userdata5 = QtWidgets.QLabel(self.user_info)
        try:
            font = QtGui.QFont()
            font.setFamily("Segoe UI")
            font.setPointSize(15)
            font.setBold(True)
            font.setWeight(75)
            self.userdata5.setFont(font)
            try:
                self.userdata5.setAlignment(QtCore.Qt.AlignRight|QtCore.Qt.AlignTrailing|QtCore.Qt.AlignVCenter)
            except Exception:
                pass
            self.userdata5.setObjectName("userdata5")
            try:
                self.horizontalLayout_8.addWidget(self.userdata5)
            except Exception:
                pass
        except Exception:
            pass

        self.label_13 = QtWidgets.QLabel(self.user_info)
        try:
            font = QtGui.QFont()
            font.setFamily("Segoe UI")
            font.setPointSize(15)
            font.setBold(True)
            font.setWeight(75)
            self.label_13.setFont(font)
            self.label_13.setObjectName("label_13")
            try:
                self.horizontalLayout_8.addWidget(self.label_13)
                self.horizontalLayout_8.setStretch(1, 2)
            except Exception:
                pass
        except Exception:
            pass
        try:
            self.frame_2.addLayout(self.horizontalLayout_8)
        except Exception:
            pass

        self.horizontalLayout_9 = QtWidgets.QHBoxLayout()
        try:
            self.horizontalLayout_9.setContentsMargins(10, -1, 10, -1)
            self.horizontalLayout_9.setSpacing(10)
            self.horizontalLayout_9.setObjectName("horizontalLayout_9")
        except Exception:
            pass

        self.label_17 = QtWidgets.QLabel(self.user_info)
        try:
            font = QtGui.QFont()
            font.setFamily("Segoe UI")
            font.setPointSize(15)
            font.setBold(True)
            font.setWeight(75)
            self.label_17.setFont(font)
            self.label_17.setObjectName("label_17")
            try:
                self.horizontalLayout_9.addWidget(self.label_17)
            except Exception:
                pass
        except Exception:
            pass

        self.userdata6 = QtWidgets.QLabel(self.user_info)
        try:
            font = QtGui.QFont()
            font.setFamily("Segoe UI")
            font.setPointSize(15)
            font.setBold(True)
            font.setWeight(75)
            self.userdata6.setFont(font)
            try:
                self.userdata6.setAlignment(QtCore.Qt.AlignRight|QtCore.Qt.AlignTrailing|QtCore.Qt.AlignVCenter)
            except Exception:
                pass
            self.userdata6.setObjectName("userdata6")
            try:
                self.horizontalLayout_9.addWidget(self.userdata6)
            except Exception:
                pass
        except Exception:
            pass

        self.label_16 = QtWidgets.QLabel(self.user_info)
        try:
            font = QtGui.QFont()
            font.setFamily("Segoe UI")
            font.setPointSize(15)
            font.setBold(False)
            font.setWeight(50)
            self.label_16.setFont(font)
            self.label_16.setObjectName("label_16")
            try:
                self.horizontalLayout_9.addWidget(self.label_16)
                self.horizontalLayout_9.setStretch(1, 2)
            except Exception:
                pass
        except Exception:
            pass
        try:
            self.frame_2.addLayout(self.horizontalLayout_9)
            self.verticalLayout_3.addLayout(self.frame_2)
        except Exception:
            pass

        self.frame_1 = QtWidgets.QVBoxLayout()
        try:
            self.frame_1.setSpacing(0)
            self.frame_1.setObjectName("frame_1")
        except Exception:
            pass

        self.horizontalLayout_5 = QtWidgets.QHBoxLayout()
        try:
            self.horizontalLayout_5.setContentsMargins(10, -1, 10, -1)
            self.horizontalLayout_5.setSpacing(10)
            self.horizontalLayout_5.setObjectName("horizontalLayout_5")
        except Exception:
            pass

        self.label_2 = QtWidgets.QLabel(self.user_info)
        try:
            font = QtGui.QFont()
            font.setFamily("Segoe UI")
            font.setPointSize(15)
            font.setBold(True)
            font.setWeight(75)
            self.label_2.setFont(font)
            self.label_2.setObjectName("label_2")
            try:
                self.horizontalLayout_5.addWidget(self.label_2)
            except Exception:
                pass
        except Exception:
            pass

        self.userdata1 = QtWidgets.QLabel(self.user_info)
        try:
            font = QtGui.QFont()
            font.setFamily("Segoe UI")
            font.setPointSize(15)
            font.setBold(True)
            font.setWeight(75)
            self.userdata1.setFont(font)
            try:
                self.userdata1.setAlignment(QtCore.Qt.AlignRight|QtCore.Qt.AlignTrailing|QtCore.Qt.AlignVCenter)
            except Exception:
                pass
            self.userdata1.setObjectName("userdata1")
            try:
                self.horizontalLayout_5.addWidget(self.userdata1)
            except Exception:
                pass
        except Exception:
            pass

        self.label_5 = QtWidgets.QLabel(self.user_info)
        try:
            font = QtGui.QFont()
            font.setFamily("Segoe UI")
            font.setPointSize(15)
            font.setBold(True)
            font.setWeight(75)
            self.label_5.setFont(font)
            self.label_5.setObjectName("label_5")
            try:
                self.horizontalLayout_5.addWidget(self.label_5)
                self.horizontalLayout_5.setStretch(1, 2)
            except Exception:
                pass
        except Exception:
            pass
        try:
            self.frame_1.addLayout(self.horizontalLayout_5)
        except Exception:
            pass

        self.line_2 = QtWidgets.QFrame(self.user_info)
        try:
            self.line_2.setFrameShape(QtWidgets.QFrame.HLine)
            self.line_2.setFrameShadow(QtWidgets.QFrame.Sunken)
            self.line_2.setObjectName("line_2")
            try:
                self.frame_1.addWidget(self.line_2)
            except Exception:
                pass
        except Exception:
            pass

        self.horizontalLayout_3 = QtWidgets.QHBoxLayout()
        try:
            self.horizontalLayout_3.setContentsMargins(10, -1, 10, -1)
            self.horizontalLayout_3.setSpacing(10)
            self.horizontalLayout_3.setObjectName("horizontalLayout_3")
        except Exception:
            pass

        self.label = QtWidgets.QLabel(self.user_info)
        try:
            font = QtGui.QFont()
            font.setFamily("Segoe UI")
            font.setPointSize(15)
            font.setBold(True)
            font.setWeight(75)
            self.label.setFont(font)
            self.label.setObjectName("label")
            try:
                self.horizontalLayout_3.addWidget(self.label)
            except Exception:
                pass
        except Exception:
            pass

        self.userdata2 = QtWidgets.QLabel(self.user_info)
        try:
            font = QtGui.QFont()
            font.setFamily("Segoe UI")
            font.setPointSize(15)
            font.setBold(True)
            font.setWeight(75)
            self.userdata2.setFont(font)
            try:
                self.userdata2.setAlignment(QtCore.Qt.AlignRight|QtCore.Qt.AlignTrailing|QtCore.Qt.AlignVCenter)
            except Exception:
                pass
            self.userdata2.setObjectName("userdata2")
            try:
                self.horizontalLayout_3.addWidget(self.userdata2)
            except Exception:
                pass
        except Exception:
            pass

        self.label_7 = QtWidgets.QLabel(self.user_info)
        try:
            font = QtGui.QFont()
            font.setFamily("Segoe UI")
            font.setPointSize(15)
            font.setBold(True)
            font.setWeight(75)
            self.label_7.setFont(font)
            self.label_7.setObjectName("label_7")
            try:
                self.horizontalLayout_3.addWidget(self.label_7)
                self.horizontalLayout_3.setStretch(1, 2)
            except Exception:
                pass
        except Exception:
            pass
        try:
            self.frame_1.addLayout(self.horizontalLayout_3)
        except Exception:
            pass

        self.horizontalLayout_2 = QtWidgets.QHBoxLayout()
        try:
            self.horizontalLayout_2.setContentsMargins(10, -1, 10, -1)
            self.horizontalLayout_2.setSpacing(10)
            self.horizontalLayout_2.setObjectName("horizontalLayout_2")
        except Exception:
            pass

        self.label_3 = QtWidgets.QLabel(self.user_info)
        try:
            font = QtGui.QFont()
            font.setFamily("Segoe UI")
            font.setPointSize(15)
            font.setBold(True)
            font.setWeight(75)
            self.label_3.setFont(font)
            self.label_3.setObjectName("label_3")
            try:
                self.horizontalLayout_2.addWidget(self.label_3)
            except Exception:
                pass
        except Exception:
            pass

        self.userdata3 = QtWidgets.QLabel(self.user_info)
        try:
            font = QtGui.QFont()
            font.setFamily("Segoe UI")
            font.setPointSize(15)
            font.setBold(True)
            font.setWeight(75)
            self.userdata3.setFont(font)
            try:
                self.userdata3.setAlignment(QtCore.Qt.AlignRight|QtCore.Qt.AlignTrailing|QtCore.Qt.AlignVCenter)
            except Exception:
                pass
            self.userdata3.setObjectName("userdata3")
            try:
                self.horizontalLayout_2.addWidget(self.userdata3)
            except Exception:
                pass
        except Exception:
            pass

        self.label_9 = QtWidgets.QLabel(self.user_info)
        try:
            font = QtGui.QFont()
            font.setFamily("Segoe UI")
            font.setPointSize(15)
            font.setBold(True)
            font.setWeight(75)
            self.label_9.setFont(font)
            self.label_9.setObjectName("label_9")
            try:
                self.horizontalLayout_2.addWidget(self.label_9)
                self.horizontalLayout_2.setStretch(1, 2)
            except Exception:
                pass
        except Exception:
            pass
        try:
            self.frame_1.addLayout(self.horizontalLayout_2)
            self.verticalLayout_3.addLayout(self.frame_1)
            self.horizontalLayout.addLayout(self.verticalLayout_3)
        except Exception:
            pass

        # Pie chart widget (safe: widget_piechart has its own headless fallbacks)
        try:
            self.widget = PieChartWidget(self.user_info)
            self.widget.setObjectName("widget")
            try:
                self.horizontalLayout.addWidget(self.widget)
                self.horizontalLayout.setStretch(0, 1)
                self.horizontalLayout.setStretch(1, 1)
            except Exception:
                pass
        except Exception:
            logging.exception("Failed to create PieChartWidget; continuing without it")

        try:
            self.verticalLayout.addWidget(self.user_info)
        except Exception:
            pass

        self.retranslateUi(Form)
        try:
            QtCore.QMetaObject.connectSlotsByName(Form)
        except Exception:
            pass

    def retranslateUi(self, Form):
        _translate = QtCore.QCoreApplication.translate
        try:
            Form.setWindowTitle(_translate("Form", "Form"))
            self.label_10.setText(_translate("Form", "총 보유자산"))
            self.userdata4.setText(_translate("Form", "0"))
            self.label_11.setText(_translate("Form", "KRW"))
            self.label_14.setText(_translate("Form", "총 평가손익"))
            self.userdata5.setText(_translate("Form", "0"))
            self.label_13.setText(_translate("Form", "KRW"))
            self.label_17.setText(_translate("Form", "총평가수익률"))
            self.userdata6.setText(_translate("Form", "0"))
            self.label_16.setText(_translate("Form", "%"))
            self.label_2.setText(_translate("Form", "보유 KRW"))
            self.userdata1.setText(_translate("Form", "0"))
            self.label_5.setText(_translate("Form", "KRW"))
            self.label.setText(_translate("Form", "총매수금액"))
            self.userdata2.setText(_translate("Form", "0"))
            self.label_7.setText(_translate("Form", "KRW"))
            self.label_3.setText(_translate("Form", "총평가금액"))
            self.userdata3.setText(_translate("Form", "0"))
            self.label_9.setText(_translate("Form", "KRW"))
        except Exception:
            # In headless/stub mode, setting text may not be supported; ignore.
            pass

if __name__ == "__main__":
    # Only run demo when real Qt is available
    if _HAS_QT:
        import sys
        app = QtWidgets.QApplication(sys.argv)
        Form = QtWidgets.QWidget()
        ui = Ui_Form()
        ui.setupUi(Form)
        Form.show()
        sys.exit(app.exec_())