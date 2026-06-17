"""
- 한국 ETF: pykrx
- 미국 ETF: yfinance
- 항상 바탕화면 위에 표시 (tkinter)
"""

import tkinter as tk
import threading
from datetime import datetime, date
import subprocess
import sys
from config import (
    FONT, HOLDINGS, REFRESH_SECONDS,
    BG, CARD_BG, BORDER,
    TEXT_PRI, TEXT_SEC, TEXT_CODE,
    UP_COLOR, UP_BG, DOWN_COLOR, DOWN_BG, FLAT_COLOR, FLAT_BG,
    FOOTER_BG, BTN_BG, BTN_FG, FOOTER_DOT,
    DOT_RED, DOT_YELLOW, DOT_GREEN,
)

# ── 의존성 자동 설치 ──────────────────────────────────────────────
def install(package):
    subprocess.check_call([sys.executable, "-m", "pip", "install", package, "-q"])

try:
    import yfinance as yf
except ImportError:
    print("yfinance 설치 중..."); install("yfinance"); import yfinance as yf

try:
    from pykrx import stock as krx
except ImportError:
    print("pykrx 설치 중..."); install("pykrx"); from pykrx import stock as krx


def get_krx_price(ticker: str) -> float | None:
    try:
        today = date.today().strftime("%Y%m%d")
        df = krx.get_market_ohlcv_by_date(
            fromdate=(date.today().replace(day=1)).strftime("%Y%m%d"),
            todate=today,
            ticker=ticker,
        )
        if df is None or df.empty:
            return None
        return float(df["종가"].iloc[-1])
    except Exception as e:
        print(f"[KRX 오류] {ticker}: {e}")
        return None


def get_us_price(ticker: str) -> float | None:
    try:
        info = yf.Ticker(ticker).fast_info
        price = getattr(info, "last_price", None) or getattr(info, "regularMarketPrice", None)
        return float(price) if price else None
    except Exception as e:
        print(f"[US 오류] {ticker}: {e}")
        return None


def fetch_prices() -> list[dict]:
    results = []
    for h in HOLDINGS:
        if h["market"] == "KRX":
            current = get_krx_price(h["ticker"])
            fmt = lambda v: f"₩{v:,.0f}"
        else:
            current = get_us_price(h["ticker"])
            fmt = lambda v: f"${v:,.2f}"

        if current is None:
            results.append({**h, "current": None, "pct": None,
                            "pl": None, "total_pl": None, "fmt": fmt})
            continue

        buy = h["buy_price"]
        qty = h["quantity"]
        pct      = (current - buy) / buy * 100
        pl       = current - buy
        total_pl = pl * qty

        results.append({
            **h,
            "current":   current,
            "pct":       pct,
            "pl":        pl,
            "total_pl":  total_pl,
            "fmt":       fmt,
        })
    return results


