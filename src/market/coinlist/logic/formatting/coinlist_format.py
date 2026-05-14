"""
[Purpose]
- 코인리스트 화면에서 사용하는 숫자/텍스트 포맷 유틸을 제공한다.

[Responsibilities]
- 가격 표기 규칙(format_price) 제공

[Main Flow]
- CoinlistWidget 및 coinlist_logic에서 표시 문자열 생성 시 호출

[Dependencies]
- 없음

[UI Binding]
- 없음
"""


def format_price(price, coin=None) -> str:
    if price is None or price == 0:
        return ""

    decimal_places = 0
    if price < 1:
        decimal_places = 4
    elif price < 10:
        decimal_places = 2
    elif price < 100:
        decimal_places = 1
    else:
        decimal_places = 0

    formatted = "{:,.{}f}".format(price, decimal_places)
    if "." in formatted:
        formatted = formatted.rstrip("0").rstrip(".")
    return formatted