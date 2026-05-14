#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
Pie chart widget (headless-safe)

Provides:
- PieWorker: background worker (QThread or threading fallback) that updates the pie chart.
- MyMplCanvas: matplotlib FigureCanvas (Qt or Agg fallback).
- PieChartWidget: QWidget wrapper that exposes the canvas.
"""
from __future__ import annotations
import time
import logging
import threading

# Try Qt + QtAgg, otherwise fall back to Agg and minimal stubs
try:
    from PyQt5.QtCore import QThread
    from PyQt5.QtWidgets import QWidget, QApplication
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure
    import matplotlib.pyplot as plt
    _HAS_QT = True
except Exception as _e:
    logging.warning("PyQt5/Qt backend not available: %s. Falling back to headless mode.", _e)
    _HAS_QT = False
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas

    # thread-like fallback for QThread
    class QThread(threading.Thread):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.daemon = True
            self._alive = False

        def run(self):
            self._alive = True
            try:
                super().run()
            finally:
                self._alive = False

        def terminate(self):
            self._alive = False

    class QWidget:
        def __init__(self, *args, **kwargs):
            pass

    class QApplication:
        def __init__(self, *args, **kwargs):
            pass
        def exec_(self):
            return 0

try:
    from app import static
except ImportError:
    try:
        import importlib as _il
        static = _il.import_module("src.server.app").static  # type: ignore[assignment]
    except Exception:
        static = None  # type: ignore[assignment]


class PieWorker(QThread):
    """
    Worker that updates the pie chart periodically.
    Uses QThread when PyQt available, otherwise uses threading.Thread semantics.
    """
    def __init__(self, canvas):
        super().__init__()
        self.alive = False
        self.canvas = canvas

    def run(self):
        self.alive = True
        while self.alive:
            time.sleep(1)
            try:
                self.draw_piechart()
            except Exception:
                logging.exception("PieWorker draw_piechart failed")

    def draw_piechart(self):
        # Build data
        account = getattr(static, "account", None)
        cash = 0
        datas = []
        sum_val = 0
        if account is not None:
            try:
                cash = int(getattr(account, "cash", 0) + getattr(account, "locked_cash", 0))
            except Exception:
                cash = 0
            datas = [[cash, 'KRW']]
            sum_val = cash
            for k in getattr(account, "coins", {}) or {}:
                try:
                    val = int(account.coins[k].get('evaluate', 0))
                except Exception:
                    val = 0
                datas.append([val, k])
                sum_val += val
        else:
            datas = [[0, 'KRW']]
            sum_val = 0

        # sort and consolidate
        datas.sort(reverse=True)
        remain = [0, 'Other Coins']
        labels = []
        frequency = []

        if sum_val != 0:
            for item in datas:
                if len(labels) < 7 or item[1] == 'KRW':
                    percent = round(item[0] / sum_val * 100) if sum_val else 0
                    labels.append(f"{item[1]} : {percent}%")
                    frequency.append(item[0])
                else:
                    remain[0] += item[0]
            if remain[0] != 0:
                percent = round(remain[0] / sum_val * 100) if sum_val else 0
                labels.append(f"{remain[1]} : {percent}%")
                frequency.append(remain[0])
            try:
                self.canvas.axes.clear()
                self.canvas.axes2.clear()
            except Exception:
                pass
        else:
            labels = ["KRW : 100%"]
            frequency = [1]

        # Draw donut pie
        try:
            pie = self.canvas.axes.pie(
                frequency,
                startangle=90,
                counterclock=False,
                wedgeprops=dict(width=0.5)
            )
            try:
                self.canvas.axes2.legend(pie[0], labels, loc='center', labelcolor='white', borderpad=1, fontsize=12)
                self.canvas.axes2.axis('off')
            except Exception:
                try:
                    self.canvas.axes2.legend(pie[0], labels, loc='center')
                    self.canvas.axes2.axis('off')
                except Exception:
                    pass
            # draw or draw_idle
            if hasattr(self.canvas, 'draw_idle'):
                try:
                    self.canvas.draw_idle()
                except Exception:
                    self.canvas.draw()
            else:
                self.canvas.draw()
        except Exception:
            logging.exception("Failed to render pie chart")

    def close(self) -> None:
        self.alive = False
        try:
            return super().terminate()
        except Exception:
            try:
                if hasattr(self, 'join'):
                    self.join(timeout=1)
            except Exception:
                pass


class MyMplCanvas(FigureCanvas):
    """
    Matplotlib figure canvas with two subplots for pie + legend.
    """
    def __init__(self, parent=None, width=12, height=8):
        try:
            plt.rcParams['axes.facecolor'] = '#31363b'
            plt.rcParams['axes.edgecolor'] = '#ffffff'
            plt.rcParams['xtick.color'] = '#ffffff'
            plt.rcParams['ytick.color'] = '#ffffff'
        except Exception:
            pass

        self.figure = Figure(figsize=(width, height))
        self.figure.set_facecolor('#31363b')
        self.figure.set_edgecolor('#ffffff')

        try:
            self.axes = self.figure.add_subplot(1, 2, 1)
            self.axes2 = self.figure.add_subplot(1, 2, 2)
        except Exception:
            self.axes = None
            self.axes2 = None

        try:
            super().__init__(self.figure)
        except Exception:
            try:
                FigureCanvas.__init__(self, self.figure)
            except Exception:
                pass

        if parent is not None and hasattr(self, 'setParent'):
            try:
                self.setParent(parent)
            except Exception:
                pass

    def draw_idle(self):
        # Ensure draw_idle exists or fallback to draw
        try:
            return super().draw_idle()
        except Exception:
            try:
                return self.draw()
            except Exception:
                pass


class PieChartWidget(QWidget):
    """
    Reusable widget housing the matplotlib canvas and worker.
    """
    def __init__(self, parent=None):
        try:
            super().__init__(parent)
        except Exception:
            pass
        self.canvas = MyMplCanvas(self, width=7, height=3)
        self.pw = PieWorker(self.canvas)
        # initial draw
        try:
            self.pw.draw_piechart()
        except Exception:
            pass

    def closeEvent(self, event):
        try:
            self.pw.close()
        except Exception:
            pass