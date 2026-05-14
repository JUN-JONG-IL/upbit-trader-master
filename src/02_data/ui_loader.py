#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UI 로더 보정 유틸

- uic.loadUi를 호출할 때 .ui 내부의 tabPosition 같은 속성에
  Alignment enum(AlignTop 등)이 들어있어 PyQt5에서 불일치가 발생하면
  해당 블록만 안전하게 숫자로 바꿔 임시 파일로 로드해 줍니다.

사용법 (dialog에서):
from src.data.ui_loader import load_ui_with_tab_fix
load_ui_with_tab_fix("path/to/ui.ui", self)
"""

import os
import tempfile
import re
from PyQt5 import uic

def load_ui_with_tab_fix(ui_path: str, baseinstance) -> None:
    try:
        raw = open(ui_path, "r", encoding="utf-8").read()
    except Exception:
        uic.loadUi(ui_path, baseinstance)
        return

    def _replace_block(m):
        block = m.group(0)
        # Mapping Align* -> QTabWidget.TabPosition numbers (North=0, South=1, West=2, East=3)
        block = block.replace("<enum>AlignTop</enum>", "<number>0</number>")
        block = block.replace("<enum>AlignBottom</enum>", "<number>1</number>")
        block = block.replace("<enum>AlignLeft</enum>", "<number>2</number>")
        block = block.replace("<enum>AlignRight</enum>", "<number>3</number>")
        block = block.replace("<enum>North</enum>", "<number>0</number>")
        block = block.replace("<enum>South</enum>", "<number>1</number>")
        block = block.replace("<enum>West</enum>", "<number>2</number>")
        block = block.replace("<enum>East</enum>", "<number>3</number>")
        return block

    fixed = re.sub(r'(<property\s+name="tabPosition">.*?</property>)', _replace_block, raw, flags=re.DOTALL)
    tf = tempfile.NamedTemporaryFile(delete=False, suffix=".ui", mode="w", encoding="utf-8")
    try:
        tf.write(fixed)
        tf.flush()
        tf.close()
        uic.loadUi(tf.name, baseinstance)
    finally:
        try:
            os.unlink(tf.name)
        except Exception:
            pass