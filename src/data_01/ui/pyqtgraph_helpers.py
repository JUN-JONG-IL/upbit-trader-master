#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PyQtGraph 실시간 차트 헬퍼

라이트 모드 기반 PlotWidget 팩토리 함수를 제공합니다.
- create_realtime_chart() : 라이트 모드 실시간 차트 생성
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def create_realtime_chart(container_widget, title: str = "Real-time Chart"):
    """실시간 차트를 생성하여 container_widget에 추가합니다.

    Args:
        container_widget : 차트를 추가할 QWidget 컨테이너
        title            : 차트 제목

    Returns:
        pg.PlotWidget 인스턴스, 또는 pyqtgraph 미설치 시 None
    """
    try:
        import pyqtgraph as pg  # type: ignore
        from PyQt5.QtWidgets import QVBoxLayout

        layout = container_widget.layout()
        if not layout:
            layout = QVBoxLayout(container_widget)
            layout.setContentsMargins(0, 0, 0, 0)

        plot_widget = pg.PlotWidget(title=title)
        plot_widget.setBackground("w")  # 라이트 모드 배경
        plot_widget.showGrid(x=True, y=True, alpha=0.3)
        plot_widget.setLabel("left", "Value", color="#000000")
        plot_widget.setLabel("bottom", "Time (s)", color="#000000")

        # OpenGL 가속 활성화 (사용 가능한 경우)
        try:
            plot_widget.useOpenGL(True)
        except Exception:
            pass  # OpenGL 미지원 환경에서는 소프트웨어 렌더링 사용

        layout.addWidget(plot_widget)
        logger.debug("[PyQtGraphHelpers] 차트 생성 완료: %s", title)
        return plot_widget

    except ImportError:
        logger.debug("[PyQtGraphHelpers] pyqtgraph 미설치 — 차트 비활성화")
        return None
    except Exception as exc:
        logger.warning("[PyQtGraphHelpers] 차트 생성 실패: %s", exc)
        return None
