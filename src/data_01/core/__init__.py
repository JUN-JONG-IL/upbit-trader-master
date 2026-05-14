"""
[Purpose]
core/ - 코어 데이터 관리 패키지

[Responsibilities]
- DataManager (MongoDB CRUD 래퍼) re-export

[References]
- work_order/DB설계.md
"""

from .data_manager import DataManager

__all__ = ["DataManager"]
