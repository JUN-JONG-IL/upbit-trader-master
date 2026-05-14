# src/01_core ?대뜑

## 紐⑹쟻
upbit-trader ?뚮옯?쇱쓽 **?듭떖 ?명봽??諛?怨듯넻 紐⑤뱢**???쒓났?⑸땲??

## ?대뜑 援ъ“

```
src/01_core/
?쒋?? auth/           # ?몄쬆 諛?濡쒓렇??
?쒋?? base/           # 湲곕낯 ?명봽??(?대깽??猷⑦봽 ??
?쒋?? config/         # ?ㅼ젙 愿由?(援?root config/ ?ы븿)
?쒋?? lib/            # ?듭떖 ?쇱씠釉뚮윭由?(援?root lib/)
?붴?? utils/          # 怨듯넻 ?좏떥由ы떚
```

## 媛??대뜑 ?ㅻ챸

### auth/ - ?몄쬆 諛?濡쒓렇??
?ъ슜???몄쬆, ?몄뀡 愿由? 2FA ?깆쓣 ?대떦?⑸땲??

**援ъ“**:
- `services/`: 鍮꾩쫰?덉뒪 濡쒖쭅 (AuthService, SessionManager, TwoFactorAuth)
- `ui/`: 濡쒓렇???붾㈃ UI (LoginWidget, login.ui)

**?ъ슜 ?덉떆**:
```python
from auth import gui_main, AuthService

# GUI 濡쒓렇???ㅽ뻾
gui_main()

# ?쒕퉬??吏곸젒 ?ъ슜
auth_service = AuthService()
auth_service.authenticate(username, password)
```

### base/ - 湲곕낯 ?명봽??
?뚮옯???꾩뿭?먯꽌 ?ъ슜?섎뒗 湲곕낯 ?명봽?쇰? ?쒓났?⑸땲??

**二쇱슂 湲곕뒫**:
- `event_loop.py`: asyncio ?대깽??猷⑦봽 愿由?(Windows SelectorEventLoopPolicy ?ㅼ젙)

**?ъ슜 ?덉떆**:
```python
from base import setup_event_loop, get_event_loop

# ???쒖옉 ????踰덈쭔 ?몄텧
setup_event_loop()

# ?대깽??猷⑦봽 媛?몄삤湲?
loop = get_event_loop()
```

### config/ - ?ㅼ젙 愿由?
YAML 湲곕컲 ?ㅼ젙 ?뚯씪 濡쒕뵫 諛?愿由щ? ?대떦?⑸땲??

**二쇱슂 ?뚯씪**:
- `config.yaml`: ?ㅼ젣 ?ㅼ젙 ?뚯씪 (Git ?쒖쇅)
- `config.yaml.example`: ?ㅼ젙 ?쒗뵆由?
- `loader.py`: ?ㅼ젙 濡쒕뵫 濡쒖쭅

**?ъ슜 ?덉떆**:
```python
from config import load_config

config = load_config()
upbit_key = config['UPBIT']['ACCESS_KEY']
```

### lib/ - ?듭떖 ?쇱씠釉뚮윭由?
MongoDB/Redis/SQLAlchemy ?듯빀 IO ?몃뱾??諛??듭떖 ?쇱씠釉뚮윭由щ? ?쒓났?⑸땲??

**二쇱슂 紐⑤뱢**:
- `db_handler.py`: DBHandler ?대옒??(MongoDB/Redis/SQLAlchemy ?듯빀, dask/Polars 吏??

**?ъ슜 ?덉떆**:
```python
from lib import DBHandler

db = DBHandler(ip="localhost", port=27017)
inserted_id = await db.insert_item_one(data, "candles", "KRW-BTC_minute_1")
result = await db.find_item_one({"symbol": "KRW-BTC"}, "candles", "KRW-BTC_minute_1")
```

### utils/ - 怨듯넻 ?좏떥由ы떚
?뚮옯???꾩뿭?먯꽌 ?ъ슜?섎뒗 ?좏떥由ы떚 ?⑥닔/?대옒?ㅻ? ?쒓났?⑸땲??

**二쇱슂 紐⑤뱢**:
- `logger.py`: JSON 援ъ“??濡쒓퉭
- `debounce.py`, `throttle.py`: ?⑥닔 ?ㅽ뻾 ?쒖뼱
- `metrics_lite.py`: 寃쎈웾 硫뷀듃由?뒪 ?섏쭛
- `compute/`: 湲곗닠??吏??怨꾩궛 ?붿쭊
- `metrics/`: Prometheus 硫뷀듃由?뒪 export

**?ъ슜 ?덉떆**:
```python
from utils import get_logger, debounce, throttle
from utils.compute import IndicatorEngine

logger = get_logger()

@debounce(300)  # 300ms debounce
def on_resize():
    logger.info("Resized")
```

## 媛쒕컻 媛?대뱶

### ?대뜑 ?ㅼ씠諛?洹쒖튃
- ?レ옄 prefix ?좎?: `01_core`, `data_01`, ...
- 紐낇솗???⑥닔/蹂듭닔 援щ텇: `auth` (?⑥씪 媛쒕뀗), `utils` (蹂듭닔 ?좏떥由ы떚)

### import 寃쎈줈
- ?덈? import ?ъ슜: `from auth import ...`
- ?곷? import 湲덉? (?뚯뒪???쒖쇅)

### ?섏쐞 ?명솚??
- 湲곗〈 import 寃쎈줈 ?좎? ?꾩닔
- `__init__.py`?먯꽌 re-export濡?蹂댁옣

## ?뺤옣 怨꾪쉷
- `validation/`: ?낅젰 寃利?紐⑤뱢
- `security/`: 蹂댁븞 ?좏떥由ы떚 (?뷀샇?? ?댁떆 ??

---

**?묒꽦**: Copilot Workspace Refactor
**?좎쭨**: 2026-03-05

