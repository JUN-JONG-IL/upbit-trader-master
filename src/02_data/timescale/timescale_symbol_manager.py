# timescale_symbol_manager.py
from __future__ import annotations
import logging
from typing import List, Set, Callable
from PyQt5.QtCore import QStringListModel
from PyQt5.QtWidgets import QCompleter

from .timescale_worker import timescale_ConnectorWorker
from .timescale_utils import timescale_build_dsn

logger = logging.getLogger("data.timescale.symbol_manager")

class SymbolManager:
    """
    Manages symbol index, recent and favorites and provides a completer model.
    Accepts a function to build DSN (usually a wrapper from dialog).
    """

    def __init__(self, dsn_builder: Callable[[], str], completer_model: QStringListModel):
        self._dsn_builder = dsn_builder
        self._symbols_index: List[str] = []
        self._recent: List[str] = []
        self._favorites: Set[str] = set()
        self._completer_model = completer_model

    # ---- persistence hooks (dialog may call save/load externally) ----
    def set_recent(self, recent: List[str]):
        self._recent = list(recent or [])

    def set_favorites(self, favs: List[str]):
        self._favorites = set(favs or [])

    def get_recent(self) -> List[str]:
        return list(self._recent)

    def get_favorites(self) -> List[str]:
        return sorted(self._favorites)

    # ---- index population ----
    def populate_symbols_async(self, result_cb, error_cb):
        dsn = self._dsn_builder()
        w = timescale_ConnectorWorker(dsn)
        w.result.connect(result_cb)
        w.error.connect(error_cb)
        w.run_action("get_distinct_symbols")
        return w

    def update_from_rows(self, rows):
        symbols = []
        for r in rows or []:
            if isinstance(r, dict):
                v = r.get("symbol")
            elif isinstance(r, (list, tuple)):
                v = r[0] if r else None
            else:
                v = r
            if v:
                symbols.append(str(v))
        self._symbols_index = symbols
        self._refresh_completer_model()

    # ---- selection tracking ----
    def note_selected(self, sym: str, max_recent: int = 50):
        if not sym:
            return
        if sym in self._recent:
            self._recent.remove(sym)
        self._recent.insert(0, sym)
        if len(self._recent) > max_recent:
            self._recent = self._recent[:max_recent]
        if sym not in self._symbols_index:
            self._symbols_index.insert(0, sym)
        self._refresh_completer_model()

    def toggle_favorite(self, sym: str):
        if not sym:
            return False
        if sym in self._favorites:
            self._favorites.remove(sym)
            return False
        else:
            self._favorites.add(sym)
            return True

    # ---- completer model management ----
    def _refresh_completer_model(self, filter_text: str = ""):
        items = []
        items.extend(sorted(self._favorites))
        items.extend([s for s in self._recent if s not in self._favorites])
        items.extend([s for s in self._symbols_index if s not in self._favorites and s not in self._recent])
        if filter_text:
            items = [s for s in items if filter_text.lower() in s.lower()]
        self._completer_model.setStringList(items)