# ── 위젯 UI ───────────────────────────────────────────────────────
class ETFWidget:
    WIDTH = 340

    def __init__(self, root: tk.Tk):
        self.root = root
        self._drag_x = self._drag_y = 0
        self._collapsed = False
        self._card_widgets: list[dict] = []
        self._last_results: list[dict] = []
        self._setup_window()
        self._build_ui()
        self._refresh_data()

    def _setup_window(self):
        r = self.root
        r.title("ETF Widget")
        r.configure(bg=BG)
        r.resizable(False, False)
        r.overrideredirect(True)
        r.attributes("-topmost", True)
        r.attributes("-alpha", 0.97)
        sw = r.winfo_screenwidth()
        r.geometry(f"+{sw - self.WIDTH - 24}+64")

    def _bind_drag(self, widget):
        widget.bind("<ButtonPress-1>", self._drag_start)
        widget.bind("<B1-Motion>", self._drag_move)

    def _build_ui(self):
        # ── Header ──────────────────────────────────────────
        hdr = tk.Frame(self.root, bg=BG)
        hdr.pack(fill="x", padx=14, pady=(14, 10))
        self._bind_drag(hdr)

        # 왼쪽: macOS 도트 + 타이틀
        left = tk.Frame(hdr, bg=BG)
        left.pack(side="left")
        self._bind_drag(left)

        dots_frame = tk.Frame(left, bg=BG)
        dots_frame.pack(side="left")
        for col, action in [(DOT_RED, self.root.destroy), (DOT_YELLOW, None), (DOT_GREEN, None)]:
            c = tk.Canvas(dots_frame, width=11, height=11, bg=BG,
                          highlightthickness=0, cursor="hand2" if action else "arrow")
            c.pack(side="left", padx=(0, 3))
            c.create_oval(1, 1, 10, 10, fill=col, outline="")
            if action:
                c.bind("<Button-1>", lambda e, a=action: a())
            else:
                self._bind_drag(c)

        title_area = tk.Frame(left, bg=BG)
        title_area.pack(side="left", padx=(10, 0))
        self._bind_drag(title_area)

        title_lbl = tk.Label(title_area, text="ETF 위젯", bg=BG, fg=TEXT_PRI,
                             font=(FONT, 13, "bold"), anchor="w")
        title_lbl.pack(anchor="w")
        self._bind_drag(title_lbl)

        self._subtitle_var = tk.StringVar(value="— 개 종목 추적 중")
        sub_lbl = tk.Label(title_area, textvariable=self._subtitle_var, bg=BG, fg=TEXT_SEC,
                           font=(FONT, 10), anchor="w")
        sub_lbl.pack(anchor="w")
        self._bind_drag(sub_lbl)

        # 오른쪽: 토글 버튼
        self._toggle_btn = tk.Label(
            hdr, text="접기 ↕", bg=BTN_BG, fg=BTN_FG,
            font=(FONT, 10, "bold"), padx=13, pady=6, cursor="hand2",
        )
        self._toggle_btn.pack(side="right")
        self._toggle_btn.bind("<Button-1>", self._toggle)

        # ── 카드 컨테이너 ────────────────────────────────────
        self.container = tk.Frame(self.root, bg=BG, padx=10)
        self.container.pack(fill="both", expand=True)

        # ── 푸터 ────────────────────────────────────────────
        foot_outer = tk.Frame(self.root, bg=FOOTER_BG)
        foot_outer.pack(fill="x", padx=10, pady=(0, 10))

        foot_inner = tk.Frame(foot_outer, bg=FOOTER_BG)
        foot_inner.pack(pady=7, padx=12)

        dot_c = tk.Canvas(foot_inner, width=5, height=5, bg=FOOTER_BG, highlightthickness=0)
        dot_c.pack(side="left")
        dot_c.create_oval(0, 0, 5, 5, fill=FOOTER_DOT, outline="")

        self._status_var = tk.StringVar(value="갱신: --:--:--  ·  60s마다 자동 갱신")
        tk.Label(foot_inner, textvariable=self._status_var, bg=FOOTER_BG, fg=TEXT_SEC,
                 font=(FONT, 9)).pack(side="left", padx=(6, 0))

    def _toggle(self, event=None):
        self._collapsed = not self._collapsed
        self._toggle_btn.config(text="펼치기 ↕" if self._collapsed else "접기 ↕")
        self._rebuild_cards(self._last_results)

    def _make_card(self, parent) -> dict:
        """Canvas 기반 라운드 모서리 카드를 생성한다."""
        outer = tk.Frame(parent, bg=BG)
        outer.pack(fill="x", pady=4)

        canvas = tk.Canvas(outer, bg=BG, highlightthickness=0, bd=0)
        canvas.pack(fill="x")

        inner = tk.Frame(canvas, bg=CARD_BG)
        inner_id = canvas.create_window(0, 0, anchor="nw", window=inner)

        def redraw(event=None):
            canvas.update_idletasks()
            w = canvas.winfo_width()
            if w <= 1:
                return
            h = inner.winfo_reqheight()
            if h <= 0:
                return
            canvas.config(height=h)
            canvas.delete("rr")
            r = 14
            pts = [r,0, w-r,0, w,0, w,r, w,h-r, w,h, w-r,h, r,h, 0,h, 0,h-r, 0,r, 0,0]
            canvas.create_polygon(pts, smooth=True, fill=CARD_BG, outline="", tags="rr")
            canvas.tag_lower("rr")
            canvas.itemconfig(inner_id, width=w)

        inner.bind("<Configure>", redraw)
        canvas.bind("<Configure>", redraw)

        w = {"outer": outer, "canvas": canvas, "inner": inner, "redraw": redraw}

        if self._collapsed:
            # 축소 모드: 이름 + 배지
            row = tk.Frame(inner, bg=CARD_BG, padx=14, pady=10)
            row.pack(fill="x")
            name_lbl = tk.Label(row, text="", bg=CARD_BG, fg=TEXT_PRI,
                                font=(FONT, 12, "bold"), anchor="w")
            name_lbl.pack(side="left", fill="x", expand=True)
            badge = tk.Label(row, text="", bg=FLAT_BG, fg=FLAT_COLOR,
                             font=(FONT, 11, "bold"), padx=10, pady=4)
            badge.pack(side="right")
            w.update({"name": name_lbl, "badge": badge})

        else:
            # 확장 모드: 이름/코드/배지 + 현재가 + 칩 3개
            pad = tk.Frame(inner, bg=CARD_BG, padx=14, pady=12)
            pad.pack(fill="x")

            # 상단: 이름+코드 (왼쪽), 등락 배지 (오른쪽)
            top = tk.Frame(pad, bg=CARD_BG)
            top.pack(fill="x", pady=(0, 8))

            name_area = tk.Frame(top, bg=CARD_BG)
            name_area.pack(side="left", fill="x", expand=True)
            name_lbl = tk.Label(name_area, text="", bg=CARD_BG, fg=TEXT_PRI,
                                font=(FONT, 13, "bold"), anchor="w")
            name_lbl.pack(anchor="w")
            code_lbl = tk.Label(name_area, text="", bg=CARD_BG, fg=TEXT_CODE,
                                font=(FONT, 10), anchor="w")
            code_lbl.pack(anchor="w")

            badge = tk.Label(top, text="", bg=FLAT_BG, fg=FLAT_COLOR,
                             font=(FONT, 13, "bold"), padx=10, pady=5)
            badge.pack(side="right", anchor="n")

            # 현재가
            price_lbl = tk.Label(pad, text="", bg=CARD_BG, fg=TEXT_PRI,
                                 font=(FONT, 22, "bold"), anchor="w")
            price_lbl.pack(anchor="w", pady=(0, 9))

            # 칩 3개: 매입가 / 주당 손익 / 총 손익
            chips = tk.Frame(pad, bg=CARD_BG)
            chips.pack(anchor="w", fill="x")

            buy_chip = tk.Label(chips, text="", bg=BORDER, fg=TEXT_SEC,
                                font=(FONT, 9), padx=8, pady=3)
            buy_chip.pack(side="left", padx=(0, 4))

            per_chip = tk.Label(chips, text="", bg=FLAT_BG, fg=FLAT_COLOR,
                                font=(FONT, 9, "bold"), padx=8, pady=3)
            per_chip.pack(side="left", padx=(0, 4))

            total_chip = tk.Label(chips, text="", bg=FLAT_BG, fg=FLAT_COLOR,
                                  font=(FONT, 9, "bold"), padx=8, pady=3)
            total_chip.pack(side="left")

            w.update({
                "name": name_lbl, "code": code_lbl, "badge": badge,
                "price": price_lbl,
                "buy_chip": buy_chip, "per_chip": per_chip, "total_chip": total_chip,
            })

        return w

    def _rebuild_cards(self, results: list[dict]):
        for c in self._card_widgets:
            c["outer"].destroy()
        self._card_widgets = [self._make_card(self.container) for _ in results]
        self._fill_cards(results)

    def _refresh_data(self):
        def worker():
            results = fetch_prices()
            self.root.after(0, lambda: self._update_ui(results))
        threading.Thread(target=worker, daemon=True).start()
        self.root.after(REFRESH_SECONDS * 1000, self._refresh_data)

    def _update_ui(self, results: list[dict]):
        self._last_results = results
        self._subtitle_var.set(f"{len(results)}개 종목 추적 중")
        if len(self._card_widgets) != len(results):
            self._rebuild_cards(results)
            return
        self._fill_cards(results)

    def _fill_cards(self, results: list[dict]):
        for w, r in zip(self._card_widgets, results):
            name = r.get("name", r["ticker"])

            if r["current"] is None:
                w["name"].config(text=name)
                w["badge"].config(text="조회 실패", bg=FLAT_BG, fg=FLAT_COLOR)
                if not self._collapsed:
                    w["code"].config(text=r["ticker"])
                    w["price"].config(text="—", fg=TEXT_SEC)
                    w["buy_chip"].config(text="매입 —", bg=BORDER, fg=TEXT_SEC)
                    w["per_chip"].config(text="주당 —", bg=FLAT_BG, fg=FLAT_COLOR)
                    w["total_chip"].config(text="총 —", bg=FLAT_BG, fg=FLAT_COLOR)
                self.root.after_idle(w["redraw"])
                continue

            pct   = r["pct"]
            fmt   = r["fmt"]
            up    = pct > 0
            c_fg  = UP_COLOR   if up else (DOWN_COLOR   if pct < 0 else FLAT_COLOR)
            c_bg  = UP_BG      if up else (DOWN_BG      if pct < 0 else FLAT_BG)
            arrow = "▲" if up  else ("▼" if pct < 0 else "—")
            badge_text = f"{arrow} {'+' if up else ''}{pct:.2f}%"

            w["name"].config(text=name)
            w["badge"].config(text=badge_text, bg=c_bg, fg=c_fg)

            if not self._collapsed:
                w["code"].config(text=r["ticker"])
                w["price"].config(text=fmt(r["current"]), fg=TEXT_PRI)

                sp = "+" if r["pl"] >= 0 else ""
                st = "+" if r["total_pl"] >= 0 else ""
                w["buy_chip"].config(text=f"매입 {fmt(r['buy_price'])}", bg=BORDER, fg=TEXT_SEC)
                w["per_chip"].config(text=f"주당 {sp}{fmt(r['pl'])}", bg=c_bg, fg=c_fg)
                w["total_chip"].config(text=f"총 {st}{fmt(r['total_pl'])}", bg=c_bg, fg=c_fg)

            self.root.after_idle(w["redraw"])

        now = datetime.now().strftime("%H:%M:%S")
        self._status_var.set(f"갱신: {now}  ·  {REFRESH_SECONDS}s마다 자동 갱신")

    def _drag_start(self, e):
        self._drag_x = e.x_root - self.root.winfo_x()
        self._drag_y = e.y_root - self.root.winfo_y()

    def _drag_move(self, e):
        self.root.geometry(f"+{e.x_root - self._drag_x}+{e.y_root - self._drag_y}")


if __name__ == "__main__":
    root = tk.Tk()
    ETFWidget(root)
    root.mainloop()
