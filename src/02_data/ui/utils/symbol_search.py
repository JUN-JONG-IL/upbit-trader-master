# -*- coding: utf-8 -*-
"""
심볼 검색 유틸리티 (symbol_search.py)

기능:
  - 한글 초성 추출
  - 심볼(영문) / 한글명 / 초성 복합 매칭
  - 전체 심볼 필터링
  - 알려진 코인/종목 한글명 사전 구축
"""
from __future__ import annotations

from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# 초성 리스트 (유니코드 한글 자음 순서)
# ---------------------------------------------------------------------------
_CHOSUNG_LIST = [
    'ㄱ', 'ㄲ', 'ㄴ', 'ㄷ', 'ㄸ', 'ㄹ', 'ㅁ', 'ㅂ', 'ㅃ',
    'ㅅ', 'ㅆ', 'ㅇ', 'ㅈ', 'ㅉ', 'ㅊ', 'ㅋ', 'ㅌ', 'ㅍ', 'ㅎ',
]

_HANGUL_START = 0xAC00   # '가'
_HANGUL_END   = 0xD7A3   # '힣'
_JUNGSUNG_COUNT = 21
_JONGSUNG_COUNT = 28


def get_chosung(text: str) -> str:
    """한글 문자열에서 초성만 추출합니다.

    영문·숫자·기호는 그대로 반환합니다.

    Args:
        text: 입력 문자열 (한글 포함 가능)

    Returns:
        초성 문자열 (예: '비트코인' → 'ㅂㅌㅋㅇ')
    """
    result = []
    for ch in text:
        code = ord(ch)
        if _HANGUL_START <= code <= _HANGUL_END:
            # 음절 인덱스 = (초성 * 21 + 중성) * 28 + 종성
            syllable_index = code - _HANGUL_START
            chosung_index = syllable_index // (_JUNGSUNG_COUNT * _JONGSUNG_COUNT)
            result.append(_CHOSUNG_LIST[chosung_index])
        else:
            result.append(ch)
    return ''.join(result)


def _is_all_chosung(text: str) -> bool:
    """문자열이 전부 초성(ㄱ~ㅎ)으로만 이루어져 있는지 확인합니다."""
    if not text:
        return False
    return all(ch in _CHOSUNG_LIST for ch in text)


def get_initials(text: str) -> str:
    """영문 텍스트에서 각 단어의 첫 글자를 추출합니다 (이니셜).

    Args:
        text: 영문 텍스트 (예: 'Bitcoin Cash')

    Returns:
        이니셜 문자열 (예: 'BC')
    """
    words = text.split()
    return "".join(w[0].upper() for w in words if w)


def _is_english_query(text: str) -> bool:
    """검색어가 순수 영문자만으로 이루어져 있는지 확인합니다."""
    return bool(text) and all(c.isalpha() and ord(c) < 128 for c in text)


def match_symbol(query: str, symbol: str, name_ko: str = "", name_en: str = "") -> bool:
    """검색어가 심볼 또는 명칭과 매칭되는지 확인합니다.

    매칭 방식 (우선순위 순):
    1. 영문 심볼 부분 일치 (대소문자 무시) - KRW-BTC에서 'btc' 검색
    2. 한글명 부분 일치 - '비트코인'
    3. 한글 초성 매칭 - 'ㅂㅌㅋㅇ'
    4. 영문명 부분 일치 (대소문자 무시) - 'bitcoin'
    5. 영문 단어 첫글자 약어 매칭 - 'bc' → 'BitCoin' 첫글자들 (b,c 매칭)
    6. 심볼에서 특수문자(-) 제거 후 매칭 - 'krwbtc' → 'KRW-BTC'

    Args:
        query: 검색어
        symbol: 심볼 문자열 (예: 'KRW-BTC')
        name_ko: 한글명 (예: '비트코인')
        name_en: 영문명 (예: 'Bitcoin')

    Returns:
        매칭 여부
    """
    if not query:
        return True

    q = query.strip()
    q_lower = q.lower()
    s_lower = symbol.lower()

    # 1) 영문 심볼 부분 일치 (대소문자 무시)
    if q_lower in s_lower:
        return True

    # 6) 심볼에서 특수문자 제거 후 매칭 (예: 'krwbtc' → 'KRW-BTC')
    s_clean = s_lower.replace("-", "").replace("_", "").replace(".", "").replace("=", "")
    q_clean = q_lower.replace("-", "").replace("_", "")
    if q_clean in s_clean:
        return True

    # 2) 한글명 부분 일치
    if name_ko and q in name_ko:
        return True

    # 3) 한글 초성 매칭
    if name_ko and _is_all_chosung(q):
        chosung_of_name = get_chosung(name_ko)
        if q in chosung_of_name:
            return True

    # 4) 영문명 부분 일치
    if name_en and q_lower in name_en.lower():
        return True

    # 5) 영문 단어 첫글자 약어 매칭 (예: 'bc' → 'Bitcoin Cash')
    if name_en and q.isalpha() and len(q) >= 2:
        words = name_en.split()
        if len(words) >= 2:
            abbr = "".join(w[0].lower() for w in words if w)
            if q_lower == abbr:
                return True

    # 심볼 뒷부분만 매칭 (예: 'eth' → 'KRW-ETH'에서 ETH 부분)
    parts = symbol.split("-")
    for part in parts:
        if q_lower == part.lower():
            return True

    return False


