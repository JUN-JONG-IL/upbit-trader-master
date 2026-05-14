# -*- coding: utf-8 -*-
"""
08_portfolio 모듈 인터페이스
포트폴리오 및 사용자 정보 추상화
"""
from __future__ import annotations
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_portfolio_dir = str(Path(__file__).parents[3] / "08_portfolio")
if _portfolio_dir not in sys.path:
    sys.path.insert(0, _portfolio_dir)


class PortfolioService:
    """08_portfolio 모듈 서비스 레이어"""

    def __init__(self) -> None:
        self._portfolio_widget: Optional[Any] = None
        self._userinfo_widget: Optional[Any] = None

    def get_portfolio_widget(self) -> Any:
        if self._portfolio_widget is None:
            try:
                from portfolio.portfolio_widget import PortfolioWidget  # type: ignore
                self._portfolio_widget = PortfolioWidget
            except ImportError:
                pass
        return self._portfolio_widget

    def get_userinfo_widget(self) -> Any:
        if self._userinfo_widget is None:
            try:
                from userinfo.userinfo_widget import UserinfoWidget  # type: ignore
                self._userinfo_widget = UserinfoWidget
            except ImportError:
                pass
        return self._userinfo_widget

    async def get_balances(self) -> List[Dict[str, Any]]:
        """보유 자산 조회 - 08_portfolio 모듈 위임"""
        try:
            from portfolio.portfolio_logic import get_balances as _get_balances  # type: ignore
            return await _get_balances() or []
        except ImportError:
            pass
        except Exception:
            pass
        return []
