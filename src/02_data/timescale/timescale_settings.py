# timescale_settings.py
from __future__ import annotations
import json
from typing import List, Any, Dict, Optional, Tuple
from PyQt5.QtCore import QSettings

SETTINGS_GROUP = "TimescaleDialog"
RECENT_KEY = "recent_symbols"
FAV_KEY = "favorite_symbols"


class TimescaleSettings:
    def __init__(self):
        self._settings = QSettings("UpbitTrader", "TimescaleDialog")

    def load_connection(self) -> Dict[str, Any]:
        """
        Load connection and related persistent options.
        Returns a dict with keys (host, db, user, pass, mode, auto_override,
        backfill_periodic, backfill_interval_sec).
        """
        self._settings.beginGroup(SETTINGS_GROUP)
        try:
            # QSettings may store booleans/strings/ints — normalize them
            def _as_bool(v):
                return v in (True, "true", "True", "1", 1)

            def _as_int(v, fallback=30):
                try:
                    return int(v)
                except Exception:
                    return int(fallback)

            result = {
                "host": self._settings.value("host", "") or "",
                "db": self._settings.value("db", "") or "",
                "user": self._settings.value("user", "") or "",
                "pass": self._settings.value("pass", "") or "",
                "mode": self._settings.value("mode", "auto") or "auto",
                "auto_override": _as_bool(self._settings.value("auto_override", False)),
                # new backfill-related keys
                "backfill_periodic": _as_bool(self._settings.value("backfill_periodic", False)),
                "backfill_interval_sec": _as_int(self._settings.value("backfill_interval_sec", int(30)))
            }
            return result
        finally:
            self._settings.endGroup()

    def save_connection(self, host: Optional[Any] = None, db: Optional[Any] = None,
                        user: Optional[Any] = None, passwd: Optional[Any] = None,
                        mode: Optional[Any] = None, auto_override: Optional[Any] = None,
                        **kwargs) -> None:
        """
        Save connection and optional backfill settings.

        Supports two usages:
        - save_connection(host, db, user, passwd, mode, auto_override)
          (backward-compatible)
        - save_connection(conn_dict) where conn_dict is a single dict argument
          containing keys like 'host','db','user','pass','mode','auto_override',
          and optional 'backfill_periodic','backfill_interval_sec'.

        Any provided backfill keys in kwargs will be stored.
        """
        # If first positional argument is a dict (legacy or new call), accept that
        # Example: save_connection(conn_dict)
        if isinstance(host, dict) and db is None and user is None and passwd is None:
            conn = host  # type: ignore
            host = conn.get("host", "")
            db = conn.get("db", "")
            user = conn.get("user", "")
            passwd = conn.get("pass", conn.get("passwd", conn.get("password", "")))
            mode = conn.get("mode", "auto")
            auto_override = conn.get("auto_override", False)
            # extract backfill keys if present
            backfill_periodic = conn.get("backfill_periodic", conn.get("auto_backfill_periodic", False))
            backfill_interval_sec = conn.get("backfill_interval_sec", conn.get("auto_backfill_interval_sec", None))
        else:
            # Also accept backfill keys via kwargs
            backfill_periodic = kwargs.get("backfill_periodic", kwargs.get("auto_backfill_periodic", False))
            backfill_interval_sec = kwargs.get("backfill_interval_sec", kwargs.get("auto_backfill_interval_sec", None))

        # Normalize types
        def _norm_bool(v):
            return v in (True, "true", "True", "1", 1)

        def _norm_int(v, fallback=None):
            try:
                return int(v)
            except Exception:
                return fallback

        self._settings.beginGroup(SETTINGS_GROUP)
        try:
            # store core connection fields
            self._settings.setValue("host", host if host is not None else "")
            self._settings.setValue("db", db if db is not None else "")
            self._settings.setValue("user", user if user is not None else "")
            self._settings.setValue("pass", passwd if passwd is not None else "")
            self._settings.setValue("mode", mode if mode is not None else "auto")
            self._settings.setValue("auto_override", bool(auto_override))

            # store backfill fields (optional)
            try:
                self._settings.setValue("backfill_periodic", bool(_norm_bool(backfill_periodic)))
            except Exception:
                # ignore if not serializable
                pass

            if backfill_interval_sec is not None:
                try:
                    self._settings.setValue("backfill_interval_sec", int(_norm_int(backfill_interval_sec, int(30))))
                except Exception:
                    pass

            self._settings.sync()
        finally:
            self._settings.endGroup()

    def load_recent_and_favs(self) -> Tuple[List[str], List[str]]:
        """
        Return (recent_list, fav_list)
        """
        self._settings.beginGroup(SETTINGS_GROUP)
        try:
            recent_json = self._settings.value(RECENT_KEY, "[]")
            fav_json = self._settings.value(FAV_KEY, "[]")
            try:
                recent = json.loads(recent_json) if isinstance(recent_json, str) else recent_json or []
            except Exception:
                recent = []
            try:
                favs = json.loads(fav_json) if isinstance(fav_json, str) else fav_json or []
            except Exception:
                favs = []
            return recent, favs
        finally:
            self._settings.endGroup()

    def save_recent_and_favs(self, recent: List[str], favs: List[str]) -> None:
        self._settings.beginGroup(SETTINGS_GROUP)
        try:
            self._settings.setValue(RECENT_KEY, json.dumps(recent))
            self._settings.setValue(FAV_KEY, json.dumps(favs))
            self._settings.sync()
        finally:
            self._settings.endGroup()

    def _str_to_bool(self, v) -> bool:
        return v in (True, "true", "True", "1", 1)