def filter_symbols(
    query: str,
    symbols: List[str],
    name_map: Dict[str, str],
    name_en_map: Optional[Dict[str, str]] = None,
) -> List[str]:
    """검색어로 전체 심볼 목록을 필터링합니다.

    Args:
        query: 검색어 (빈 문자열이면 전체 반환)
        symbols: 심볼 목록
        name_map: 심볼 → 한글명 매핑 딕셔너리
        name_en_map: 심볼 → 영문명 매핑 딕셔너리 (선택)

    Returns:
        매칭된 심볼 목록 (원래 순서 유지)
    """
    if not query:
        return list(symbols)
    if name_en_map is None:
        name_en_map = {}
    return [
        s for s in symbols
        if match_symbol(query, s, name_map.get(s, ""), name_en_map.get(s, ""))
    ]


def build_name_map() -> Dict[str, str]:
    """알려진 코인/종목 한글명 사전을 구축합니다.

    Returns:
        심볼 → 한글명 딕셔너리
    """
    return {
        # ── 업비트 KRW 마켓 주요 암호화폐 ───────────────────────────────
        "KRW-BTC":   "비트코인",
        "KRW-ETH":   "이더리움",
        "KRW-XRP":   "리플",
        "KRW-SOL":   "솔라나",
        "KRW-ADA":   "에이다",
        "KRW-DOGE":  "도지코인",
        "KRW-DOT":   "폴카닷",
        "KRW-AVAX":  "아발란체",
        "KRW-LINK":  "체인링크",
        "KRW-MATIC": "폴리곤",
        "KRW-ATOM":  "코스모스",
        "KRW-LTC":   "라이트코인",
        "KRW-BCH":   "비트코인캐시",
        "KRW-ETC":   "이더리움클래식",
        "KRW-TRX":   "트론",
        "KRW-UNI":   "유니스왑",
        "KRW-NEAR":  "니어프로토콜",
        "KRW-FTM":   "팬텀",
        "KRW-SAND":  "샌드박스",
        "KRW-MANA":  "디센트럴랜드",
        "KRW-SHIB":  "시바이누",
        "KRW-APT":   "앱토스",
        "KRW-ARB":   "아비트럼",
        "KRW-OP":    "옵티미즘",
        "KRW-SUI":   "수이",
        "KRW-SEI":   "세이",
        "KRW-INJ":   "인젝티브",
        "KRW-IMX":   "이뮤터블",
        "KRW-ALGO":  "알고랜드",
        "KRW-HBAR":  "헤데라",
        "KRW-VET":   "비체인",
        "KRW-THETA": "세타토큰",
        "KRW-FIL":   "파일코인",
        "KRW-ICP":   "인터넷컴퓨터",
        "KRW-EOS":   "이오스",
        "KRW-AAVE":  "에이브",
        "KRW-CRV":   "커브",
        "KRW-GRT":   "그래프",
        "KRW-COMP":  "컴파운드",
        "KRW-MKR":   "메이커",
        "KRW-SNX":   "신세틱스",
        "KRW-YFI":   "연파이낸스",
        "KRW-BAT":   "베이직어텐션토큰",
        "KRW-ZIL":   "질리카",
        "KRW-ENJ":   "엔진코인",
        "KRW-CHZ":   "칠리즈",
        "KRW-FLOW":  "플로우",
        "KRW-STX":   "스택스",
        "KRW-XTZ":   "테조스",
        "KRW-KSM":   "쿠사마",
        "KRW-KLAY":  "클레이튼",
        # ── 국내 주식 주요 종목 ──────────────────────────────────────────
        "005930": "삼성전자",
        "000660": "SK하이닉스",
        "035420": "NAVER",
        "005380": "현대차",
        "051910": "LG화학",
        "006400": "삼성SDI",
        "035720": "카카오",
        "207940": "삼성바이오로직스",
        "068270": "셀트리온",
        "323410": "카카오뱅크",
        # ── 해외 주식 주요 종목 ──────────────────────────────────────────
        "AAPL":  "애플",
        "MSFT":  "마이크로소프트",
        "GOOGL": "알파벳",
        "AMZN":  "아마존",
        "NVDA":  "엔비디아",
        "TSLA":  "테슬라",
        "META":  "메타",
        "NFLX":  "넷플릭스",
        # ── 선물 ────────────────────────────────────────────────────────
        "ES=F":  "S&P500선물",
        "NQ=F":  "나스닥선물",
        "YM=F":  "다우선물",
        "GC=F":  "금선물",
        "CL=F":  "원유선물",
    }


