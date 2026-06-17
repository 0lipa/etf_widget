# Font
FONT = "Noto Sans KR"

# ══════════════════════════════════════════════════════════════════
#  ★ 여기에 보유 ETF 정보를 입력하세요
# ══════════════════════════════════════════════════════════════════
HOLDINGS = [
    {
        "name": "두산로보틱스",   # 표시 이름
        "ticker": "454910",            # 종목코드 (KRX: 6자리 숫자 / 미국: 영문 티커)
        "market": "KRX",               # "KRX" 또는 "US"
        "buy_price": 111500,            # 매입 단가 (원 또는 달러)
        "quantity": 2,                # 보유 수량
    },
    {
        "name": "KODEX 미국AI전력핵심인프라",
        "ticker": "487230",
        "market": "KRX",
        "buy_price": 25850,
        "quantity": 8,
    },
    # 미국 ETF 예시 (사용 시 주석 해제 후 수정)
    # {
    #     "name": "VOO",
    #     "ticker": "VOO",
    #     "market": "US",
    #     "buy_price": 490.0,
    #     "quantity": 2,
    # },
]

REFRESH_SECONDS = 60   # 가격 갱신 주기 (초)
# ══════════════════════════════════════════════════════════════════


# ── 색상 팔레트 (Warm Cream / ETF.dc.html 기반) ───────────────────
BG          = "#F2EAE0"   # 따뜻한 크림 (배경)
CARD_BG     = "#FFFFFF"   # 카드 흰색
BORDER      = "#E5DDD5"   # 구분선 / 매입가 칩 배경
HANDLE_BG   = "#F2EAE0"   # 드래그 헤더 (BG와 동일)
TEXT_PRI    = "#2D2620"   # 짙은 웜 브라운 (주 텍스트)
TEXT_SEC    = "#8A8070"   # 중간 웜 그레이 (보조 텍스트)
TEXT_CODE   = "#9D9388"   # 연한 웜 그레이 (종목코드)
UP_COLOR    = "#1E7A4A"   # 포레스트 그린 (상승)
UP_BG       = "#CDEEDE"   # 연한 민트 (상승 배지 배경)
DOWN_COLOR  = "#C04A38"   # 코랄 레드 (하락)
DOWN_BG     = "#F5E0DA"   # 연한 살몬 (하락 배지 배경)
FLAT_COLOR  = "#8A8070"   # 회색 (보합)
FLAT_BG     = "#EEEAE5"   # 뉴트럴 배지 배경
FOOTER_BG   = "#E8DBD0"   # 푸터 배경
BTN_BG      = "#E2D0BE"   # 토글 버튼 배경
BTN_FG      = "#5C4632"   # 토글 버튼 텍스트

# 푸터 상태 표시 점
FOOTER_DOT  = "#70B87A"   # 연한 초록 (활성 상태)

# macOS 신호등 버튼 색상 (피치 톤)
DOT_RED     = "#F09080"
DOT_YELLOW  = "#F0C878"
DOT_GREEN   = "#80C878"
