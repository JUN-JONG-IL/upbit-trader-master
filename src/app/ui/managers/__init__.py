"""
UI 매니저 패키지 (v11.0 - 책임 분리)

책임 분리:
- WidgetLoader: 위젯 생성 및 임베드 (_make_* 메서드)
- MenuHandler: 메뉴 액션 처리 (_on_* 메서드)
- DBDialogManager: DB 다이얼로그 관리 (_open_*_dialog 메서드) + 우선순위 설정 다이얼로그
- SymbolLoader: 심볼 데이터 비동기 로딩
- WidgetFactory: 위젯 생성/배치 전담 (window_main.py 모듈화)
- WorkerManager: 워커 생명주기 관리 (window_main.py 모듈화)

변경 이력:
- v11.0: AIDialogManager 제거 (우선순위 관련 기능은 DBDialogManager로 완전 통합)
"""

from .widget_loader import WidgetLoader
from .menu_handler import MenuHandler
from .db_dialog_manager import DBDialogManager
from .symbol_loader import SymbolLoader
from .widget_factory import WidgetFactory
from .worker_manager import WorkerManager

__all__ = [
    "WidgetLoader",
    "MenuHandler",
    "DBDialogManager",
    "SymbolLoader",
    "WidgetFactory",
    "WorkerManager",
]