"""
Small QSettings helper utilities to centralize keys and defaults.
"""
try:
    from PyQt5.QtCore import QSettings
except Exception:
    QSettings = None  # type: ignore[assignment,misc]


DEFAULT_GENERAL = {
    'chart_type': 'candlestick',
    'timezone': 'KST',
}


def load_general(settings) -> dict:
    if settings is None:
        return DEFAULT_GENERAL.copy()
    return settings.value("general_settings", DEFAULT_GENERAL.copy(), type=dict)


def save_general(settings, general: dict):
    if settings is not None:
        settings.setValue("general_settings", general)


def load_indicators(settings) -> dict:
    if settings is None:
        return {}
    return settings.value("active_indicators", {}, type=dict)


def save_indicators(settings, indicators: dict):
    if settings is not None:
        settings.setValue("active_indicators", indicators)
