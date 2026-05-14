"""
[Purpose]
- 코인리스트 검색(자동완성/초성/로마자) 기능을 분리하여 관리한다.

[Responsibilities]
- 초성 추출 / 로마자 변환 / 매칭 규칙
- QCompleter prefix 갱신 (debounce 100ms 적용)
- 엔터/선택 시 코인 선택 및 스크롤

[Main Flow]
- CoinlistWidget에서 이벤트를 받아 SearchController가 처리 후,
  coin_list.selectRow / scrollToItem / chkItemClicked 호출

[Dependencies]
- unicodedata
- functools.lru_cache
- PyQt5 (QEvent, Qt)
- utils.debounce

[UI Binding]
- CoinlistWidget.search_line, CoinlistWidget.completer, CoinlistWidget.coin_list
"""

import unicodedata
from functools import lru_cache

from PyQt5.QtCore import QEvent, Qt, QTimer
from PyQt5.QtWidgets import QAbstractItemView


class CoinListSearchController:
    def __init__(self, widget):
        self.widget = widget  # CoinlistWidget
        
        # Debounce 타이머 (100ms)
        self._debounce_timer = QTimer()
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(100)  # 100ms debounce
        self._debounce_timer.timeout.connect(self._do_update_completer)
        self._pending_text = ""

    def update_completer_model(self, text: str):
        """텍스트 입력 시 completer prefix 설정으로 필터링 (debounced 100ms)"""
        self._pending_text = text
        self._debounce_timer.stop()
        self._debounce_timer.start()
    
    def _do_update_completer(self):
        """실제 completer 업데이트 (debounce 후)"""
        self.widget.completer.setCompletionPrefix(self._pending_text)
        self.widget.completer.complete()

    def event_filter(self, obj, event) -> bool:
        if obj != self.widget.search_line:
            return False

        if event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_Escape:
                self.widget.search_line.clear()
                return True

        if event.type() == QEvent.InputMethod:
            committed = self.widget.search_line.text()
            preedit = event.preeditString()
            full_query = committed + preedit
            self.update_completer_model(full_query)
            return False

        return False

    def matches(self, query: str, name: str) -> bool:
        q_lower = query.lower()
        t_lower = name.replace(" ", "").lower()
        q_chosung = self.extract_chosung(query)
        t_chosung = self.extract_chosung(name.replace(" ", ""))
        q_roman = self.extract_roman(query)
        t_roman = self.extract_roman(name.replace(" ", ""))

        q_adjusted = q_lower.replace("c", "k").replace("v", "b")
        q_roman_adjusted = q_roman.replace("c", "k").replace("v", "b")

        has_complete_han = any("가" <= c <= "힣" for c in query)

        return (
            t_lower.startswith(q_lower)
            or (t_chosung.startswith(q_chosung) if not has_complete_han else False)
            or t_roman.startswith(q_lower)
            or t_roman.startswith(q_roman)
            or t_roman.startswith(q_adjusted)
            or t_roman.startswith(q_roman_adjusted)
        )

    def on_completion_activated(self, text: str):
        self.widget.search_line.setText(text)
        self.select_and_scroll_to_coin(text)

    def on_search_enter(self):
        text = self.widget.search_line.text()
        if text:
            self.select_and_scroll_to_coin(text)

    def select_and_scroll_to_coin(self, text: str):
        found_rows = []
        for i, coin in enumerate(self.widget.displayed_coins):
            if self.matches(text, coin.korean_name) or self.matches(text, coin.english_name):
                name = coin.korean_name if self.widget.name_toggle_korean else coin.english_name
                found_rows.append((i, name))

        if not found_rows:
            return

        q_lower = text.lower()
        found_rows.sort(key=lambda x: (0 if x[1].lower() == q_lower else 1, x[1].lower()))
        selected_row = found_rows[0][0]

        self.widget.coin_list.selectRow(selected_row)
        self.widget.coin_list.scrollToItem(
            self.widget.coin_list.item(selected_row, 0),
            QAbstractItemView.PositionAtTop,
        )
        self.widget.chkItemClicked(selected_row)

    @lru_cache(maxsize=512)
    def extract_chosung(self, text: str) -> str:
        """한국어 문자열의 초성을 추출하는 함수"""
        chosung = ""
        CHO = ["ㄱ","ㄲ","ㄴ","ㄷ","ㄸ","ㄹ","ㅁ","ㅂ","ㅃ","ㅅ","ㅆ","ㅇ","ㅈ","ㅉ","ㅊ","ㅋ","ㅌ","ㅍ","ㅎ"]
        for char in text:
            if "가" <= char <= "힣":
                code = ord(char) - ord("가")
                chosung += CHO[code // 588]
            else:
                chosung += char.lower()
        return chosung

    @lru_cache(maxsize=512)
    def extract_roman(self, text: str) -> str:
        """한국어 문자열을 로마자로 변환하는 함수"""
        roman = ""
        cho_map = {'\u1100':'g', '\u1101':'kk', '\u1102':'n', '\u1103':'d', '\u1104':'tt', '\u1105':'r', '\u1106':'m', '\u1107':'b', '\u1108':'pp', '\u1109':'s', '\u110a':'ss', '\u110b':'', '\u110c':'j', '\u110d':'jj', '\u110e':'ch', '\u110f':'k', '\u1110':'t', '\u1111':'p', '\u1112':'h'}
        jung_map = {'\u1161':'a', '\u1162':'ae', '\u1163':'ya', '\u1164':'yae', '\u1165':'eo', '\u1166':'e', '\u1167':'yeo', '\u1168':'ye', '\u1169':'o', '\u116a':'wa', '\u116b':'wae', '\u116c':'oe', '\u116d':'yo', '\u116e':'u', '\u116f':'wo', '\u1170':'we', '\u1171':'wi', '\u1172':'yu', '\u1173':'eu', '\u1174':'ui', '\u1175':'i'}
        jong_map = {'':'', '\u11a8':'k', '\u11a9':'k', '\u11aa':'k', '\u11ab':'n', '\u11ac':'n', '\u11ad':'n', '\u11ae':'t', '\u11af':'l', '\u11b0':'k', '\u11b1':'m', '\u11b2':'l', '\u11b3':'l', '\u11b4':'l', '\u11b5':'p', '\u11b6':'l', '\u11b7':'m', '\u11b8':'p', '\u11b9':'p', '\u11ba':'t', '\u11bb':'t', '\u11bc':'ng', '\u11bd':'t', '\u11be':'t', '\u11bf':'k', '\u11c0':'t', '\u11c1':'p', '\u11c2':'t'}
        for char in text:
            if "가" <= char <= "힣":
                decomposed = unicodedata.normalize("NFD", char)
                cho = decomposed[0]
                jung = decomposed[1]
                jong = decomposed[2] if len(decomposed) > 2 else ""
                roman += cho_map.get(cho, "") + jung_map.get(jung, "") + jong_map.get(jong, "")
            else:
                roman += char.lower()
        return roman