#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
API Settings Dialog

Dialog for configuring OpenAI and Google API keys
"""

import os
import logging
from pathlib import Path

try:
    from PyQt5.QtWidgets import QWidget, QDialog, QVBoxLayout, QLabel, QPushButton
except Exception as _e:
    from utils.qt_stub import QtCore, QtGui, QtWidgets
