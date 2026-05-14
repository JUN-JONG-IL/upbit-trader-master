"""
userinfo ?⑦궎吏 怨듦컻 吏꾩엯??(headless-safe)

?먮옒 ??븷:
- from userinfo import UserinfoWidget, PieChartWidget ?깆쑝濡??꾩젽???몃??먯꽌 媛꾪렪???ъ슜?섍쾶 ??

蹂寃??ы빆:
- PyQt5/GUI 愿???꾪룷???ㅽ뙣 ?쒖뿉???⑦궎吏 import媛 ?ㅽ뙣?섏? ?딅룄濡??덉쟾???泥?placeholder)瑜??쒓났?⑸땲??
- ?ㅼ젣 ?꾩젽 援ы쁽? ?숈씪???대쫫?쇰줈 ?쒓났?섎ŉ, ?대? ?뚯씪?ㅼ씠 ?대? headless-safe ?섎룄濡??⑥튂?섏뼱 ?덉쑝硫?
  ?ш린?쒕뒗 ?뺤긽?곸쑝濡??먮옒 ?대옒?ㅻ? 媛?몄샃?덈떎.
"""

import logging

try:
    from .ui.widget_userinfo import UserinfoWidget
except Exception as e:
    logging.exception("Failed to import UserinfoWidget from widget_userinfo: %s", e)

    class UserinfoWidget:
        """Placeholder UserinfoWidget (PyQt not available)."""
        def __init__(self, *args, **kwargs):
            logging.warning("Using placeholder UserinfoWidget (no GUI).")

try:
    from .ui.widget_piechart import PieChartWidget, PieWorker, MyMplCanvas
except Exception as e:
    logging.exception("Failed to import PieChartWidget/PieWorker/MyMplCanvas from widget_piechart: %s", e)

    class PieChartWidget:
        """Placeholder PieChartWidget (PyQt not available)."""
        def __init__(self, *args, **kwargs):
            logging.warning("Using placeholder PieChartWidget (no GUI).")

    class PieWorker:
        """Placeholder PieWorker."""
        def __init__(self, *args, **kwargs):
            logging.warning("Using placeholder PieWorker (no GUI).")
        def start(self, *args, **kwargs):
            return None
        def stop(self, *args, **kwargs):
            return None

    class MyMplCanvas:
        """Placeholder MyMplCanvas (fallback to Agg canvas if needed)."""
        def __init__(self, *args, **kwargs):
            logging.warning("Using placeholder MyMplCanvas (no GUI).")

# ?щ끂異?API
__all__ = [
    "UserinfoWidget",
    "PieChartWidget",
    "PieWorker",
    "MyMplCanvas",
]