def build_name_en_map() -> Dict[str, str]:
    """알려진 코인/종목 영문명 사전을 구축합니다.

    Returns:
        심볼 → 영문명 딕셔너리
    """
    return {
        "KRW-BTC":   "Bitcoin",
        "KRW-ETH":   "Ethereum",
        "KRW-XRP":   "Ripple",
        "KRW-SOL":   "Solana",
        "KRW-ADA":   "Cardano",
        "KRW-DOGE":  "Dogecoin",
        "KRW-DOT":   "Polkadot",
        "KRW-AVAX":  "Avalanche",
        "KRW-LINK":  "Chainlink",
        "KRW-MATIC": "Polygon",
        "KRW-ATOM":  "Cosmos",
        "KRW-LTC":   "Litecoin",
        "KRW-BCH":   "Bitcoin Cash",
        "KRW-ETC":   "Ethereum Classic",
        "KRW-TRX":   "Tron",
        "KRW-UNI":   "Uniswap",
        "KRW-NEAR":  "NEAR Protocol",
        "KRW-FTM":   "Fantom",
        "KRW-SAND":  "The Sandbox",
        "KRW-MANA":  "Decentraland",
        "KRW-SHIB":  "Shiba Inu",
        "KRW-APT":   "Aptos",
        "KRW-ARB":   "Arbitrum",
        "KRW-OP":    "Optimism",
        "KRW-SUI":   "Sui",
        "KRW-SEI":   "Sei",
        "KRW-INJ":   "Injective",
        "KRW-IMX":   "Immutable X",
        "KRW-ALGO":  "Algorand",
        "KRW-HBAR":  "Hedera",
        "KRW-VET":   "VeChain",
        "KRW-THETA": "Theta Token",
        "KRW-FIL":   "Filecoin",
        "KRW-ICP":   "Internet Computer",
        "KRW-EOS":   "EOS",
        "KRW-AAVE":  "Aave",
        "KRW-CRV":   "Curve DAO",
        "KRW-GRT":   "The Graph",
        "KRW-COMP":  "Compound",
        "KRW-MKR":   "Maker",
        "KRW-SNX":   "Synthetix",
        "KRW-YFI":   "Yearn Finance",
        "KRW-BAT":   "Basic Attention Token",
        "KRW-ZIL":   "Zilliqa",
        "KRW-ENJ":   "Enjin Coin",
        "KRW-CHZ":   "Chiliz",
        "KRW-FLOW":  "Flow",
        "KRW-STX":   "Stacks",
        "KRW-XTZ":   "Tezos",
        "KRW-KSM":   "Kusama",
        "KRW-KLAY":  "Klaytn",
        # 해외 주식
        "AAPL":  "Apple",
        "MSFT":  "Microsoft",
        "GOOGL": "Alphabet",
        "AMZN":  "Amazon",
        "NVDA":  "NVIDIA",
        "TSLA":  "Tesla",
        "META":  "Meta Platforms",
        "NFLX":  "Netflix",
        # 선물
        "ES=F":  "S&P 500 Futures",
        "NQ=F":  "Nasdaq Futures",
        "YM=F":  "Dow Futures",
        "GC=F":  "Gold Futures",
        "CL=F":  "Crude Oil Futures",
    }
